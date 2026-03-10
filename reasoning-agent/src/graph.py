from __future__ import annotations

import re
from typing import List, Optional
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.prompts import REASONING_AGENT_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class ReasoningState(TypedDict):
    """Shared state flowing through the reasoning agent graph."""

    # Inputs (populated by the caller / main orchestrator)
    telemetry: str                        # Raw telemetry blob (metrics, traces, logs)
    sop_output: Optional[str]             # Checklist produced by the SOP agent (may be None)
    code_output: Optional[str]            # Execution results from the Code agent (may be None)

    # Internal / output
    signal_classification: str            # Per-signal NORMAL / WARNING / CRITICAL table
    hypotheses: str                       # Ranked root-cause hypotheses
    causal_chains: str                    # Inferred causal relationships between signals
    telemetry_gaps: str                   # Missing data that would confirm / rule out hypotheses
    reasoning_summary: str                # Full structured output consumed by the main agent


# ---------------------------------------------------------------------------
# Node helpers
# ---------------------------------------------------------------------------

# build user prompt is for the main agent
def _build_user_prompt(state: ReasoningState) -> str:
    telemetry = state["telemetry"]
    sop_output = state.get("sop_output") or "(not yet available)"
    code_output = state.get("code_output") or "(not yet available)"

    return f"""\
## Telemetry Input
{telemetry}

## SOP Agent Output (for context only — do not repeat its checklist)
{sop_output}

## Code Agent Execution Output (for context only — raw query/command results)
{code_output}

## Your Task
Analyse the telemetry above and produce a structured diagnostic rationale with the
following sections. Use exactly these headings:

### 1. Signal Classification
For every distinct metric, span attribute, or log signal present in the telemetry,
produce a table:

| Signal | Value | Status | Justification |
|--------|-------|--------|---------------|
| ...    | ...   | NORMAL / WARNING / CRITICAL | ... |

### 2. Root-Cause Hypotheses
List up to 5 hypotheses, ranked by confidence. Format each as:

**[Confidence: High/Medium/Low]** <Hypothesis statement>
- Supporting evidence: <signals that support this>
- Counter-evidence / unknowns: <what could disprove this>

### 3. Causal Chains
Describe any inferred causal relationships between signals (e.g. A → B → C).
Use plain English. If no causal chain is apparent, state "No clear causal chain identified."

### 4. Telemetry Gaps
List specific metrics, spans, or log fields that are absent but would be needed to
confirm or rule out the top hypotheses. If none, state "No critical gaps identified."

### 5. Diagnostic Summary
2–4 sentence plain-English summary of the most likely situation. This will be passed
directly to the main orchestrator agent.
"""


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def classify_signals_node(state: ReasoningState) -> dict:
    """
    First pass: extract and classify every telemetry signal independently.
    Produces a structured signal table stored in `signal_classification`.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    telemetry = state["telemetry"]
    prompt = f"""\
You are a telemetry parser. Given the raw telemetry below, extract every distinct
signal (metric name + value, span attribute, or log field) and classify it as
NORMAL, WARNING, or CRITICAL based on standard SRE thresholds.

Return ONLY a markdown table with columns:
| Signal | Value | Status | Justification |

Raw telemetry:
{telemetry}
"""
    messages = [
        SystemMessage(content=REASONING_AGENT_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]
    resp = llm.invoke(messages)
    return {"signal_classification": resp.content}


def hypothesise_node(state: ReasoningState) -> dict:
    """
    Second pass: using classified signals plus SOP/code context,
    generate ranked root-cause hypotheses and causal chains.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    signal_classification = state.get("signal_classification", "")
    sop_output = state.get("sop_output") or "(not yet available)"
    code_output = state.get("code_output") or "(not yet available)"

    prompt = f"""\
You have the following classified signals from the telemetry:

{signal_classification}

SOP Agent context:
{sop_output}

Code Agent execution results:
{code_output}

Based on the classified signals above, produce:

### 2. Root-Cause Hypotheses
List up to 5 hypotheses ranked by confidence:

**[Confidence: High/Medium/Low]** <Hypothesis statement>
- Supporting evidence: <signals that support this>
- Counter-evidence / unknowns: <what could disprove this>

### 3. Causal Chains
Describe inferred causal relationships between signals (A → B → C).
If none, state "No clear causal chain identified."

### 4. Telemetry Gaps
List specific missing signals that would confirm or rule out the top hypotheses.
If none, state "No critical gaps identified."
"""
    messages = [
        SystemMessage(content=REASONING_AGENT_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]
    resp = llm.invoke(messages)

    # Parse the three sections out of the single LLM response
    content = resp.content
    sections = _split_sections(content)

    return {
        "hypotheses": sections.get("hypotheses", content),
        "causal_chains": sections.get("causal_chains", ""),
        "telemetry_gaps": sections.get("telemetry_gaps", ""),
    }


def summarise_node(state: ReasoningState) -> dict:
    """
    Final pass: consolidate all intermediate reasoning into the full structured
    output that the main orchestrator will consume.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    signal_classification = state.get("signal_classification", "")
    hypotheses = state.get("hypotheses", "")
    causal_chains = state.get("causal_chains", "")
    telemetry_gaps = state.get("telemetry_gaps", "")

    prompt = f"""\
Consolidate the following reasoning artefacts into a single structured diagnostic report.
Use exactly the headings below and do not omit any section.

### 1. Signal Classification
{signal_classification}

### 2. Root-Cause Hypotheses
{hypotheses}

### 3. Causal Chains
{causal_chains}

### 4. Telemetry Gaps
{telemetry_gaps}

### 5. Diagnostic Summary
Write a 2–4 sentence plain-English summary of the most likely situation based on all
of the above. This will be read by the main orchestrator agent to produce final
recommendations for the user.
"""
    messages = [
        SystemMessage(content=REASONING_AGENT_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]
    resp = llm.invoke(messages)
    return {"reasoning_summary": resp.content}


# ---------------------------------------------------------------------------
# Section parser utility
# ---------------------------------------------------------------------------

def _split_sections(text: str) -> dict:
    """
    Loosely parse a markdown response that contains the three hypothesis sections.
    Returns a dict with keys: hypotheses, causal_chains, telemetry_gaps.
    """

    sections = {}
    patterns = {
        "hypotheses": r"###\s*2\.\s*Root.Cause Hypotheses(.*?)(?=###\s*3\.|$)",
        "causal_chains": r"###\s*3\.\s*Causal Chains(.*?)(?=###\s*4\.|$)",
        "telemetry_gaps": r"###\s*4\.\s*Telemetry Gaps(.*?)(?=###\s*5\.|$)",
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        sections[key] = m.group(1).strip() if m else ""
    return sections


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_reasoning_graph():
    """
    Construct and compile the LangGraph StateGraph for the reasoning agent.

    Node execution order:
        START → classify_signals → hypothesise → summarise → END

    The graph is designed to be called either standalone (via run_reasoning_agent.py)
    or as a sub-graph invoked by the main orchestrator agent.

    Expected input keys:
        telemetry   (required) – raw telemetry string
        sop_output  (optional) – SOP agent checklist
        code_output (optional) – Code agent execution results

    Output keys added to state:
        signal_classification, hypotheses, causal_chains,
        telemetry_gaps, reasoning_summary
    """
    graph = StateGraph(ReasoningState)

    graph.add_node("classify_signals", classify_signals_node)
    graph.add_node("hypothesise", hypothesise_node)
    graph.add_node("summarise", summarise_node)

    graph.add_edge(START, "classify_signals")
    graph.add_edge("classify_signals", "hypothesise")
    graph.add_edge("hypothesise", "summarise")
    graph.add_edge("summarise", END)

    return graph.compile()