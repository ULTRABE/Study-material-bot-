"""
Job data models for the worker pool.
"""
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


class JobStatus(str, Enum):
    PENDING = "pending"
    DETECTING = "detecting"
    EXTRACTING = "extracting"
    DOWNLOADING = "downloading"
    OPTIMIZING = "optimizing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProcessingJob:
    """Represents a single media processing job."""

    url: str
    user_id: int
    chat_id: int
    message_id: int
    bot_token: str
    bot_id: int
    is_premium: bool = False

    # Auto-generated fields
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    error_message: Optional[str] = None
    output_file: Optional[str] = None
    file_size_bytes: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize job to dictionary for Redis storage."""
        return {
            "job_id": self.job_id,
            "url": self.url,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "message_id": self.message_id,
            "bot_token": self.bot_token,
            "bot_id": self.bot_id,
            "is_premium": self.is_premium,
            "status": self.status.value,
            "progress": self.progress,
            "error_message": self.error_message,
            "output_file": self.output_file,
            "file_size_bytes": self.file_size_bytes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcessingJob":
        """Deserialize job from dictionary."""
        job = cls(
            url=data["url"],
            user_id=data["user_id"],
            chat_id=data["chat_id"],
            message_id=data["message_id"],
            bot_token=data["bot_token"],
            bot_id=data["bot_id"],
            is_premium=data.get("is_premium", False),
        )
        job.job_id = data.get("job_id", job.job_id)
        job.status = JobStatus(data.get("status", JobStatus.PENDING.value))
        job.progress = data.get("progress", 0)
        job.error_message = data.get("error_message")
        job.output_file = data.get("output_file")
        job.file_size_bytes = data.get("file_size_bytes")
        return job
