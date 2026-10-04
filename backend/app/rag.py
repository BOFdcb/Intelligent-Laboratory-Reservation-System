"""RAG 服务：SiliconFlow Embedding + ChromaDB（Docker，REST API）。

不依赖 chromadb 客户端库，直接通过 httpx 调 Chroma v2 REST 接口，
避免 Python 3.14 下 onnxruntime 等重依赖的兼容性问题。
"""
import hashlib

import httpx

from .config import settings
from .llm import get_embed_client

TENANT = "default_tenant"
DATABASE = "default_database"
COLLECTION_NAME = "lab_rules"

_collection_id_cache: str | None = None


def _base() -> str:
    return f"http://{settings.CHROMA_HOST}:{settings.CHROMA_PORT}/api/v2"


def embed_texts(texts: list[str]) -> list[list[float]]:
    client = get_embed_client()
    resp = client.embeddings.create(model=settings.EMBED_MODEL_NAME, input=texts)
    return [d.embedding for d in resp.data]


def get_collection_id() -> str:
    global _collection_id_cache
    if _collection_id_cache:
        return _collection_id_cache
    url = f"{_base()}/tenants/{TENANT}/databases/{DATABASE}/collections"
    resp = httpx.post(url, json={"name": COLLECTION_NAME, "get_or_create": True}, timeout=30)
    resp.raise_for_status()
    _collection_id_cache = resp.json()["id"]
    return _collection_id_cache


def add_documents(documents: list[str], metadatas: list[dict] | None = None) -> int:
    """文档切分后入库，返回写入条数。"""
    if not documents:
        return 0
    cid = get_collection_id()
    embeddings = embed_texts(documents)
    ids = [hashlib.md5(d.encode()).hexdigest() for d in documents]
    url = f"{_base()}/tenants/{TENANT}/databases/{DATABASE}/collections/{cid}/upsert"
    payload = {
        "ids": ids,
        "embeddings": embeddings,
        "documents": documents,
        "metadatas": metadatas or [{} for _ in documents],
    }
    resp = httpx.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    return len(ids)


def search(query: str, top_k: int = 3) -> list[str]:
    """按语义检索最相关的文档片段。"""
    try:
        cid = get_collection_id()
        q_emb = embed_texts([query])[0]
        url = f"{_base()}/tenants/{TENANT}/databases/{DATABASE}/collections/{cid}/query"
        resp = httpx.post(url, json={"query_embeddings": [q_emb], "n_results": top_k}, timeout=60)
        resp.raise_for_status()
        docs = resp.json().get("documents", [[]])[0]
        return [d for d in docs if d]
    except Exception:
        # ChromaDB 未启动或检索失败时静默降级，不影响主对话
        return []


def chroma_available() -> bool:
    try:
        resp = httpx.get(f"{_base()}/heartbeat", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False
