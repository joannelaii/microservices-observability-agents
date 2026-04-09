from __future__ import annotations

import os
import re
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


def _parse_sop_keywords(filepath: str) -> list[str]:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r"##\s*Keywords\s*\n(.+?)(?:\n##|\Z)", content, re.DOTALL)
        if match:
            kw_text = match.group(1).strip()
            return [kw.strip().lower() for kw in re.split(r"[,\n]", kw_text) if kw.strip()]
    except Exception:
        pass
    return []


class SOPStore:
    _vs: FAISS
    _keywords: dict[str, list[str]]  # absolute source path -> parsed keyword list

    def __init__(self, embeddings: Embeddings, sop_dir: str, index_dir: str) -> None:
        os.makedirs(index_dir, exist_ok=True)
        index_file = os.path.join(index_dir, "index.faiss")
        store_file = os.path.join(index_dir, "index.pkl")
        sop_files = [
            os.path.join(sop_dir, name)
            for name in os.listdir(sop_dir)
            if name.endswith(".md")
        ]
        latest_sop_time = max((os.path.getmtime(path) for path in sop_files), default=0)
        saved_index_time = min(
            (
                os.path.getmtime(path)
                for path in (index_file, store_file)
                if os.path.exists(path)
            ),
            default=0,
        )

        if (
            os.path.exists(index_file)
            and os.path.exists(store_file)
            and saved_index_time >= latest_sop_time
        ):
            self._vs = FAISS.load_local(
                index_dir,
                embeddings,
                allow_dangerous_deserialization=True,
            )
        else:
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

        # Build keyword index from each SOP's ## Keywords section for re-ranking
        self._keywords = {path: _parse_sop_keywords(path) for path in sop_files}

    def _keyword_score(self, source: str, query_lower: str) -> int:
        keywords = self._keywords.get(source, [])
        return sum(query_lower.count(kw) for kw in keywords if kw)

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
                    "best_score": float("inf"),
                    "chunks": [],
                }
            grouped[source]["best_score"] = min(grouped[source]["best_score"], float(score))
            grouped[source]["chunks"].append(doc.page_content)

        # Re-rank: prefer the SOP whose keywords appear most in the query
        # Fall back to FAISS similarity score when keyword counts are tied
        query_lower = query.lower()
        best_source, best_data = min(
            grouped.items(),
            key=lambda item: (
                -self._keyword_score(item[0], query_lower), # higher keyword hits -> ranked first
                float(item[1]["best_score"]), # lower FAISS distance -> ranked first
            ),
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
    Retrieve most relevant SOP document given alarm context
    """
    result = _store.search_top_sop(query)

    if result is None:
        return {
            "found": False,
            "source": "",
            "content": "",
        }

    print("\n[SOP]")
    print(result["source"])

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
