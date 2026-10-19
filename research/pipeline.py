"""The workflow: research -> check and write -> build the report -> Word file.

`build_report` is where the traceability rules are enforced, in code, whatever the model returns.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from research import demo
from research.config import Config
from research.models import Brief, Bullet, Report, Research, Section, Source, Usage
from research.report import write_docx

SOURCE_KINDS = {"official", "company", "third_party"}


@dataclass
class Result:
    report: Report
    path: Path
    usage: Usage


def run(brief: Brief, cfg: Config, progress: Callable[[str], None] = lambda _: None) -> Result:
    if not brief.company.strip():
        raise ValueError("Company name is required.")
    if cfg.demo:
        progress("Demo mode: loading the fictional sample company...")
        brief, research, draft = demo.sample(brief)
    else:
        from research.claude_client import ClaudeClient  # only needed for live runs

        client = ClaudeClient(cfg)
        progress("Searching the web (this can take a minute or two)...")
        research = client.research(brief)
        progress(f"Checking {len(research.claims)} statements against their sources...")
        draft = client.check_and_write(brief, research)
    progress("Building the Word report...")
    report = build_report(brief, research, draft, demo=cfg.demo, model=cfg.model)
    return Result(report, write_docx(report, cfg.output_dir), research.usage)


def build_report(brief: Brief, research: Research, draft: dict, *, demo: bool = False, model: str = "") -> Report:
    """Turn the model's draft (which refers to claim IDs) into a report with numbered, quoted sources.

    - A bullet with no valid claim ID is dropped and counted in `removed`.
    - Source numbers are assigned here, in order of first use; unused sources are not listed.
    """
    claims = {c.id: c for c in research.claims}
    info = {s.id: s for s in research.sources}
    kinds = {t.get("source_id"): t.get("type") for t in draft.get("source_types", [])}
    numbers: dict[str, int] = {}
    quotes: dict[str, list[str]] = {}
    removed = 0

    def cite(claim_ids: list[str]) -> list[int]:
        refs: list[int] = []
        for cid in claim_ids:
            for ev in claims[cid].evidence:
                if ev.source_id not in info:
                    continue
                n = numbers.setdefault(ev.source_id, len(numbers) + 1)
                if n not in refs:
                    refs.append(n)
                seen = quotes.setdefault(ev.source_id, [])
                if ev.quote and ev.quote not in seen:
                    seen.append(ev.quote)
        return refs

    def bullets(items: list[dict]) -> list[Bullet]:
        nonlocal removed
        kept = []
        for item in items:
            refs = cite([c for c in item.get("claim_ids", []) if c in claims])
            if refs:
                kept.append(Bullet(item.get("text", "").strip(), refs))
            else:
                removed += 1
        return kept

    summary = bullets(draft.get("summary", []))
    sections = [Section(s.get("heading", ""), bullets(s.get("bullets", []))) for s in draft.get("sections", [])]
    unverified = [Bullet(claims[u["claim_id"]].text, cite([u["claim_id"]]), u.get("reason", ""))
                  for u in draft.get("unverified", []) if u.get("claim_id") in claims]
    sources = [Source(n, info[sid].url, info[sid].title, info[sid].page_age,
                      kinds.get(sid) if kinds.get(sid) in SOURCE_KINDS else "unclassified", quotes.get(sid, []))
               for sid, n in numbers.items()]
    return Report(
        brief=brief, summary=summary, confidence=draft.get("confidence", "low"),
        confidence_reason=draft.get("confidence_reason", ""), sections=sections, unverified=unverified,
        gaps=draft.get("gaps", []), next_steps=draft.get("next_steps", []),
        sources=sources, queries=research.queries, removed=removed, demo=demo, model=model,
    )
