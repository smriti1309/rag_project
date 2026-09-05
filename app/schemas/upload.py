from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


class UploadResponse(BaseModel):
    """Schema for document upload response metadata."""

    document_id: str
    original_filename: str
    stored_filename: str
    size: int
    uploaded_at: datetime
    status: str
    chunk_count: int = 0
    file_type: str = "pdf"
    mime_type: str = "application/pdf"
    object_key: Optional[str] = None
    user_id: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class SavedDocument:
    """Internal data object representing a stored upload document and its filesystem path."""

    response: UploadResponse
    file_path: Path


