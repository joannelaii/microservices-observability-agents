from typing import Optional, TypedDict, List
from langchain_core.messages import BaseMessage


class DiagnosticState(TypedDict):
    # Input messages
    messages: List[BaseMessage]

    # Input (Alert)
    telemetry: str
    service_name: str

    # Input (Trace ID)
    trace_id: Optional[str]

    # Main agent instructions
    diagnostic_plan: Optional[str]

    # Sub-agent outputs
    sop_guidance: Optional[str]
    code_analysis: Optional[str]
    reasoning_output: Optional[str]

    root_cause_found: bool
    next_action: str
    triage: str

    # Final output
    summary: Optional[str]
    error: Optional[str]

