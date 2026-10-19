"""The live path with the Anthropic client replaced by a fake: no network, no key."""
import json

import anthropic
import httpx2 as httpx  # the HTTP library the anthropic 1.x SDK uses
import pytest
from docx import Document

from fakes import query, response, results, text
from research import claude_client
from research.claude_client import ResearchError
from research.config import Config
from research.models import Brief
from research.pipeline import run

SITE = "https://acme.example/about"
REGISTRY = "https://registry.example/acme"

DRAFT = {
    "summary": [{"text": "Acme is an active glass supplier.", "claim_ids": ["C1", "C2"]}],
    "confidence": "medium", "confidence_reason": "Registry record found.",
    "sections": [{"heading": "Identity & verification", "bullets": [
        {"text": "Incorporated in 2014.", "claim_ids": ["C1"]},
        {"text": "A fact the model made up.", "claim_ids": ["C42"]}]}],
    "unverified": [], "gaps": ["No revenue found."], "next_steps": ["Ask about volumes."],
    "source_types": [{"source_id": "S1", "type": "official"}],
}


class FakeClient:
    """Mimics `anthropic.Anthropic(...)` closely enough for ClaudeClient."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.beta = self
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _live_config(tmp_path):
    return Config(api_key="test-key", model="claude-sonnet-5-5", max_searches=5, demo=False, output_dir=tmp_path)


def _install(monkeypatch, replies):
    fake = FakeClient(replies)
    monkeypatch.setattr(claude_client.anthropic, "Anthropic", lambda **_: fake)
    return fake


def test_live_run_numbers_sources_and_drops_unsupported_text(tmp_path, monkeypatch):
    fake = _install(monkeypatch, [
        response([query("Acme Glass"), results((REGISTRY, "Registry", "2025-01"), (SITE, "About", None))],
                 stop="pause_turn", searches=1),
        response([text("Incorporated in 2014.", (REGISTRY, "Registry", "Incorporated on 12 May 2014")),
                  text("Sells glass.", (SITE, "About", "We sell glass"), (REGISTRY + "/", "Registry", "SIC 23120"))],
                 searches=1),
        response([text(json.dumps(DRAFT))]),
    ])
    result = run(Brief("Acme Glass", email="buyer@acme.example"), _live_config(tmp_path))

    research_call, continued_call, check_call = fake.calls
    assert research_call["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
    assert research_call["fallbacks"] == "default"
    assert continued_call["messages"][-1]["role"] == "assistant"  # pause_turn: the paused turn is sent back
    assert "tools" not in check_call and "output_config" in check_call

    report = result.report
    assert [s.url for s in report.sources] == [REGISTRY, SITE]  # deduped, numbered by first use
    assert [s.number for s in report.sources] == [1, 2]
    assert report.sources[0].quotes == ["Incorporated on 12 May 2014", "SIC 23120"]
    assert report.removed == 1
    assert result.usage.searches == 2

    doc_text = "\n".join(p.text for p in Document(result.path).paragraphs)
    assert "DEMO" not in doc_text
    assert "A fact the model made up." not in doc_text
    assert "[1] Registry" in doc_text


def test_api_errors_become_plain_messages(tmp_path, monkeypatch):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.AuthenticationError("invalid x-api-key", response=httpx.Response(401, request=request), body=None)
    _install(monkeypatch, [error])
    with pytest.raises(ResearchError, match="API key"):
        run(Brief("Acme"), _live_config(tmp_path))


def test_refusal_is_reported_not_written_up(tmp_path, monkeypatch):
    _install(monkeypatch, [response([], stop="refusal")])
    with pytest.raises(ResearchError, match="declined"):
        run(Brief("Acme"), _live_config(tmp_path))
