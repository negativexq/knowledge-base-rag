from dataclasses import dataclass
from datetime import datetime

DEFAULT_STATUS = "active"


@dataclass(frozen=True)
class DocumentRecord:
    source_type: str
    source_id: str
    content_hash: str
    last_synced_at: datetime
    version: int
    status: str
