from __future__ import annotations

import os
from typing import List
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from sop_agent.prompts import SOP_AGENT_SYSTEM_PROMPT
from sop_agent.sop_store import SOPStore, RetrievedSOP


class SOPState(TypedDict):
    telemetry: str
    retrieved_sops: List[dict]  # format: [{"source": "...", "content": "..."}]
    answer: str


def build_sop_graph(sop_dir: str):
    index_dir = os.path.join(sop_dir, ".faiss_index")
    store = SOPStore(sop_dir=sop_dir, index_dir=index_dir)
    store.build_or_load()

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    def retrieve_node(state: SOPState) -> dict:
        query = state["telemetry"]
        hits: List[RetrievedSOP] = store.search(query, k=4)
        return {
            "retrieved_sops": [{"source": h.source, "content": h.content} for h in hits]
        }

    def sop_reasoning_node(state: SOPState) -> dict:
        telemetry = state["telemetry"]
        sops = state.get("retrieved_sops", [])

        sop_context_blocks = []
        for i, s in enumerate(sops, start=1):
            sop_context_blocks.append(
                f"[SOP EXCERPT {i}]\nSOURCE: {s['source']}\n{s['content']}"
            )
        sop_context = "\n\n".join(sop_context_blocks) if sop_context_blocks else "(none)"

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

    graph = StateGraph(SOPState)
    graph.add_node("retrieve_sops", retrieve_node)
    graph.add_node("apply_sops", sop_reasoning_node)

    graph.add_edge(START, "retrieve_sops")
    graph.add_edge("retrieve_sops", "apply_sops")
    graph.add_edge("apply_sops", END)

    return graph.compile()