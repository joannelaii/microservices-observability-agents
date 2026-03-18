from __future__ import annotations

import os
from typing import Any

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.tools import tool


class SOPStore:
    _vs: FAISS
    _kwargs: dict[str, Any]

    def __init__(self, sop_dir: str, index_dir: str, **kwargs) -> None:
        """
        builds or loads the store from the specified directory
        """
        self._kwargs = kwargs
        os.makedirs(index_dir, exist_ok=True)
        index_file = os.path.join(index_dir, "index.faiss")
        store_file = os.path.join(index_dir, "index.pkl")

        embeddings = OpenAIEmbeddings()

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

    # taken from https://docs.langchain.com/oss/python/langgraph/agentic-rag
    @tool
    def retrieve_docs(self, query: str):
        """retriever tool bound to llm invocations"""
        docs = self._vs.as_retriever(**self._kwargs).invoke(query)
        return "\n\n".join([doc.page_content for doc in docs])
