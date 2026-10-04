"""RAG 知识库入库脚本：将 docs/rules 下的文档切分、向量化写入 ChromaDB。

用法（需先启动 ChromaDB：docker run -p 8000:8000 chromadb/chroma）：
    python ingest.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import rag


def split_text(text: str, chunk_size: int = 400, overlap: int = 60) -> list[str]:
    """按段落切分，长段落再做滑动窗口切分。"""
    chunks = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) <= chunk_size:
            chunks.append(para)
        else:
            start = 0
            while start < len(para):
                chunks.append(para[start:start + chunk_size])
                start += chunk_size - overlap
    return chunks


def main():
    if not rag.chroma_available():
        print("ChromaDB 不可用，请先启动：docker run -p 8000:8000 chromadb/chroma")
        sys.exit(1)

    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "rules")
    files = glob.glob(os.path.join(base, "*.md")) + glob.glob(os.path.join(base, "*.txt"))
    if not files:
        print(f"未找到知识库文档：{base}")
        sys.exit(1)

    all_chunks, metas = [], []
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            text = f.read()
        chunks = split_text(text)
        all_chunks.extend(chunks)
        metas.extend([{"source": os.path.basename(fp)}] * len(chunks))

    n = rag.add_documents(all_chunks, metas)
    print(f"已写入 {n} 个文档片段到 ChromaDB（collection: {rag.COLLECTION_NAME}）")


if __name__ == "__main__":
    main()
