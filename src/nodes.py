from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from src.backend import llm_and_embeddings
from src.tools.k8s import K8S_TOOLS
from .prompts import CODING_AGENT_SYSTEM_PROMPT, MAIN_AGENT_SYSTEM_PROMPT, REASONING_AGENT_SYSTEM_PROMPT, SUMMARISER_SYSTEM_PROMPT
from .state import DiagnosticState
from dotenv import load_dotenv

load_dotenv()

llm = llm_and_embeddings()["llm"]


def run_main_agent_node(state: DiagnosticState) -> DiagnosticState:
    def check_for_key(key: str):
        return "AVAILABLE" if state.get(key) else "NOT YET GATHERED"

    messages = [
        SystemMessage(content=MAIN_AGENT_SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
        Telemetry: {state["telemetry"]}
        Service: {state["service_name"]}

        ## Current State of Investigation
        SOP Guidance:     {check_for_key("sop_guidance")}
        Code Analysis:    {check_for_key("code_analysis")}
        Reasoning Output: {check_for_key("reasoning_output")}

        ## Latest Outputs
        SOP Guidance: {state.get("sop_guidance", "None")}
        Code Analysis: {state.get("code_analysis", "None")}
        Reasoning: {state.get("reasoning_output", "None")}

        Based on the above, what is the next action?
        """
        ),
    ]
    result = llm.invoke(messages)
    next_action = result.content.strip().split("\n")[0].strip()
    print("==========Main Agent==========")
    print(f"\nMain Agent full response:\n {result.content}")

    return {**state, "diagnostic_plan": result.content, "next_action": next_action}


def triage_node(state: DiagnosticState) -> DiagnosticState:
    """
    triages the incident, should not be LLM
    """
    # TODO: add tool call for SOP retrieval
    return {**state, "tool_call": "STUB: Code expert not yet implemented"}


# SOP Node
# def run_sop_node(state: DiagnosticState) -> DiagnosticState:
#     # Call SOP agent via shared helper
#     sop_dir = os.path.join(os.path.dirname(__file__), "..", "..", "sop-agent", "sops")
#     sop_dir = os.path.abspath(sop_dir)
#
#     result = run_sop_agent(telemetry=state["telemetry"], sop_dir=sop_dir)
#     print("==========SOP Agent==========")
#     print(f"\nSOP Agent returned:\n {result.get('answer', '')}")
#     return {**state, "sop_guidance": result.get("answer", "")}


# Coding Agent Node
def run_coding_agent_node(state: DiagnosticState) -> DiagnosticState:
    coding_task = state.get("coding_task") or "Investigate the incident using the available tools."
    MAX_ITERATIONS = 8

    tool_map = {t.name: t for t in K8S_TOOLS}
    llm_with_tools = llm.bind_tools(K8S_TOOLS)

    messages = [
        SystemMessage(content=CODING_AGENT_SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
            ## Incident Context
            Service: {state["service_name"]}
            Alert / Telemetry: {state["telemetry"]}

            ## SOP Guidance
            {state.get("sop_guidance") or "None"}

            ## Task from Reasoning Agent
            {coding_task}
            """
        ),
    ]

    iteration = 0
    while iteration < MAX_ITERATIONS:
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        print(f"==========Coding Agent (iteration {iteration + 1})==========")

        if not response.tool_calls:
            final_text = response.content.strip()
            print(f"Final analysis:\n{final_text}")
            return {**state, "code_analysis": final_text, "next_action": "reasoning_node"}

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            print(f"Tool call: {tool_name}({tool_args})")
            if tool_name not in tool_map:
                tool_result = f"Unknown tool: {tool_name}"
            else:
                try:
                    tool_result = tool_map[tool_name].invoke(tool_args)
                except Exception as e:
                    tool_result = f"Tool error ({type(e).__name__}): {e}"

            print(f"Tool result:\n{tool_result}\n")
            messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_id))

        iteration += 1

    fallback = f"Reached maximum of {MAX_ITERATIONS} tool call rounds without a conclusive result. Last tool result: {messages[-1].content}"
    print("Coding Agent: max iterations reached.")
    return {**state, "code_analysis": fallback, "next_action": "reasoning_node"}


# Reasoning Node
def run_reasoning_node(state: DiagnosticState) -> DiagnosticState:
    messages = [
        SystemMessage(content=REASONING_AGENT_SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
            ## Incident
            Service: {state["service_name"]}
            Alert / Telemetry: {state["telemetry"]}

            ## Evidence Gathered
            SOP Guidance:
            {state.get("sop_guidance") or "Not yet gathered"}

            Code Analysis:
            {state.get("code_analysis") or "Not yet gathered"}

            Decide the next step to be carried out based on the information gathered so far.
            """
        ),
    ]
    response = llm.invoke(messages)
    content = response.content.strip()

    next_action = content.split("\n")[0].strip()

    # extract coding task
    coding_task = None
    if "CODING TASK:" in content:
        coding_task = content.split("CODING TASK:", 1)[1].strip()

    print("==========Reasoning Agent==========")
    print(f"\nReasoning Agent response:\n{content}")

    return {
        **state,
        "reasoning_output": content,
        "next_action": next_action,
        "coding_task": coding_task,
    }


# Summariser Node
def run_summariser_node(state: DiagnosticState) -> DiagnosticState:
    messages = [
        SystemMessage(content=SUMMARISER_SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
        Telemetry: {state["telemetry"]}\n
        Service: {state["service_name"]}\n

        SOP Agent:\n
        {state.get("sop_guidance", "N/A")}\n

        Code Expert:\n
        {state.get("code_analysis", "N/A")}\n

        Reasoning Agent:\n
        {state.get("reasoning_output", "N/A")}\n
            """
        ),
    ]
    response = llm.invoke(messages)
    print("==========Summariser Agent==========")
    print(f"\nSummariser Agent returned:\n {response.content}")
    return {**state, "summary": response.content}


# TODO: implement this function
def run_best_effort_node(state: DiagnosticState) -> DiagnosticState:
    return {**state, "best_effort": "STUB: best_effort_node not yet implemented"}
