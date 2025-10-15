from pydantic import BaseModel
from typing import Optional

class FollowUpRequest(BaseModel):
    email: str
    name: Optional[str] = None
    company: Optional[str] = None
