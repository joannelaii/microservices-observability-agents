from pydantic import BaseModel
from typing import Annotated, Optional, TypedDict, List, Any
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class IncidentInfo(BaseModel):
    summary: str
    service: str
    when: str

class Diagnosis(BaseModel):
    root_cause_found: bool
    incident: IncidentInfo
    root_cause_status: str
    root_cause: str
    reason: str
    evidence: List[str]
    recommended_actions: List[str]
    next_investigation_steps: List[str]


class DiagnosticState(TypedDict):
    # Input
    messages: List[BaseMessage]
    telemetry: str
    service_name: str
    start_time: Optional[str]
    end_time: Optional[str]
    trace_id: Optional[str]
    time_window: Optional[str]
    alert_payload: Optional[dict[str, Any]]

    # Triage output: structured incident classification
    triage_metadata: Optional[dict[str, Any]]

    # Diagnostic pipeline outputs
    diagnostic_plan: Optional[str]
    sop_guidance: Optional[str]
    sop_content: Optional[str]
    coding_task: Optional[str]
    code_analysis: Optional[str]
    reasoning_output: Optional[str]

    # reasoning
    diagnosis: Optional[dict[str, Any]]
    reasoning_messages: Annotated[list[BaseMessage], add_messages]
    reasoning_step_count: int
    root_cause_found: bool
    next_action: str

    # Final output
    best_effort: Optional[str]
    summary: Optional[Diagnosis]
    error: Optional[str]

