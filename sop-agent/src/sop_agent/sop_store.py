from __future__ import annotations

import os
from dataclasses import dataclass, asdict

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.vectorstores import FAISS
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass
class RetrievedSOP:
    source: str
    content: str

    def __iter__(self):
        for k, v in asdict(self).items():
            yield ((k, v))


class SOPStore:
    _vs: FAISS

    def __init__(self, embeddings: Embeddings, sop_dir: str, index_dir: str) -> None:
        """
        builds or loads the store from the specified directory
        """
        os.makedirs(index_dir, exist_ok=True)
        index_file = os.path.join(index_dir, "index.faiss")
        store_file = os.path.join(index_dir, "index.pkl")

        # If index exists, load it
        if os.path.exists(index_file) and os.path.exists(store_file):
            self._vs = FAISS.load_local(
                index_dir, embeddings, allow_dangerous_deserialization=True
            )
            return

        # Otherwise build it once
        loader = DirectoryLoader(
            sop_dir,
            glob="**/*.md",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
        )
        docs = loader.load()

        splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=150)
        chunks = splitter.split_documents(docs)

        self._vs = FAISS.from_documents(chunks, embeddings)
        self._vs.save_local(index_dir)

    def search(self, query: str, k: int = 4) -> list[RetrievedSOP]:
        hits = self._vs.similarity_search(query, k=k)
        return [
            RetrievedSOP(
                source=d.metadata.get("source", "unknown"), content=d.page_content
            )
            for d in hits
        ]
