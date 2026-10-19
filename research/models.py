"""Plain data classes shared by every step. Nothing here knows which AI provider is used."""
from __future__ import annotations

from dataclasses import dataclass, field

CLUE_LABELS = {
    "website": "Website", "location": "Location", "contact_name": "Contact name",
    "job_title": "Job title", "phone": "Phone", "email": "Email",
    "met_at": "Where we met", "notes": "Notes",
}


@dataclass
class Brief:
    company: str
    website: str = ""
    location: str = ""
    contact_name: str = ""
    job_title: str = ""
    phone: str = ""
    email: str = ""
    met_at: str = ""
    notes: str = ""
    language: str = "en"  # "en" or "zh"

    def clues(self) -> list[tuple[str, str]]:
        """The optional fields that were filled in, as (label, value) pairs."""
        return [(label, getattr(self, key).strip()) for key, label in CLUE_LABELS.items()
                if getattr(self, key).strip()]


@dataclass
class Evidence:
    source_id: str
    quote: str


@dataclass
class Claim:
    """One statement from the research step, with the quotes the API attached to it."""
    id: str
    text: str
    evidence: list[Evidence]


@dataclass
class SourceInfo:
    id: str
    url: str
    title: str
    page_age: str = ""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    searches: int = 0


@dataclass
class Research:
    claims: list[Claim]
    sources: list[SourceInfo]
    gaps: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


@dataclass
class Bullet:
    text: str
    refs: list[int]
    note: str = ""


@dataclass
class Section:
    heading: str
    bullets: list[Bullet]


@dataclass
class Source:
    number: int
    url: str
    title: str
    page_age: str
    kind: str
    quotes: list[str]


@dataclass
class Report:
    brief: Brief
    summary: list[Bullet]
    confidence: str
    confidence_reason: str
    sections: list[Section]
    unverified: list[Bullet]
    gaps: list[str]
    next_steps: list[str]
    sources: list[Source]
    queries: list[str]
    removed: int
    demo: bool = False
    model: str = ""
