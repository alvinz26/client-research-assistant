"""Command-line version: python cli.py "Company" [--website ...] [--lang zh]"""
import argparse
import sys
import time

from research.claude_client import ResearchError
from research.config import estimate_cost, load_config
from research.models import Brief
from research.pipeline import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Research a company and write a cited Word report.")
    parser.add_argument("company", help="company name (required)")
    for flag, help_text in [("website", "company website"), ("location", "country or city"),
                            ("contact", "contact person's name"), ("title", "contact's job title"),
                            ("phone", "contact phone"), ("email", "contact email"),
                            ("met-at", "where you met, e.g. a trade fair"), ("notes", "anything else, or what you want to know")]:
        parser.add_argument(f"--{flag}", default="", help=help_text)
    parser.add_argument("--lang", choices=["en", "zh"], default="en", help="report language (default: en)")
    a = parser.parse_args()

    cfg = load_config()
    if cfg.demo:
        print("DEMO MODE: no API key found (or DEMO_MODE=1). The report shows a fictional sample company.\n")
    brief = Brief(a.company, a.website, a.location, a.contact, a.title, a.phone, a.email, a.met_at, a.notes, a.lang)
    start = time.perf_counter()
    try:
        result = run(brief, cfg, lambda msg: print(f"- {msg}"))
    except (ResearchError, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1

    report, usage = result.report, result.usage
    print(f"\n{report.brief.company} - confidence: {report.confidence}. {report.confidence_reason}")
    for bullet in report.summary:
        print(f"  * {bullet.text} {''.join(f'[{n}]' for n in bullet.refs)}")
    print(f"\n{len(report.sources)} sources, {len(report.unverified)} unverified leads, "
          f"{report.removed} statements removed, {usage.searches} searches, {time.perf_counter() - start:.0f}s")
    cost = None if cfg.demo else estimate_cost(cfg.model, usage.input_tokens, usage.output_tokens, usage.searches)
    if cost is not None:
        print(f"Estimated API cost: ${cost:.2f} ({usage.input_tokens:,} input / {usage.output_tokens:,} output tokens)")
    print(f"Saved: {result.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
