from typing import List
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from common.backend import llm_and_embeddings
from common.state import DiagnosticState, Diagnosis
from .prompts import SUMMARISER_SYSTEM_PROMPT

llm = llm_and_embeddings()["llm"]

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
    model = llm.with_structured_output(Diagnosis, method="json_schema")
    response = model.invoke(messages)
    print("[Summariser]\n")
    return {**state, "summary": response}