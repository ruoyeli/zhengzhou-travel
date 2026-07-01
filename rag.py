import logging
import os
from functools import lru_cache
from typing import List

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter


logger = logging.getLogger(__name__)
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def load_and_split_pdfs(docs_dir: str) -> List[str]:
    """
    读取 docs_dir 目录下所有 PDF 文件，切分成文本块。
    """
    if not os.path.isdir(docs_dir):
        raise ValueError(f"目录不存在: {docs_dir}")

    pdf_files = [f for f in os.listdir(docs_dir) if f.lower().endswith(".pdf")]
    if not pdf_files:
        raise ValueError(f"在 {docs_dir} 中没有找到 .pdf 文件")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        length_function=len,
    )

    all_chunks = []
    for pdf_file in pdf_files:
        file_path = os.path.join(docs_dir, pdf_file)
        loader = PyPDFLoader(file_path)
        try:
            docs = loader.load()
            chunks = splitter.split_documents(docs)
            all_chunks.extend([chunk.page_content for chunk in chunks])
        except Exception as e:
            logger.warning("加载 PDF 文件 %s 时出错: %s", pdf_file, e)
            continue

    return all_chunks


@lru_cache(maxsize=1)
def get_embeddings():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


@lru_cache(maxsize=4)
def get_vectorstore(persist_dir: str):
    return Chroma(
        persist_directory=persist_dir,
        embedding_function=get_embeddings(),
    )


def build_vectorstore(chunks: List[str], persist_dir: str):
    """
    将文本块存入 Chroma 向量库（持久化到 persist_dir）。
    """
    if not chunks:
        raise ValueError("文本块列表为空，无法构建向量库")

    vectorstore = Chroma.from_texts(
        texts=chunks,
        embedding=get_embeddings(),
        persist_directory=persist_dir,
    )
    get_vectorstore.cache_clear()
    return vectorstore


def search_docs(query: str, persist_dir: str, k: int = 3) -> str:
    if not os.path.isdir(persist_dir):
        return ""

    docs = get_vectorstore(persist_dir).similarity_search(query, k=k)
    if not docs:
        return ""

    return "\n\n---\n\n".join([doc.page_content for doc in docs])
