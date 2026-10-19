"""The rules that keep the report traceable, enforced in code rather than by the prompt."""
from research.models import Brief, Claim, Evidence, Research, SourceInfo
from research.pipeline import KEY_FACTS, build_report


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


def _fact(text="", *ids):
    return {"text": text, "claim_ids": list(ids)}


def _draft():
    key_facts = {k: _fact() for k in KEY_FACTS}
    key_facts["registration"] = _fact("Incorporated 2014.", "C1")
    key_facts["size"] = _fact("Market leader in Europe.")  # no claim behind it
    return {
        "summary": [_fact("Acme is a registered glass supplier.", "C1", "C2")],
        "confidence": "medium",
        "confidence_reason": "Registry entry found.",
        "key_facts": key_facts,
        "products": [{"category": "Glass", "text": "Glass panels", "claim_ids": ["C2"]},
                     {"category": "Doors", "text": "Invented product", "claim_ids": ["C99"]}],
        "recent": [],
        "risks": [],
        "unverified": [{"claim_id": "C3", "reason": "Quote says 40, not 400.", "other_company": False}],
        "gaps": ["No revenue figures found."],
        "next_steps": ["Ask for their annual volume."],
        "source_types": [{"source_id": "S2", "type": "official"}],
    }


def test_unsupported_text_is_removed_and_counted():
    report = build_report(Brief("Acme"), _research(), _draft())
    facts = {f.label: f for f in report.key_facts}
    assert facts["size"].text == "" and facts["size"].refs == []  # shown as "Not found"
    assert [p.text for p in report.products] == ["Glass panels"]
    assert report.removed == 2


def test_key_facts_always_have_every_field_in_order():
    report = build_report(Brief("Acme"), _research(), {"key_facts": {}})
    assert [f.label for f in report.key_facts] == KEY_FACTS


def test_numbers_follow_first_use_and_only_used_sources_are_listed():
    report = build_report(Brief("Acme"), _research(), _draft())
    # Summary cites C1 (S2) then C2 (S1), so S2 becomes [1] and S1 becomes [2].
    assert report.summary[0].refs == [1, 2]
    assert [s.url for s in report.sources] == [
        "https://registry.example/acme", "https://acme.example/products", "https://news.example/acme"]


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
    assert report.sources[2].quotes == []  # a quote that failed the check isn't shown as evidence
