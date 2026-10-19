"""The rules that keep the report traceable, enforced in code rather than by the prompt."""
from research.models import Brief, Claim, Evidence, Research, SourceInfo
from research.pipeline import build_report


def _research():
    return Research(
        claims=[
            Claim("C1", "Registered in 2014.", [Evidence("S2", "Incorporated on 12 May 2014")]),
            Claim("C2", "Sells glass panels.", [Evidence("S1", "We supply glass panels")]),
            Claim("C3", "Has 400 staff.", [Evidence("S3", "a team of 40")]),
        ],
        sources=[
            SourceInfo("S1", "https://acme.example/products", "Products"),
            SourceInfo("S2", "https://registry.example/acme", "Registry entry", "2025-01"),
            SourceInfo("S3", "https://news.example/acme", "News"),
            SourceInfo("S4", "https://never-used.example", "Unused"),
        ],
    )


def _draft(**overrides):
    draft = {
        "summary": [{"text": "Acme is a registered glass supplier.", "claim_ids": ["C1", "C2"]}],
        "confidence": "medium",
        "confidence_reason": "Registry entry found.",
        "sections": [
            {"heading": "Identity & verification", "bullets": [{"text": "Registered in 2014.", "claim_ids": ["C1"]}]},
            {"heading": "Business & products", "bullets": [
                {"text": "Sells glass panels.", "claim_ids": ["C2"]},
                {"text": "Market leader in Europe.", "claim_ids": []},
                {"text": "Invented claim.", "claim_ids": ["C99"]},
            ]},
        ],
        "unverified": [{"claim_id": "C3", "reason": "Quote says 40, not 400."}],
        "gaps": ["No revenue figures found."],
        "next_steps": ["Ask for their annual volume."],
        "source_types": [{"source_id": "S2", "type": "official"}],
    }
    draft.update(overrides)
    return draft


def test_bullets_without_a_valid_claim_are_dropped_and_counted():
    report = build_report(Brief("Acme"), _research(), _draft())
    texts = [b.text for s in report.sections for b in s.bullets]
    assert "Market leader in Europe." not in texts
    assert "Invented claim." not in texts
    assert report.removed == 2


def test_numbers_follow_first_use_and_only_used_sources_are_listed():
    report = build_report(Brief("Acme"), _research(), _draft())
    # Summary cites C1 (S2) then C2 (S1), so S2 becomes [1] and S1 becomes [2].
    assert report.summary[0].refs == [1, 2]
    assert [s.url for s in report.sources] == [
        "https://registry.example/acme", "https://acme.example/products", "https://news.example/acme"]
    assert all(s.url != "https://never-used.example" for s in report.sources)


def test_sources_carry_their_quotes_and_type():
    report = build_report(Brief("Acme"), _research(), _draft())
    registry = report.sources[0]
    assert registry.quotes == ["Incorporated on 12 May 2014"]
    assert registry.kind == "official"
    assert registry.page_age == "2025-01"
    assert report.sources[1].kind == "unclassified"


def test_unverified_claims_keep_their_text_reason_and_reference():
    report = build_report(Brief("Acme"), _research(), _draft())
    lead = report.unverified[0]
    assert lead.text == "Has 400 staff."
    assert lead.note == "Quote says 40, not 400."
    assert lead.refs == [3]
