"""Built-in sample data so anyone can try the full workflow without an API key.

The company is fictional and every URL uses the reserved `.example` domain. Demo mode always shows
this sample, whatever company is typed in, so that no made-up facts are attached to a real name.
"""
from __future__ import annotations

from research.models import Brief, Claim, Evidence, Research, SourceInfo

SOURCES = [
    SourceInfo("S1", "https://harbourline.example/about", "About us - Harbourline Facades", "2025-06"),
    SourceInfo("S2", "https://registry.example/company/09876543", "HARBOURLINE FACADES LTD - company record", "2026-02"),
    SourceInfo("S3", "https://harbourline.example/products", "Products - Harbourline Facades"),
    SourceInfo("S4", "https://tradenews.example/2026/harbourline-second-site", "Harbourline opens second fabrication site", "2026-03"),
    SourceInfo("S5", "https://directory.example/harbourline", "Harbourline Facades - trade directory listing"),
]

CLAIMS = [
    ("C1", "Registered as a private limited company, incorporated in 2014.", "S2", "Private limited Company. Incorporated on 12 May 2014"),
    ("C2", "Company status is active.", "S2", "Company status: Active"),
    ("C3", "Registered office is in Leeds.", "S2", "Registered office address: 1 Sample Street, Leeds"),
    ("C4", "The company website uses the same domain as the contact's email.", "S1", "Contact us: info@harbourline.example"),
    ("C5", "Designs, fabricates and installs rainscreen cladding and curtain walling.", "S1", "We design, fabricate and install rainscreen cladding and curtain walling for commercial buildings"),
    ("C6", "Products include aluminium composite panels and curtain wall systems.", "S3", "Aluminium composite panels (ACM); unitised and stick curtain wall systems"),
    ("C7", "Works mainly in the North of England.", "S1", "projects across the North of England"),
    ("C8", "Opened a second fabrication site in 2026.", "S4", "has opened a second fabrication facility"),
    ("C9", "Has around 120 employees.", "S5", "Employees: 50-99"),
    ("C10", "Recently completed an office refurbishment in Manchester.", "S4", "after completing a Manchester office refurbishment"),
]


def sample_brief(language: str = "en") -> Brief:
    return Brief(
        company="Harbourline Facades Ltd (fictional sample)", website="harbourline.example", location="Leeds, UK",
        contact_name="J. Doe", job_title="Procurement Manager", phone="+44 113 000 0000",
        email="j.doe@harbourline.example", met_at="Sample trade fair", notes="Interested in composite panels",
        language=language,
    )


def sample(brief: Brief) -> tuple[Brief, Research, dict]:
    """Return the fixed sample brief, its research and a draft, as the live steps would."""
    research = Research(
        claims=[Claim(cid, text, [Evidence(sid, quote)]) for cid, text, sid, quote in CLAIMS],
        sources=list(SOURCES),
        queries=["Harbourline Facades Ltd Leeds", "Harbourline Facades company registry",
                 "harbourline.example", "Harbourline Facades news 2026"],
    )
    fact = lambda text, *ids: {"text": text, "claim_ids": list(ids)}  # noqa: E731
    draft = {
        "summary": [fact("Active UK cladding and curtain-walling contractor, incorporated 2014; opened a second "
                         "fabrication site in 2026.", "C1", "C2", "C5", "C8")],
        "confidence": "high",
        "confidence_reason": "The registry record matches the name, and the contact's email domain matches the company website.",
        "key_facts": {
            "what_they_do": fact("Designs, fabricates and installs rainscreen cladding and curtain walling", "C5"),
            "business_type": fact("Fabricator and installer (contractor)", "C5"),
            "location": fact("Registered office in Leeds; works mainly in the North of England", "C3", "C7"),
            "registration": fact("Private limited company, incorporated 12 May 2014, status active", "C1", "C2"),
            "customers": fact("Commercial building projects", "C5"),
            "size": fact(""),
            "identity_check": fact("Website domain matches the contact's email domain", "C4"),
        },
        "products": [{"category": "Cladding", "text": "Aluminium composite panels (ACM)", "claim_ids": ["C6"]},
                     {"category": "Curtain walling", "text": "Unitised and stick curtain wall systems", "claim_ids": ["C6"]}],
        "recent": [{"date": "2026", "text": "Opened a second fabrication site", "claim_ids": ["C8"]},
                   {"date": "", "text": "Completed an office refurbishment in Manchester", "claim_ids": ["C10"]}],
        "risks": [],
        "unverified": [{"claim_id": "C9", "reason": "The directory lists 50-99 employees, not around 120.",
                        "other_company": False}],
        "gaps": ["No turnover or filed accounts appeared in the search results.",
                 "No information on who currently supplies their composite panels."],
        "next_steps": ["Ask about annual panel volume and their current supplier.",
                       "Read the filed accounts on the official registry for turnover.",
                       "Ask whether the new fabrication site changes their sourcing."],
        "source_types": [{"source_id": "S1", "type": "company"}, {"source_id": "S2", "type": "official"},
                         {"source_id": "S3", "type": "company"}, {"source_id": "S4", "type": "third_party"},
                         {"source_id": "S5", "type": "third_party"}],
    }
    return sample_brief(brief.language), research, draft
