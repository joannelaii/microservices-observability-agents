from __future__ import annotations

import os
from typing import Any, TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.tools import tool
from sop_agent.prompts import SOP_AGENT_SYSTEM_PROMPT
from sop_agent.sop_store import SOPStore


class SOPState(TypedDict):
    telemetry: str
    answer: str


def build_sop_graph(sop_dir: str):
    index_dir = os.path.join(sop_dir, ".faiss_index")
    store = SOPStore(sop_dir, index_dir)
    retriever = store.get_retriever(search_kwargs={"k": 4})

    # taken from https://docs.langchain.com/oss/python/langgraph/agentic-rag
    @tool
    def retriever_tool(query: str):
        """retriever tool bound to llm invocations"""
        print(query)
        docs = retriever.invoke(query)
        return "\n\n".join([doc.page_content for doc in docs])

    def sop_reasoning_node(state: SOPState) -> dict[str, Any]:
        telemetry = state["telemetry"]
        user_prompt = f"""\
        Telemetry / symptoms:
        {telemetry}

        Task:
        Produce a numbered debugging checklist strictly based on the SOP excerpts.
        If SOP excerpts are insufficient, ask a maximum of 3 targeted questions to request missing info.
        """

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        messages = [
            SystemMessage(content=SOP_AGENT_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        resp = llm.bind_tools([retriever_tool], tool_choice="any").invoke(messages)
        return {"answer": resp.content}

    APPLY_SOPS = "apply_sops"

    graph = StateGraph(SOPState)
    graph.add_node(APPLY_SOPS, sop_reasoning_node)

    graph.add_edge(START, APPLY_SOPS)
    graph.add_edge(APPLY_SOPS, END)

    return graph.compile()
