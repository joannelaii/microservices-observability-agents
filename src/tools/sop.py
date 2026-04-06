from __future__ import annotations

import os
from typing import TypedDict

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_core.tools import tool
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

from common.backend import llm_and_embeddings

load_dotenv()


class RetrievedSOP(TypedDict):
    source: str
    content: str


class SOPStore:
    _vs: FAISS

    def __init__(self, embeddings: Embeddings, sop_dir: str, index_dir: str) -> None:
        os.makedirs(index_dir, exist_ok=True)
        index_file = os.path.join(index_dir, "index.faiss")
        store_file = os.path.join(index_dir, "index.pkl")

        if os.path.exists(index_file) and os.path.exists(store_file):
            self._vs = FAISS.load_local(
                index_dir,
                embeddings,
                allow_dangerous_deserialization=True,
            )
            return

        loader = DirectoryLoader(
            sop_dir,
            glob="*.md",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
        )
        docs = loader.load()

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1200,
            chunk_overlap=150,
        )
        chunks = splitter.split_documents(docs)

        self._vs = FAISS.from_documents(chunks, embeddings)
        self._vs.save_local(index_dir)

    def search_top_sop(
        self, query: str, candidate_chunks: int = 6
    ) -> RetrievedSOP | None:
        hits = self._vs.similarity_search_with_score(query, k=candidate_chunks)
        if not hits:
            return None

        grouped: dict[str, dict[str, object]] = {}
        for doc, score in hits:
            source = doc.metadata.get("source", "unknown")
            if source not in grouped:
                grouped[source] = {
                    "score_sum": 0.0,
                    "chunks": [],
                }
            grouped[source]["score_sum"] += float(score)
            grouped[source]["chunks"].append(doc.page_content)

        best_source, best_data = min(
            grouped.items(),
            key=lambda item: float(item[1]["score_sum"]),
        )

        combined_content = "\n\n---\n\n".join(best_data["chunks"])

        return {
            "source": best_source,
            "content": combined_content,
        }


_DEFAULT_SOP_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "sops")
)
_INDEX_DIR = os.path.join(_DEFAULT_SOP_DIR, ".faiss_index")

_embeddings = llm_and_embeddings()["embeddings"]
_store = SOPStore(
    embeddings=_embeddings,
    sop_dir=_DEFAULT_SOP_DIR,
    index_dir=_INDEX_DIR,
)


@tool
def retrieve_sop(query: str) -> dict:
    """
    Retrieve most relevant SOP document given alarm context.
    """
    result = _store.search_top_sop(query)

    if result is None:
        return {
            "found": False,
            "source": "",
            "content": "",
        }

    return {
        "found": True,
        "source": result["source"],
        "content": result["content"],
    }


# TEST
# if __name__ == "__main__":
#     test_query = "payment service timeout and 5xx errors"
#     result = retrieve_sop.invoke({"query": test_query})
#     print(result)
