from __future__ import annotations
 
import json
from typing import Any, Dict, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.backend import llm_and_embeddings
from src.tools.sop import retrieve_sop
from src.tools.telemetry import get_relevant_telemetry
from .prompts import MAIN_AGENT_SYSTEM_PROMPT, REASONING_AGENT_SYSTEM_PROMPT, SUMMARISER_SYSTEM_PROMPT
from .state import DiagnosticState
import os
from dotenv import load_dotenv

load_dotenv()

llm = llm_and_embeddings()["llm"]

_REASONING_TOOLS = [retrieve_sop, get_relevant_telemetry]
 
# cap on tool-call round trips
_MAX_ITERATIONS = 6

def run_main_agent_node(state: DiagnosticState) -> DiagnosticState:
    def check_for_key(key: str):
        return "AVAILABLE" if state.get(key) else "NOT YET GATHERED"

    messages = [
        SystemMessage(content=MAIN_AGENT_SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
        Telemetry: {state["telemetry"]}
        Service: {state["service_name"]}

        ## Current State of Investigation
        SOP Guidance:     {check_for_key("sop_guidance")}
        Code Analysis:    {check_for_key("code_analysis")}
        Reasoning Output: {check_for_key("reasoning_output")}

        ## Latest Outputs
        SOP Guidance: {state.get("sop_guidance", "None")}
        Code Analysis: {state.get("code_analysis", "None")}
        Reasoning: {state.get("reasoning_output", "None")}

        Based on the above, what is the next action?
        """
        ),
    ]
    result = llm.invoke(messages)
    next_action = result.content.strip().split("\n")[0].strip()
    print("==========Main Agent==========")
    print(f"\nMain Agent full response:\n {result.content}")

    return {**state, "diagnostic_plan": result.content, "next_action": next_action}


def triage_node(state: DiagnosticState) -> DiagnosticState:
    """
    triages the incident, should not be LLM
    """
    # TODO: add tool call for SOP retrieval
    return {**state, "tool_call": "STUB: Code expert not yet implemented"}


# SOP Node
# def run_sop_node(state: DiagnosticState) -> DiagnosticState:
#     # Call SOP agent via shared helper
#     sop_dir = os.path.join(os.path.dirname(__file__), "..", "..", "sop-agent", "sops")
#     sop_dir = os.path.abspath(sop_dir)
#
#     result = run_sop_agent(telemetry=state["telemetry"], sop_dir=sop_dir)
#     print("==========SOP Agent==========")
#     print(f"\nSOP Agent returned:\n {result.get('answer', '')}")
#     return {**state, "sop_guidance": result.get("answer", "")}


# Code Expert Node, change to use code expert agent when implemented
def run_code_expert_node(state: DiagnosticState) -> DiagnosticState:
    # messages = []
    # response = llm.invoke(messages)
    # return {**state, "code_analysis": response.content}
    print("==========Code Expert==========")
    # print(f"Code Generated:\n {response.content}")
    return {**state, "code_analysis": "STUB: Code expert not yet implemented"}


def run_reasoning_node(state: DiagnosticState) -> DiagnosticState:
    """
    Agentic reasoning loop. Receives the SOP document and initial telemetry
    snapshot, then iteratively calls get_relevant_telemetry to:
      1. Identify candidate services via a broad namespace-wide sweep.
      2. Drill into each suspicious service to validate the SOP checks.
      3. Optionally follow trace IDs for a span-level deep-dive.
 
    Emits either VERDICT: ROOT_CAUSE_FOUND or VERDICT: BEST_EFFORT and
    sets next_action accordingly for the graph router.
    """
    print("==========Reasoning Agent==========")
 
    # SOP content is stored on state by whichever node populated it.
    sop_content = state.get("sop_content") or state.get("sop_guidance") or "No SOP available."

    system_msg = SystemMessage(content=REASONING_AGENT_SYSTEM_PROMPT)
    initial_human = HumanMessage(
        content=f"""
            ## Alarm Context
            Service reported in alert: {state.get("service_name", "unknown")}
            
            ## Initial Telemetry Snapshot (namespace-wide, at alarm time)
            {state.get("telemetry", "N/A")}
            
            ## SOP Document
            {sop_content}
            
            ## Code Analysis (if available)
            {state.get("code_analysis", "N/A")}
            
            Follow the investigation protocol. Call get_relevant_telemetry as needed,
            then write your VERDICT once you have enough evidence.
        """
    )
 
    messages: List[Any] = [system_msg, initial_human]

    reasoning_llm = llm.bind_tools(_REASONING_TOOLS)
    tool_map = {t.name: t for t in _REASONING_TOOLS}

    # tool-use loop
    verdict_text = ""
    iterations = 0
 
    while iterations < _MAX_ITERATIONS:
        iterations += 1
        print(f"  [Reasoning] iteration {iterations}")
 
        response: AIMessage = reasoning_llm.invoke(messages)
        messages.append(response)
 
        tool_calls: List[Dict[str, Any]] = getattr(response, "tool_calls", None) or []
 
        if not tool_calls:
            # no tool calls — it has written its conclusion
            verdict_text = response.content
            break
 
        # execute requested tool call and feed results back
        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("args", {})
            print(f"  [Reasoning] → {name}({list(args.keys())})")
            try:
                result = tool_map[name].invoke(args)
                tool_result = json.dumps(result, default=str)
            except Exception as exc:
                tool_result = json.dumps({"error": str(exc)})
 
            messages.append(
                ToolMessage(content=tool_result, tool_call_id=tc["id"])
            )
 
    else:
        # hit iteration cap
        messages.append(
            HumanMessage(
                content=(
                    "You have reached the maximum number of tool calls. "
                    "Write your VERDICT now based on the evidence gathered so far. "
                    "Use VERDICT: BEST_EFFORT if the evidence is insufficient."
                )
            )
        )
        final_response: AIMessage = reasoning_llm.invoke(messages)
        verdict_text = final_response.content
        messages.append(final_response)
 
    print(f"\nReasoning Agent verdict:\n{verdict_text}\n")

    # set graph routing fields

    upper = verdict_text.upper()
    root_cause_found = "VERDICT: ROOT_CAUSE_FOUND" in upper
 
    # TODO: edit if there is a new summariser node, if not then remove the next action for root cause found together with dianosis node
    if root_cause_found:
        next_action = "synthesize_diagnosis"
    else:
        next_action = "synthesize_best_effort"
 
    return {
        **state,
        "reasoning_output": verdict_text,
        "root_cause_found": root_cause_found,
        "next_action": next_action,
    }

# Summariser Node
def run_summariser_node(state: DiagnosticState) -> DiagnosticState:
    messages = [
        SystemMessage(content=SUMMARISER_SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
        Telemetry: {state["telemetry"]}\n
        Service: {state["service_name"]}\n

        SOP Agent:\n
        {state.get("sop_guidance", "N/A")}\n

        Code Expert:\n
        {state.get("code_analysis", "N/A")}\n

        Reasoning Agent:\n
        {state.get("reasoning_output", "N/A")}\n
            """
        ),
    ]
    response = llm.invoke(messages)
    print("==========Summariser Agent==========")
    print(f"\nSummariser Agent returned:\n {response.content}")
    return {**state, "summary": response.content}


def run_best_effort_node(state: DiagnosticState) -> DiagnosticState:
    """
    Called when the reasoning agent could not identify a definitive root cause.
    Extracts the best-effort hypothesis and next investigation steps from the
    reasoning output and stores them on state for the summariser.
    """
    print("==========Best Effort Node==========")
 
    reasoning = state.get("reasoning_output", "No reasoning output available.")
 
    messages = [
        SystemMessage(
            content=(
                "You are a concise technical writer for an incident-response system. "
                "Given an inconclusive investigation, extract and clearly restate:\n"
                "  1. The most likely hypothesis for what caused the issue.\n"
                "  2. Concrete next investigation steps that would confirm or rule it out.\n\n"
                "Format your output exactly as:\n\n"
                "HYPOTHESIS:\n<paragraph>\n\n"
                "NEXT INVESTIGATION STEPS:\n1. <step>\n2. <step>\n..."
            )
        ),
        HumanMessage(
            content=f"""
                Reasoning agent output:
                {reasoning}
                
                Service: {state.get("service_name", "unknown")}
                Initial telemetry snapshot: {state.get("telemetry", "N/A")}
            """
        ),
    ]
    response = llm.invoke(messages)
    print(f"\nBest effort output:\n{response.content}")
 
    return {**state, "best_effort": response.content}