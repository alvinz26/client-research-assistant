"""Everything that talks to the Anthropic API. Other modules only see the plain data classes it returns."""
from __future__ import annotations

import json
import re

import anthropic

from research import prompts
from research.config import FALLBACK_MODELS, Config
from research.models import Brief, Claim, Evidence, Research, SourceInfo, Usage

WEB_SEARCH_TOOL = "web_search_20250305"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_CONTINUATIONS = 4  # how many times a paused research turn is resumed

_bullet = {"type": "object", "additionalProperties": False, "required": ["text", "claim_ids"],
           "properties": {"text": {"type": "string"}, "claim_ids": {"type": "array", "items": {"type": "string"}}}}
_strings = {"type": "array", "items": {"type": "string"}}
DRAFT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "confidence", "confidence_reason", "sections", "unverified", "gaps", "next_steps", "source_types"],
    "properties": {
        "summary": {"type": "array", "items": _bullet},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "confidence_reason": {"type": "string"},
        "sections": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["heading", "bullets"],
            "properties": {"heading": {"type": "string"}, "bullets": {"type": "array", "items": _bullet}}}},
        "unverified": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["claim_id", "reason"],
            "properties": {"claim_id": {"type": "string"}, "reason": {"type": "string"}}}},
        "gaps": _strings,
        "next_steps": _strings,
        "source_types": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["source_id", "type"],
            "properties": {"source_id": {"type": "string"},
                           "type": {"type": "string", "enum": ["official", "company", "third_party"]}}}},
    },
}


class ResearchError(Exception):
    """A problem explained in plain words, safe to show to the user."""


class ClaudeClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = anthropic.Anthropic(api_key=cfg.api_key)
        self.usage = Usage()

    def research(self, brief: Brief) -> Research:
        """Call 1: Claude searches the web and writes cited statements about the company."""
        request = {"role": "user", "content": prompts.research_request(brief)}
        blocks: list = []
        for _ in range(MAX_CONTINUATIONS + 1):
            messages = [request] + ([{"role": "assistant", "content": list(blocks)}] if blocks else [])
            response = self._create(
                max_tokens=16000, system=prompts.RESEARCH_SYSTEM, messages=messages,
                tools=[{"type": WEB_SEARCH_TOOL, "name": "web_search", "max_uses": self.cfg.max_searches}])
            blocks.extend(response.content)
            if response.stop_reason != "pause_turn":
                break
        research = parse_research(blocks)
        research.usage = self.usage
        return research

    def check_and_write(self, brief: Brief, research: Research) -> dict:
        """Call 2 (no web access): check each claim against its quotes and arrange the supported ones."""
        response = self._create(
            max_tokens=16000, system=prompts.check_system(brief.language),
            messages=[{"role": "user", "content": prompts.check_request(brief, research)}],
            output_config={"format": {"type": "json_schema", "schema": DRAFT_SCHEMA}})
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise ResearchError("The checking step returned an incomplete answer. Please try again.") from None

    def _create(self, **kwargs):
        if self.cfg.model in FALLBACK_MODELS:  # on a mistaken refusal, the API retries on another model
            kwargs.update(betas=[FALLBACK_BETA], fallbacks="default")
        try:
            response = self.client.beta.messages.create(model=self.cfg.model, **kwargs)
        except anthropic.AuthenticationError:
            raise ResearchError("The API key was rejected. Check ANTHROPIC_API_KEY in your .env file.") from None
        except anthropic.PermissionDeniedError:
            raise ResearchError("This API key isn't allowed to use this model or web search. "
                                "Web search can be enabled in the Claude Console settings.") from None
        except anthropic.NotFoundError:
            raise ResearchError(f"Model '{self.cfg.model}' was not found. Check ANTHROPIC_MODEL in .env.") from None
        except anthropic.RateLimitError:
            raise ResearchError("Rate limit reached. Wait a minute and try again.") from None
        except anthropic.BadRequestError as e:
            raise ResearchError(f"The API rejected the request: {e.message}") from None
        except anthropic.APIConnectionError:
            raise ResearchError("Could not reach the Anthropic API. Check your internet connection.") from None
        except anthropic.APIStatusError as e:
            raise ResearchError(f"The Anthropic API returned an error ({e.status_code}). Try again shortly.") from None
        if response.stop_reason == "refusal":
            raise ResearchError("Claude declined this request, so no report was written. "
                                "Try rewording the notes or company details.")
        self.usage.input_tokens += response.usage.input_tokens
        self.usage.output_tokens += response.usage.output_tokens
        self.usage.searches += getattr(getattr(response.usage, "server_tool_use", None), "web_search_requests", 0) or 0
        return response


def parse_research(blocks: list) -> Research:
    """Cited text blocks become claims; search results and citations become sources, deduped by URL."""
    sources: dict[str, SourceInfo] = {}
    claims: list[Claim] = []
    queries: list[str] = []
    loose_text: list[str] = []

    def source_id(url: str, title: str | None, page_age: str | None = None) -> str:
        key = url.split("#")[0].rstrip("/")
        if key not in sources:
            sources[key] = SourceInfo(f"S{len(sources) + 1}", url, title or url, page_age or "")
        elif page_age and not sources[key].page_age:
            sources[key].page_age = page_age
        return sources[key].id

    for block in blocks:
        kind = getattr(block, "type", "")
        if kind == "server_tool_use" and block.name == "web_search":
            queries.append((block.input or {}).get("query", ""))
        elif kind == "web_search_tool_result" and isinstance(block.content, list):  # an error is a single object
            for r in block.content:
                source_id(r.url, r.title, getattr(r, "page_age", None))
        elif kind == "text":
            cites = [c for c in (block.citations or []) if c.type == "web_search_result_location"]
            text = re.sub(r"\*\*|__", "", block.text).strip().lstrip("-*• ").strip()
            if cites and text:
                evidence = []
                for c in cites:
                    ev = Evidence(source_id(c.url, c.title), c.cited_text)
                    if ev not in evidence:
                        evidence.append(ev)
                claims.append(Claim(f"C{len(claims) + 1}", text, evidence))
            elif not cites:
                loose_text.append(block.text)
    return Research(claims, list(sources.values()), parse_gaps("".join(loose_text)), [q for q in queries if q])


def parse_gaps(text: str) -> list[str]:
    """Read the "- " list that follows a "GAPS:" line."""
    match = re.search(r"GAPS:?[ \t]*\n(.*)", text, re.S | re.I)
    if not match:
        return []
    return [line.strip().lstrip("-*• ").strip() for line in match.group(1).splitlines()
            if line.strip().startswith(("-", "*", "•"))]
