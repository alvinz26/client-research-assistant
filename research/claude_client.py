"""Everything that talks to the Anthropic API. Other modules only see the plain data classes it returns."""
from __future__ import annotations

import json
import re
from bisect import bisect_right
from datetime import date, timedelta

import anthropic

from research import prompts
from research.config import FALLBACK_MODELS, Config
from research.models import Brief, Claim, Evidence, Research, SourceInfo, Usage
from research.pipeline import KEY_FACTS

WEB_SEARCH_TOOL = "web_search_20250305"
BLOCKED_DOMAINS = ["linkedin.com/in"]  # personal profile pages: research the company, not the person
# Web fetch reads a whole page, so its citations carry the exact text instead of a ~150-character snippet.
# It can only open URLs from the brief or from search results, so personal profiles stay out.
WEB_FETCH_TOOL = {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 3,
                  "citations": {"enabled": True}, "max_content_tokens": 8000}
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_CONTINUATIONS = 4  # how many times a paused research turn is resumed


def _obj(**props) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def _list(item: dict) -> dict:
    return {"type": "array", "items": item}


def _enum(*values: str) -> dict:
    return {"type": "string", "enum": list(values)}


# Kept flat on purpose: nested objects make the structured-output grammar too large for the API.
_str = {"type": "string"}
DRAFT_SCHEMA = _obj(
    summary=_list(_obj(text=_str, claim_ids=_list(_str))),
    confidence=_enum("high", "medium", "low"),
    confidence_reason=_str,
    entries=_list(_obj(section=_enum("key_fact", "product", "recent", "risk"), label=_str, text=_str,
                       claim_ids=_list(_str))),
    unverified=_list(_obj(claim_id=_str, text=_str, reason=_str, other_company={"type": "boolean"})),
    gaps=_list(_str),
    next_steps=_list(_str),
    source_types=_list(_obj(source_id=_str, type=_enum("official", "company", "third_party"))),
)


def draft_from_entries(data: dict) -> dict:
    """Sort the flat `entries` rows into the key facts and tables that build_report expects."""
    draft = {k: v for k, v in data.items() if k != "entries"}
    draft.update(key_facts={}, products=[], recent=[], risks=[])
    for e in data.get("entries", []):
        row, section, label = {"text": e.get("text", ""), "claim_ids": e.get("claim_ids", [])}, e.get("section"), e.get("label", "")
        if section == "key_fact" and label in KEY_FACTS:
            draft["key_facts"].setdefault(label, row)
        elif section == "product":
            draft["products"].append({**row, "category": label})
        elif section == "recent":
            draft["recent"].append({**row, "date": label})
        elif section == "risk":
            draft["risks"].append(row)
    return draft


class ResearchError(Exception):
    """A problem explained in plain words, safe to show to the user."""


def verify_key(key: str) -> None:
    """Check that a key works by listing models, which costs nothing. Raises ResearchError if it doesn't."""
    try:
        anthropic.Anthropic(api_key=key).models.list(limit=1)
    except anthropic.AuthenticationError:
        raise ResearchError("That API key was rejected. Check that it was copied in full.") from None
    except anthropic.APIConnectionError:
        raise ResearchError("Could not reach the Anthropic API. Check your internet connection.") from None
    except anthropic.APIStatusError as e:
        raise ResearchError(f"The key couldn't be checked ({e.status_code}). Try again shortly.") from None


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
                tools=[{"type": WEB_SEARCH_TOOL, "name": "web_search", "max_uses": self.cfg.max_searches,
                        "blocked_domains": BLOCKED_DOMAINS}, WEB_FETCH_TOOL])
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
            return draft_from_entries(json.loads(text))
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


SENTENCE_END = re.compile(r"(?<=[.!?。！？])[*_\"”')\]]*\s+|\n+")
AGO = re.compile(r"(\d+)\s+(day|week|month|year)s?\s+ago", re.I)


def parse_research(blocks: list) -> Research:
    """Cited text becomes claims (one per sentence); search results and citations become sources, deduped by URL.

    The API often cites part of a sentence ("incorporated in 2014"), so each claim is widened to the whole
    sentence it sits in. Uncited sentences (introductions, commentary) are not claims.
    """
    sources: dict[str, SourceInfo] = {}
    queries: list[str] = []
    fetched: list[tuple[str, str]] = []  # (source id, page text) for each page read with web fetch, in order
    full = ""
    cited: list[tuple[int, int, list[Evidence]]] = []

    def source_id(url: str, title: str | None, page_age: str | None = None) -> str:
        key = url.split("#")[0].rstrip("/")
        if key not in sources:
            sources[key] = SourceInfo(f"S{len(sources) + 1}", url, (title or url).strip().lstrip("-• ").strip(),
                                      _page_date(page_age))
        elif page_age and not sources[key].page_age:
            sources[key].page_age = _page_date(page_age)
        return sources[key].id

    def evidence(c) -> Evidence | None:
        if c.type == "web_search_result_location":
            return Evidence(source_id(c.url, c.title), _tidy(c.cited_text))
        index = getattr(c, "document_index", None)  # a citation into a fetched page
        if c.type in ("char_location", "page_location") and index is not None and index < len(fetched):
            sid, page = fetched[index]
            exact = page[c.start_char_index:c.end_char_index] if c.type == "char_location" and page else ""
            return Evidence(sid, _tidy(exact or c.cited_text))
        return None

    for block in blocks:
        kind = getattr(block, "type", "")
        if kind == "text":
            found = [e for e in map(evidence, block.citations or []) if e]
            start, full = len(full), full + block.text
            if found and block.text.strip():  # position of the cited words, ignoring surrounding spaces
                lead = len(block.text) - len(block.text.lstrip())
                cited.append((start + lead, start + len(block.text.rstrip()), found))
            continue
        full += "\n"  # a tool call ends the sentence before it
        if kind == "server_tool_use" and block.name == "web_search":
            queries.append((block.input or {}).get("query", ""))
        elif kind == "web_search_tool_result" and isinstance(block.content, list):  # an error is a single object
            for r in block.content:
                source_id(r.url, r.title, getattr(r, "page_age", None))
        elif kind == "web_fetch_tool_result" and getattr(block.content, "type", "") == "web_fetch_result":
            doc = block.content.content
            source = getattr(doc, "source", None)
            page = source.data if getattr(source, "type", "") == "text" else ""
            fetched.append((source_id(block.content.url, getattr(doc, "title", None)), page))

    starts = [0] + [m.end() for m in SENTENCE_END.finditer(full)]
    grouped: dict[tuple[int, int], list[Evidence]] = {}
    for start, end, evidence in cited:
        key = (bisect_right(starts, start) - 1, bisect_right(starts, max(start, end - 1)) - 1)
        bucket = grouped.setdefault(key, [])
        bucket += [e for e in evidence if e not in bucket]
    claims = []
    for (first, last), evidence in grouped.items():
        end = starts[last + 1] if last + 1 < len(starts) else len(full)
        text = re.sub(r"\*\*|__", "", full[starts[first]:end]).strip().lstrip("-*• ").strip()
        if text:
            claims.append(Claim(f"C{len(claims) + 1}", text, evidence))
    return Research(claims, list(sources.values()), parse_gaps(full), [q for q in queries if q])


def _tidy(quote: str) -> str:
    """Remove page formatting (markdown headings, escapes, line breaks) from a quote without changing its words."""
    quote = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", quote or "")  # markdown links and images: keep the text
    quote = re.sub(r"\]\([^)]*\)|\[\]", "", quote)  # link pieces cut in half at the start of a quote
    quote = re.sub(r"(?m)^\s*(#+\s*|[-*]\s+)", "", quote).replace("\\_", "_").replace("**", "")
    return re.sub(r"\s+", " ", quote).strip()


def _page_date(age: str | None) -> str:
    """Turn a relative page age ("284 days ago") into a date, so it still means something in a saved report."""
    match = AGO.search(age or "")
    if not match:
        return age or ""
    unit = match.group(2).lower()
    day = date.today() - timedelta(days=int(match.group(1)) * {"day": 1, "week": 7, "month": 30, "year": 365}[unit])
    return day.isoformat() if unit in ("day", "week") else day.strftime("%Y-%m")


def parse_gaps(text: str) -> list[str]:
    """Read the "- " list that follows a "GAPS:" line."""
    match = re.search(r"GAPS:?[ \t]*\n(.*)", text, re.S | re.I)
    if not match:
        return []
    return [line.strip().lstrip("-*• ").strip() for line in match.group(1).splitlines()
            if line.strip().startswith(("-", "*", "•"))]
