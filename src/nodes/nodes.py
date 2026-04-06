from __future__ import annotations
 
import json
from typing import Any, Dict, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from common.backend import llm_and_embeddings
from common.state import DiagnosticState
from dotenv import load_dotenv
from .prompts import SUMMARISER_SYSTEM_PROMPT

load_dotenv()

llm = llm_and_embeddings()["llm"]


# Code Expert Node, change to use code expert agent when implemented
def run_code_expert_node(state: DiagnosticState) -> DiagnosticState:
    # messages = []
    # response = llm.invoke(messages)
    # return {**state, "code_analysis": response.content}
    print("==========Code Expert==========")
    # print(f"Code Generated:\n {response.content}")
    return {**state, "code_analysis": "STUB: Code expert not yet implemented"}


# Summariser Node
def run_summariser_node(state: DiagnosticState) -> DiagnosticState:
    """
    Produces a conditional summary based on whether root cause was found.
    - If root_cause_found=True: produces a 4-section structured incident report
    - If root_cause_found=False: states root cause is inconclusive and lists best-effort findings
    """
    root_cause_found = state.get("root_cause_found", False)
    reasoning_output = state.get("reasoning_output", "No reasoning output available.")
    triage_metadata = state.get("triage_metadata", {})
    
    # Build the user message with explicit context about the verdict
    verdict_flag = "TRUE" if root_cause_found else "FALSE"
    
    user_content = f"""
ROOT_CAUSE_FOUND = {verdict_flag}

Incident Type: {triage_metadata.get('incident_type', 'unknown')}
Severity: {triage_metadata.get('severity', 'unknown')}

Reasoning Agent Output:
{reasoning_output}

Based on the ROOT_CAUSE_FOUND flag above, format your response according to the instructions in the system prompt.
    """
    
    messages = [
        SystemMessage(content=SUMMARISER_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
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
