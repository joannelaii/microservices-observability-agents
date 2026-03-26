from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from src.backend import llm_and_embeddings
from .prompts import MAIN_AGENT_SYSTEM_PROMPT, SUMMARISER_SYSTEM_PROMPT
from .state import DiagnosticState
import os
from dotenv import load_dotenv
import uuid

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
    Triage logic to route between two flows:
    1) Alarm-based: has telemetry -> call SOP_TOOL
    2) User trace-id: has trace_id -> call TELEMETRY_TOOL to fetch relevant data
    """
    # Flow 1: User provided trace_id -> fetch telemetry for that trace
    if state.get("trace_id") and state["trace_id"] is not None:
        tool_call = {
            "id": str(uuid.uuid4()),
            "name": "get_relevant_telemetry",
            "args": {"trace_id": state["trace_id"]}
        }
        print("==========Triage: TRACE_ID Flow==========\n")
        return {
            **state,
            "messages": state["messages"] + [AIMessage(content="", tool_calls=[tool_call])],
            "triage": "telemetry_tool"
        }
    
    # Flow 2: Alarm triggered -> retrieve relevant SOP by telemetry
    last_message = state["messages"][-1]
    query = last_message.content if hasattr(last_message, 'content') else str(last_message)
    tool_call = {
        "id": str(uuid.uuid4()),
        "name": "retrieve_sop",
        "args": {"query": query}
    }
    print("==========Triage: ALARM Flow==========\n")
    return {
        **state,
        "messages": state["messages"] + [AIMessage(content="", tool_calls=[tool_call])],
        "triage": "sop_tool"
    }


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


# Reasoning Node, change to use reasoning agent when implemented
def run_reasoning_node(state: DiagnosticState) -> DiagnosticState:
    # messages = []
    # response = llm.invoke(messages)
    # return {**state, "reasoning_output": response.content}
    print("==========Reasoning Agent==========")
    # print(f"Reasoning Agent returned:\n {response.content}")
    # TODO: Bind tool call to llm invoke
    return {
        **state,
        "reasoning_output": "STUB: Reasoning agent not yet implemented",
        "root_cause_found": True,
        # Hard coded next action for testing but I think there needs to be some logic here to decide what the next action is since the graph uses a route_next function to determine the next node
        "next_action": "synthesize_diagnosis",
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

