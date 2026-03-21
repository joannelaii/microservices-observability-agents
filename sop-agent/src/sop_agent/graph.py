from __future__ import annotations

import os
from typing import Any, TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage
from sop_agent.backend import llm_and_embeddings
from sop_agent.prompts import SOP_AGENT_SYSTEM_PROMPT
from sop_agent.sop_store import SOPStore, RetrievedSOP


class SOPState(TypedDict):
    telemetry: str
    retrieved_sops: list[
        dict[str, str]
    ]  # format: [{"source": "...", "content": "..."}]
    answer: str


def build_sop_graph(sop_dir: str):
    index_dir = os.path.join(sop_dir, ".faiss_index")

    config = llm_and_embeddings()
    embeddings = config["embeddings"]
    llm = config["llm"]
    store = SOPStore(embeddings, sop_dir=sop_dir, index_dir=index_dir)

    def retrieve_node(state: SOPState) -> dict[str, list[dict[str, str]]]:
        query = state["telemetry"]
        hits = store.search(query, k=4)
        return {"retrieved_sops": [dict(h) for h in hits]}

    def sop_reasoning_node(state: SOPState) -> dict[str, Any]:
        telemetry = state["telemetry"]
        sops = state["retrieved_sops"]

        sop_context_blocks = [
            f"[SOP EXCERPT {i}]\nSOURCE: {s['source']}\n{s['content']}"
            for i, s in enumerate(sops, start=1)
        ]
        sop_context = (
            "\n\n".join(sop_context_blocks) if sop_context_blocks else "(none)"
        )

        user_prompt = f"""\
        Telemetry / symptoms:
        {telemetry}

        Relevant SOP excerpts:
        {sop_context}

        Task:
        Produce a numbered debugging checklist strictly based on the SOP excerpts.
        If SOP excerpts are insufficient, ask a maximum of 3 targeted questions to request missing info.
        """

        messages = [
            SystemMessage(content=SOP_AGENT_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        resp = llm.invoke(messages)
        return {"answer": resp.content}

    RETRIEVE_SOPS = "retrieve_sops"
    APPLY_SOPS = "apply_sops"

    graph = StateGraph(SOPState)
    graph.add_node(RETRIEVE_SOPS, retrieve_node)
    graph.add_node(APPLY_SOPS, sop_reasoning_node)

    graph.add_edge(START, RETRIEVE_SOPS)
    graph.add_edge(RETRIEVE_SOPS, APPLY_SOPS)
    graph.add_edge(APPLY_SOPS, END)

    return graph.compile()
