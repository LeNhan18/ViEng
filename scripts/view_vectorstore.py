"""
Xem nội dung vectorstore (các chunks đã index).
Chạy: python scripts/view_vectorstore.py

Tùy chọn:
  --limit N    Chỉ hiển thị N chunks đầu (mặc định: 20)
  --all        Hiển thị tất cả chunks
  --output F   Ghi ra file F thay vì in ra màn hình
  --search Q   Tìm chunks liên quan đến query Q
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from app.core.config import get_settings


def main():
    parser = argparse.ArgumentParser(description="Xem nội dung vectorstore")
    parser.add_argument("--limit", type=int, default=20, help="Số chunks hiển thị (mặc định: 20)")
    parser.add_argument("--all", action="store_true", help="Hiển thị tất cả chunks")
    parser.add_argument("--output", type=str, help="Ghi ra file thay vì in màn hình")
    parser.add_argument("--search", type=str, help="Tìm chunks liên quan đến query")
    args = parser.parse_args()

    settings = get_settings()
    persist_dir = Path(settings.chroma_persist_dir)

    if not persist_dir.exists() or not any(persist_dir.iterdir()):
        print("Vectorstore chưa tồn tại. Chạy index trước: POST /api/v1/rag/index")
        return 1

    print("Đang load embeddings và vectorstore...")
    embeddings = HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": "cpu"},
    )
    vectorstore = Chroma(
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
    )

    if args.search:
        k = 100 if args.all else args.limit
        results = vectorstore.similarity_search(args.search, k=k)
        results = [{"content": d.page_content, "meta": d.metadata} for d in results]
        print(f"\nTìm thấy {len(results)} chunks liên quan đến '{args.search}':\n")
    else:
        collection = vectorstore._collection
        data = collection.get(include=["documents", "metadatas"])
        docs = data["documents"] or []
        metas = data["metadatas"] or [{}] * len(docs)
        results = [{"content": d, "meta": m} for d, m in zip(docs, metas)]
        limit = len(results) if args.all else args.limit
        results = results[:limit]
        print(f"\nTổng số chunks: {len(docs)}")
        print(f"Hiển thị {len(results)} chunks:\n")

    lines = []
    for i, item in enumerate(results, 1):
        meta = item.get("meta", {})
        content = item.get("content", "")
        source = meta.get("source", "N/A")
        if isinstance(source, str) and "knowledge_base" in source:
            source = Path(source).name
        preview = content[:400] + "..." if len(content) > 400 else content
        block = f"{'='*60}\nChunk {i} | Nguồn: {source}\n{'-'*60}\n{preview}\n"
        lines.append(block)
        print(block)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"\nĐã ghi {len(lines)} chunks vào {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
