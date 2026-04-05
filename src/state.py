from typing import Optional, TypedDict, List, Any
from langchain_core.messages import BaseMessage


class DiagnosticState(TypedDict):
    # Input
    messages: List[BaseMessage]
    telemetry: str
    service_name: str
    start_time: Optional[str]
    trace_id: Optional[str]
    time_window: Optional[str]
    alert_payload: Optional[dict[str, Any]]

    # Triage output: structured incident classification
    triage_metadata: Optional[dict[str, Any]]

    # Diagnostic pipeline outputs
    diagnostic_plan: Optional[str]
    sop_guidance: Optional[str]
    sop_content: Optional[str]
    code_analysis: Optional[str]
    reasoning_output: Optional[str]

    root_cause_found: bool
    next_action: str

    # Final output
    best_effort: Optional[str]
    summary: Optional[str]
    error: Optional[str]

