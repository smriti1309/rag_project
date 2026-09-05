from datetime import datetime, timezone
from pathlib import Path
import uuid

from fastapi import UploadFile

from app.core.config import settings
from app.schemas.upload import SavedDocument, UploadResponse


def save_file(file: UploadFile) -> SavedDocument:
    """Save an uploaded PDF file to disk after validation.

    Args:
        file: The UploadFile object received from the request.

    Returns:
        SavedDocument: Internal container with document metadata and saved file path.

    Raises:
        ValueError: If validation fails (missing filename, invalid extension, or size limit exceeded).
        OSError: If file writing or directory creation fails.
    """
    if not file.filename:
        raise ValueError("Filename must be provided.")

    original_filename = file.filename
    file_ext = Path(original_filename).suffix.lower()

    if file_ext not in settings.allowed_extensions:
        raise ValueError("Only PDF files are allowed.")

    content = file.file.read()

    if len(content) == 0:
        raise ValueError("Uploaded file is empty.")

    if len(content) > settings.max_file_size:
        raise ValueError(
            f"File size ({len(content)} bytes) exceeds the maximum allowed limit of {settings.max_file_size} bytes."
        )

    try:
        settings.upload_directory.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise OSError(f"Failed to create upload directory: {e}") from e

    document_id = str(uuid.uuid4())
    stored_filename = f"{document_id}.pdf"
    destination_path = settings.upload_directory / stored_filename

    try:
        destination_path.write_bytes(content)
    except Exception as e:
        raise OSError(f"Failed to save file to disk: {e}") from e

    response = UploadResponse(
        document_id=document_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        size=len(content),
        uploaded_at=datetime.now(timezone.utc),
        status="uploaded",
    )
    return SavedDocument(response=response, file_path=destination_path)

