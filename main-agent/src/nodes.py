from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from .state import DiagnosticState
from sop_agent.graph import build_sop_graph
import os

llm = ChatOpenAI(model="gpt-4o", temperature=0)

def run_main_agent_node(state: DiagnosticState) -> DiagnosticState:
    messages = [
        SystemMessage(content="""You are the main orchestrating agent for a 
        microservices diagnostic system. When given telemetry and an alert:
        1. Analyse what kind of problem this is
        2. Identify which services/components are affected
        3. Decide what information is needed to diagnose it
        Output a clear diagnostic plan that will guide the specialist agents."""),
        HumanMessage(content=f"""
        Alert: {state['alert']}
        Service: {state['service_name']}
        What is your diagnostic plan?
        """)
    ]
    result = llm.invoke(messages)
    return {**state, "diagnostic_plan": result.content}

# SOP Node
def run_sop_node(state: DiagnosticState) -> DiagnosticState:
    # Call SOP agent
    sop_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "sop-agent", "sops")
    sop_dir = os.path.abspath(sop_dir)

    sop_graph = build_sop_graph(sop_dir=sop_dir)
    result = sop_graph.invoke({
        "telemetry": state["alert"],
        "retrieved_sops": [],
        "answer": ""
    })
    return {**state, "sop_guidance": result["answer"]}

# Code Expert Node, change to use code expert agent when implemented
def run_code_expert_node(state: DiagnosticState) -> DiagnosticState:
    messages = []
    response = llm.invoke(messages)
    return {**state, "code_analysis": response.content}

# Reasoning Node, change to use reasoning agent when implemented
def run_reasoning_node(state: DiagnosticState) -> DiagnosticState:
    messages = []
    response = llm.invoke(messages)
    return {**state, "reasoning_output": response.content}

# Summariser Node
def run_summariser_node(state: DiagnosticState) -> DiagnosticState:
    messages = [
        SystemMessage(content="""You are the main diagnostic agent for a microservices
        observability system. Synthesise inputs from specialist agents into a clear,
        actionable incident report for an on-call engineer.
        Structure: 1) Summary  2) Root Cause  3) Recommended Actions  4) Prevention"""),
        HumanMessage(content=f"""
        Alert: {state['alert']}
        Service: {state['service_name']}

        SOP Agent:
        {state.get('sop_guidance', 'N/A')}

        Code Expert:
        {state.get('code_analysis', 'N/A')}

        Reasoning Agent:
        {state.get('reasoning_output', 'N/A')}
            """)
    ]
    response = llm.invoke(messages)
    return {**state, "summary": response.content}