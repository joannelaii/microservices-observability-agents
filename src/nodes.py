import re

from langchain_core.messages import HumanMessage, SystemMessage

from src.backend import llm_and_embeddings
from .prompts import CODE_GENERATION_AGENT_SYSTEM_PROMPT, MAIN_AGENT_SYSTEM_PROMPT, REASONING_AGENT_SYSTEM_PROMPT, SUMMARISER_SYSTEM_PROMPT
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


# Code Expert Helpers
def _extract_code_block(text: str) -> tuple[str, str] | None:
    """Return (language, code) for the first fenced code block found.

    Recognises python, bash, sh, shell, and plain (no language tag) blocks.
    Returns None if no fenced block is present.
    """
    match = re.search(r'```(python|bash|sh|shell|)\n(.*?)```', text, re.DOTALL | re.IGNORECASE)
    if match:
        lang = match.group(1).lower() or "shell"
        code = match.group(2).strip()
        return lang, code
    return None


def _execute_code(lang: str, code: str) -> str:
    """Execute code and return captured stdout + stderr.

    Both python and shell scripts are run as subprocesses so that a timeout
    applies uniformly — blocking kubectl calls inside generated scripts cannot
    hang the agent forever.
    """
    import subprocess
    import sys as _sys

    timeout = 60  # seconds — generous for multi-step kubectl scripts

    try:
        if lang == "python":
            result = subprocess.run(
                [_sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        else:
            result = subprocess.run(
                code,
                shell=True,  # noqa: S602
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        output = (result.stdout + result.stderr).strip()
        return output if output else "Code executed successfully but produced no output."
    except subprocess.TimeoutExpired:
        return f"Execution error: script timed out after {timeout} seconds."
    except Exception as e:
        return f"Execution error ({type(e).__name__}): {e}"


# Code Generation Node
def run_code_generation_node(state: DiagnosticState) -> DiagnosticState:
    coding_task = state.get("coding_task") or "Analyse the available telemetry and investigate the incident."

    MAX_ITERATIONS = 5

    # Reset history at the start of a new coding session (when Reasoning Agent just routed here)
    history: list = [] if state.get("next_action") == "coding_node" else list(state.get("code_execution_history") or [])

    # Guard: if we've hit the iteration limit, return best-effort insight from history
    if len(history) >= MAX_ITERATIONS:
        summary = f"Reached maximum of {MAX_ITERATIONS} execution steps without a conclusive result. Last result: {history[-1]['result']}"
        print(f"\nCode Generation Agent: max iterations reached, returning best-effort insight.")
        return {**state, "code_analysis": summary, "code_execution_history": [], "next_action": "reasoning_node"}

    history_section = ""
    if history:
        history_section = "\n## Previous Execution Results\n"
        for i, entry in enumerate(history, 1):
            history_section += f"\n### Step {i}\nCode:\n```{entry['lang']}\n{entry['code']}\n```\nResult:\n{entry['result']}\n"

    prompt = "Generate the next script to execute." if history else "Generate the first script to execute."

    messages = [
        SystemMessage(content=CODE_GENERATION_AGENT_SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
            ## Incident Context
            Service: {state["service_name"]}
            Alert / Telemetry: {state["telemetry"]}

            ## SOP Guidance
            {state.get("sop_guidance") or "None"}

            ## Task from Reasoning Agent
            {coding_task}
            {history_section}
            {prompt}
            """
        ),
    ]
    response = llm.invoke(messages)
    content = response.content.strip()

    print("==========Code Generation Agent==========")
    print(f"\nCode Generation Agent response:\n{content}")

    # A code block takes priority — if one is present, always execute it even if INSIGHT also appears
    extracted = _extract_code_block(content)
    if extracted:
        return {**state, "generated_code": content, "code_execution_history": history, "next_action": "code_execution_node"}

    if "INSIGHT:" in content:
        insight = content.split("INSIGHT:", 1)[1].strip()
        print(f"\nCode Generation Agent insight: {insight}")
        return {**state, "code_analysis": insight, "code_execution_history": [], "next_action": "reasoning_node"}

    fallback = f"Code generation produced no executable code or insight. Raw output:\n{content}"
    return {**state, "code_analysis": fallback, "code_execution_history": [], "next_action": "reasoning_node"}


# Code Execution Node
def run_code_execution_node(state: DiagnosticState) -> DiagnosticState:
    generated = state.get("generated_code") or ""
    extracted = _extract_code_block(generated)

    if not extracted:
        result = f"No executable code block found in generated code. Raw:\n{generated}"
        lang, code = "unknown", ""
    else:
        lang, code = extracted
        result = _execute_code(lang, code)

    print("==========Code Execution Agent==========")
    print(f"\nExecuting {lang} code:\n{code}")
    print(f"\nExecution result:\n{result}")

    history = list(state.get("code_execution_history") or [])
    history.append({"lang": lang, "code": code, "result": result})

    return {**state, "code_execution_history": history, "next_action": "code_generation_node"}


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

    # extract coding task to pass to the coding agent for execution
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

