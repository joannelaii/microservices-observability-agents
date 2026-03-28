from langchain_core.messages import HumanMessage, SystemMessage

from src.backend import llm_and_embeddings
from .prompts import CODING_AGENT_SYSTEM_PROMPT, MAIN_AGENT_SYSTEM_PROMPT, REASONING_AGENT_SYSTEM_PROMPT, SUMMARISER_SYSTEM_PROMPT
from .state import DiagnosticState
import os
from dotenv import load_dotenv

load_dotenv()

llm = llm_and_embeddings()["llm"]


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


# Code Expert Node
def run_code_expert_node(state: DiagnosticState) -> DiagnosticState:
    coding_task = state.get("coding_task") or "Analyse the available telemetry and write a focused diagnostic script."

    messages = [
        SystemMessage(content=CODING_AGENT_SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
            ## Incident Context
            Service: {state["service_name"]}
            Alert / Telemetry: {state["telemetry"]}

            ## SOP Guidance
            {state.get("sop_guidance") or "None"}

            ## Task from Reasoning Agent
            {coding_task}

            Write the Python code (e.g. function/script) required to accomplish this task.
            """
        ),
    ]
    response = llm.invoke(messages)
    print("==========Code Expert==========")
    print(f"\nCode Expert response:\n{response.content}")
    return {**state, "code_analysis": response.content}


# Reasoning Node
def run_reasoning_node(state: DiagnosticState) -> DiagnosticState:
    messages = [
        SystemMessage(content=REASONING_AGENT_SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
            ## Incident
            Service: {state["service_name"]}
            Alert / Telemetry: {state["telemetry"]}

            ## Evidence Gathered
            SOP Guidance:
            {state.get("sop_guidance") or "Not yet gathered"}

            Code Analysis:
            {state.get("code_analysis") or "Not yet gathered"}

            Decide the next step to be carried out based on the information gathered so far.
            """
        ),
    ]
    response = llm.invoke(messages)
    content = response.content.strip()

    next_action = content.split("\n")[0].strip()

    # extract coding task to pass to the coding agent for execution
    coding_task = None
    if "CODING TASK:" in content:
        coding_task = content.split("CODING TASK:", 1)[1].strip()

    print("==========Reasoning Agent==========")
    print(f"\nReasoning Agent response:\n{content}")

    return {
        **state,
        "reasoning_output": content,
        "next_action": next_action,
        "coding_task": coding_task,
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


# TODO: implement this function
def run_best_effort_node(state: DiagnosticState) -> DiagnosticState:
    return {**state, "best_effort": "STUB: best_effort_node not yet implemented"}

