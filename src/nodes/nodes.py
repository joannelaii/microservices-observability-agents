from __future__ import annotations
 
import json
from typing import Any, Dict, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from common.backend import llm_and_embeddings
from tools.k8s import K8S_TOOLS
from common.state import DiagnosticState
from common.util import usage_from_response
from dotenv import load_dotenv
from .prompts import SUMMARISER_SYSTEM_PROMPT, CODING_AGENT_SYSTEM_PROMPT

load_dotenv()

llm = llm_and_embeddings()["llm"]


# Coding Agent Node
def run_coding_agent_node(state: DiagnosticState) -> DiagnosticState:
    print("\n[CODING]\n")
    coding_task = state.get("coding_task") or "Investigate the incident using the available tools."
    MAX_ITERATIONS = 8
    step_count = int(state.get("reasoning_step_count", 0) or 0)
    input_tokens = int(state.get("meta_input_tokens", 0) or 0)
    output_tokens = int(state.get("meta_output_tokens", 0) or 0)
    total_tokens = int(state.get("meta_total_tokens", 0) or 0)

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
        usage = usage_from_response(response)
        input_tokens += usage["input_tokens"]
        output_tokens += usage["output_tokens"]
        total_tokens += usage["total_tokens"]
        messages.append(response)

        print(f"==========Coding Agent (iteration {iteration + 1})==========")

        if not response.tool_calls:
            final_text = response.content.strip()
            print(f"Final analysis:\n{final_text}")
            return {
                **state,
                "code_analysis": final_text,
                "coding_task": None,
                "reasoning_step_count": step_count + 1,
                "meta_input_tokens": input_tokens,
                "meta_output_tokens": output_tokens,
                "meta_total_tokens": total_tokens,
            }

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
    return {
        **state,
        "code_analysis": fallback,
        "coding_task": None,
        "reasoning_step_count": step_count + 1,
        "meta_input_tokens": input_tokens,
        "meta_output_tokens": output_tokens,
        "meta_total_tokens": total_tokens,
    }
