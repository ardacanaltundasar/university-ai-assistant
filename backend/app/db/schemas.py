"""PostgreSQL API şemaları (Pydantic)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    title: str = Field(default="Yeni Sohbet", max_length=255)


class ChatSessionOut(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionOut]


class DeleteSessionResponse(BaseModel):
    success: bool = True
    message: str = "Chat session deleted"


class ChatMessageOut(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageListResponse(BaseModel):
    session_id: UUID
    messages: list[ChatMessageOut]


class FeedbackCreate(BaseModel):
    message_id: UUID | None = None
    rating: str = Field(..., min_length=1, max_length=32)
    comment: str | None = None


class FeedbackOut(BaseModel):
    id: UUID
    message_id: UUID | None
    rating: str
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentMetadataOut(BaseModel):
    id: UUID
    source: str
    source_type: str
    title: str
    url: str | None
    indexed_at: datetime | None
    chunk_count: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentMetadataOut]
