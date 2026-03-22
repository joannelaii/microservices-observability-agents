import os
from typing import TypedDict

from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel

OLLAMA_MODEL = "qwen2.5-coder"


class LLM_EMBEDDING(TypedDict):
    llm: BaseChatModel
    embeddings: Embeddings


def llm_and_embeddings() -> LLM_EMBEDDING:
    if "OPENAI_API_KEY" in os.environ:
        return {
            "embeddings": OpenAIEmbeddings(),
            "llm": ChatOpenAI(model="gpt-4o-mini", temperature=0),
        }
    __endpoint = os.environ.get("OLLAMA_ENDPOINT")
    __token = os.environ.get("OLLAMA_TOKEN")
    headers = {"X-Tunnel-Authorization": f"tunnel {__token}"}
    return {
        "embeddings": OllamaEmbeddings(
            model=OLLAMA_MODEL,
            base_url=__endpoint,
            client_kwargs={"headers": headers},
        ),
        "llm": ChatOllama(
            model=OLLAMA_MODEL,
            base_url=__endpoint,
            client_kwargs={"headers": headers},
        ),
    }
