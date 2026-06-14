from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


JournalTone = Literal["warm", "reflective", "adventurous", "elegant"]
JournalLengthMode = Literal["short", "standard", "detailed"]
JournalTemplateKey = Literal["editorial", "scrapbook", "field_notes"]


class TripJournalGenerateRequest(BaseModel):
    tone: JournalTone = "warm"
    length_mode: JournalLengthMode = "standard"
    use_ai: bool = True
    template_key: JournalTemplateKey = "editorial"


class TripJournalUpdateRequest(BaseModel):
    title: str
    intro_text: Optional[str] = None
    closing_text: Optional[str] = None
    tone: JournalTone = "warm"
    length_mode: JournalLengthMode = "standard"
    content_json: Dict[str, Any]


class TripJournalResponse(BaseModel):
    id: int
    trip_id: int
    title: str
    intro_text: Optional[str] = None
    closing_text: Optional[str] = None
    tone: str
    length_mode: str
    content_json: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
