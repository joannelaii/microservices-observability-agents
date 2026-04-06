import json
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .prompts import REASONING_AGENT_SYSTEM_PROMPT
from common.state import DiagnosticState
from common.util import llm
from tools.sop import retrieve_sop
from tools.telemetry import get_relevant_telemetry


_REASONING_TOOLS = [retrieve_sop, get_relevant_telemetry]
_MAX_ITERATIONS = 6

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
            print(f"  [Reasoning] → {name}({args})")
            try:
                result = tool_map[name].invoke(args)
                tool_result = json.dumps(result, default=str)
            except Exception as exc:
                tool_result = json.dumps({"error": str(exc)})
 
            # print(f"  [Reasoning] ← {tool_result}")
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

    return {
        **state,
        "reasoning_output": verdict_text,
        "root_cause_found": root_cause_found,
        "next_action": "synthesis_node",
    }