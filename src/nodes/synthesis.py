from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from common.state import DiagnosticState
from common.util import llm, usage_update
from .prompts import SYNTHESIS_SYSTEM_PROMPT


class Synthesis(BaseModel):
    status: str
    service: str | None
    root_cause: str
    evidence: list[str]
    uncertainties: list[str]
    next_steps: list[str]


def run_synthesis_node(state: DiagnosticState) -> DiagnosticState:
    reasoning_output = state.get("reasoning_output") or ""
    service_name = state.get("service_name")
    root_cause_found = state.get("root_cause_found", False)

    prompt = HumanMessage(
        content=f"""
Service from alert: {service_name}
Root cause found flag: {root_cause_found}
Start Time: {state.get("start_time", "")}
End Time: {state.get("end_time", "")}

Reasoning verdict:
{reasoning_output}

Convert this into the required JSON schema.
"""
    )

    synthesis_model = llm.with_structured_output(Synthesis, include_raw=True)
    response = synthesis_model.invoke([
        SystemMessage(content=SYNTHESIS_SYSTEM_PROMPT),
        prompt,
    ])
    diagnosis = response["parsed"].model_dump()
    raw_response = response["raw"]

    print("\n[SYNTHESIS]")
    print(diagnosis, end="\n\n")
    return {
        **state,
        "diagnosis": diagnosis,
        "next_action": "summarizer_node",
        **usage_update(state, raw_response),
    }
