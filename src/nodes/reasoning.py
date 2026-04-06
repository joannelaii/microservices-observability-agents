import json
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .prompts import REASONING_AGENT_SYSTEM_PROMPT
from common.state import DiagnosticState
from common.util import llm
from tools.sop import retrieve_sop
from tools.telemetry import get_relevant_telemetry

_REASONING_TOOLS = [retrieve_sop, get_relevant_telemetry]

def run_reasoning_node(state: DiagnosticState) -> DiagnosticState:
    reasoning_messages = list(state.get("reasoning_messages") or [])
    step_count = int(state.get("reasoning_step_count", 0) or 0)
    sop_content = state.get("sop_content") or state.get("sop_guidance") or "No SOP available."

    if not reasoning_messages:
        reasoning_messages = [
            SystemMessage(content=REASONING_AGENT_SYSTEM_PROMPT),
            HumanMessage(
                content=f"""
## Alarm Context
Service reported in alert: {state.get("service_name", "unknown")}
Trace ID from alert: {state.get("trace_id", "N/A")}
Start time: {state.get("start_time", "N/A")}
End time: {state.get("end_time", "N/A")}
Time window: {state.get("time_window", "N/A")}

## Initial Telemetry Snapshot
{state.get("telemetry", "N/A")}

## SOP Document
{sop_content}

## Code Analysis
{state.get("code_analysis", "N/A")}

Use the exact Start time and End time above in any telemetry tool call.
Do not invent timestamps.
"""
            ),
        ]

    reasoning_llm = llm.bind_tools(_REASONING_TOOLS)
    response = reasoning_llm.invoke(reasoning_messages)

    print("tool_calls:", response.tool_calls)

    updates: DiagnosticState = {
        "reasoning_messages": reasoning_messages + [response],
        "reasoning_step_count": step_count + 1,
    }

    if not response.tool_calls:
        text = str(response.content or "")
        updates["reasoning_output"] = text
        upper = text.upper()
        updates["root_cause_found"] = "VERDICT: ROOT_CAUSE_FOUND" in upper

    return updates