from typing import Optional, TypedDict

class MainAgentState(TypedDict):
    # Input
    alert: str
    service_name: str

    # Main agent instructions
    diagnostic_plan: Optional[str]
    
    # Sub-agent outputs
    sop_guidance: Optional[str]
    code_analysis: Optional[str]
    reasoning_output: Optional[str]

    # Final output
    summary: Optional[str]
    error: Optional[str]