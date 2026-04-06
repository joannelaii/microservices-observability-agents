from langchain_core.messages import HumanMessage, SystemMessage

from common.state import DiagnosticState
from common.util import llm
from .prompts import SYNTHESIS_SYSTEM_PROMPT

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

    response = llm.invoke([
        SystemMessage(content=SYNTHESIS_SYSTEM_PROMPT),
        prompt,
    ])

    diagnosis_text = response.content.strip()

    import json
    diagnosis = json.loads(diagnosis_text)

    print("\n[SYNTHESIS]")
    print(diagnosis, end="\n\n")
    return {
        **state,
        "diagnosis": diagnosis,
        "next_action": "summarizer_node",
    }