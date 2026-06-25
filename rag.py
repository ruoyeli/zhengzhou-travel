from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from pathlib import Path
import os
from typing import List


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
            print(f"加载 PDF 文件 {pdf_file} 时出错: {e}")
            continue

    return all_chunks


def build_vectorstore(chunks: List[str], persist_dir: str):
    """
    将文本块存入 Chroma 向量库（持久化到 persist_dir）。
    """
    if not chunks:
        raise ValueError("文本块列表为空，无法构建向量库")

    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    # 创建 Chroma 向量库并持久化
    vectorstore = Chroma.from_texts(
        texts=chunks,
        embedding=embeddings,
        persist_directory=persist_dir,
    )
    return vectorstore


def search_docs(query: str, persist_dir: str, k: int = 3) -> str:
    if not os.path.isdir(persist_dir):
        return ""

    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    # 从持久化目录加载已有的向量库
    vectorstore = Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings,
    )

    docs = vectorstore.similarity_search(query, k=k)
    if not docs:
        return ""

    return "\n\n---\n\n".join([doc.page_content for doc in docs])
