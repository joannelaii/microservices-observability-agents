from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from .prompts import MAIN_AGENT_SYSTEM_PROMPT, SUMMARISER_SYSTEM_PROMPT
from .state import DiagnosticState
from run_sop_agent import run_sop_agent
import os
from dotenv import load_dotenv

load_dotenv()
    
llm = ChatOpenAI(model="gpt-4o", temperature=0)

def run_main_agent_node(state: DiagnosticState) -> DiagnosticState:
    messages = [
        SystemMessage(content=MAIN_AGENT_SYSTEM_PROMPT),
        HumanMessage(content=f"""
        Telemetry: {state['telemetry']}
        Service: {state['service_name']}

        ## Current State of Investigation
        SOP Guidance:     {'AVAILABLE' if state.get('sop_guidance')     else 'NOT YET GATHERED'}
        Code Analysis:    {'AVAILABLE' if state.get('code_analysis')    else 'NOT YET GATHERED'}
        Reasoning Output: {'AVAILABLE' if state.get('reasoning_output') else 'NOT YET GATHERED'}

        ## Latest Outputs
        SOP Guidance: {state.get('sop_guidance', 'None')}
        Code Analysis: {state.get('code_analysis', 'None')}
        Reasoning: {state.get('reasoning_output', 'None')}

        Based on the above, what is the next action?
        """)
    ]
    result = llm.invoke(messages)
    next_action = result.content.strip().split("\n")[0].strip()
    print("==========Main Agent==========")
    print(f"\nMain Agent full response:\n {result.content}")

    return {
        **state,
        "diagnostic_plan": result.content,
        "next_action": next_action
    }

# SOP Node
def run_sop_node(state: DiagnosticState) -> DiagnosticState:
    # Call SOP agent via shared helper
    sop_dir = os.path.join(os.path.dirname(__file__), "..", "..", "sop-agent", "sops")
    sop_dir = os.path.abspath(sop_dir)

    result = run_sop_agent(telemetry=state["telemetry"], sop_dir=sop_dir)
    print("==========SOP Agent==========")
    print(f"\nSOP Agent returned:\n {result.get('answer', '')}")
    return {**state, "sop_guidance": result.get("answer", "")}

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
    return {**state, "reasoning_output": "STUB: Reasoning agent not yet implemented", "root_cause_found": True}

# Summariser Node
def run_summariser_node(state: DiagnosticState) -> DiagnosticState:
    messages = [
        SystemMessage(content=SUMMARISER_SYSTEM_PROMPT),
        HumanMessage(content=f"""
        Telemetry: {state['telemetry']}\n
        Service: {state['service_name']}\n

        SOP Agent:\n
        {state.get('sop_guidance', 'N/A')}\n

        Code Expert:\n
        {state.get('code_analysis', 'N/A')}\n

        Reasoning Agent:\n
        {state.get('reasoning_output', 'N/A')}\n
            """)
    ]
    response = llm.invoke(messages)
    print("==========Summariser Agent==========")
    print(f"\nSummariser Agent returned:\n {response.content}")
    return {**state, "summary": response.content}