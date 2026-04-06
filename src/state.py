from typing import Optional, TypedDict


class DiagnosticState(TypedDict):
    # Input
    telemetry: str
    service_name: str

    # Main agent instructions
    diagnostic_plan: Optional[str]

    # Instructions from ReasoningAgent to CodingAgent
    coding_task: Optional[str]

    # Coding sub-loop state
    generated_code: Optional[str] # Latest code block produced by Code Generation Agent
    code_execution_history: Optional[list] # [{lang, code, result}, ...] for current session

    # Sub-agent outputs
    sop_guidance: Optional[str]
    code_analysis: Optional[str]
    reasoning_output: Optional[str]

    root_cause_found: bool
    next_action: str

    # Final output
    summary: Optional[str]
    error: Optional[str]

