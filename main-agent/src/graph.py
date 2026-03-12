from langgraph.graph import StateGraph, START, END
from .state import DiagnosticState
from .nodes import (
    run_main_agent_node,
    run_sop_node,
    run_code_expert_node,
    run_reasoning_node,
    run_summariser_node
)

def build_graph() -> StateGraph:
    graph = StateGraph(DiagnosticState)

    # Add nodes
    graph.add_node("main", run_main_agent_node)
    graph.add_node("sop_agent", run_sop_node)
    graph.add_node("code_expert", run_code_expert_node)
    graph.add_node("reasoning", run_reasoning_node)
    graph.add_node("summariser", run_summariser_node)

    # Adjust flow accordingly
    graph.add_edge(START, "main")
    graph.add_edge("main", "sop_agent")
    graph.add_edge("sop_agent",   "code_expert")
    graph.add_edge("code_expert", "reasoning")
    graph.add_edge("reasoning",   "summariser")
    graph.add_edge("summariser",  END)

    return graph.compile()
