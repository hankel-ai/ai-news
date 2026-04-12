from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Story:
    title: str
    url: str
    source_name: str
    summary: str = ""
    article_content: str = ""
    score: Optional[int] = None
    published: Optional[datetime] = None
    image_url: Optional[str] = None
    keywords_matched: list[str] = field(default_factory=list)
