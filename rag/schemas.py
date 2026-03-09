from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel, Field

class ChunkRecord(BaseModel):
    vector_id: int 
    chunk_id: str 
    file_path: str 
    title_path: Union[List[str], str, None] 
    chunk_type: str  
    chunk_index: int
    doc_hash: str
    text_for_embedding: str
    excerpt_markdown: str

class Manifest(BaseModel):
    kb_version: str 
    source_dir: str
    build_time: str
    embedding_model: str
    llm_provider_default: str
    faiss_metric: str
    doc_count: int
    chunk_count: int
    failed_files: List[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    question: str


class Citation(BaseModel):
    id: int
    file_path: str
    title_path: Optional[Union[List[str], str]] = None
    excerpt: str
    score: Optional[float] = None


class ChatResponse(BaseModel):
    answer_markdown: str
    citations: List[Citation]
    request_id: str


class CacheStatusResponse(BaseModel):
    provider: str
    size: int
    max_size: int
    info: dict


class HealthResponse(BaseModel):
    status: str
    kb_loaded: bool
    kb_version: Optional[str] = None
    provider: Optional[str] = None
    llm_model: Optional[str] = None
    embed_model: Optional[str] = None
    detail: Optional[str] = None
