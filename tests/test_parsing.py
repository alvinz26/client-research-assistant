"""Turning the research response's content blocks into claims, sources, queries and gaps."""
from types import SimpleNamespace as NS

from fakes import fetch_text, fetched, query, results, text
from research.claude_client import parse_gaps, parse_research

REGISTRY = "https://registry.example/acme"


def _blocks():
    return [
        text("I'll start by searching for the company."),
        query("Acme Glass Leeds"),
        results((REGISTRY, "- Acme - registry", "30 days ago"), ("https://acme.example/", "Acme home", None)),
        text("- **Acme Glass Ltd was incorporated in 2014.**", (REGISTRY, "Acme - registry", "## Overview\n\nIncorporated on\n12 May 2014")),
        text(" It sells glass panels.", ("https://acme.example", "Acme home", "We supply glass panels"),
             ("https://news.example/acme#top", "News", "Acme, the glass panel maker")),
        text(" A different firm, Acme Ltd (UK), is "),
        text("registered in Birmingham", ("https://registry.example/other", "Acme Ltd", "Registered office: Birmingham")),
        text(".\n\nGAPS:\n- No revenue figures found\n- No staff numbers found\n"),
    ]


def test_cited_text_becomes_whole_sentence_claims():
    research = parse_research(_blocks())
    assert [c.text for c in research.claims] == [
        "Acme Glass Ltd was incorporated in 2014.",
        "It sells glass panels.",
        "A different firm, Acme Ltd (UK), is registered in Birmingham.",  # fragment expanded to its sentence
    ]
    assert [c.id for c in research.claims] == ["C1", "C2", "C3"]
    assert research.queries == ["Acme Glass Leeds"]


def test_quotes_titles_and_page_dates_are_tidied():
    research = parse_research(_blocks())
    assert research.claims[0].evidence[0].quote == "Overview Incorporated on 12 May 2014"
    assert research.sources[0].title == "Acme - registry"
    assert research.sources[0].page_age[:4].isdigit()  # "30 days ago" becomes a date


def test_sources_are_deduped_by_url_and_keep_page_age():
    research = parse_research(_blocks())
    urls = [s.url for s in research.sources]
    assert len(urls) == 4  # trailing slash and #fragment don't create duplicates
    assert [s.id for s in research.sources] == ["S1", "S2", "S3", "S4"]
    home = research.claims[1].evidence[0].source_id
    assert home == "S2"


def test_gaps_are_read_from_the_gaps_list():
    assert parse_research(_blocks()).gaps == ["No revenue figures found", "No staff numbers found"]
    assert parse_gaps("No marker here\n- not a gap") == []


def test_citations_into_a_fetched_page_use_the_exact_page_text():
    page = "Accueil. Nous fabriquons des planchers rayonnants, des plafonds chauffants et des câbles chauffants."
    start = page.index("des planchers")
    research = parse_research([
        fetched("https://acme.example/produits", "Produits", page),
        fetch_text("Acme makes radiant floors, heated ceilings and heating cables.", 0, start, len(page), "des planchers..."),
    ])
    claim = research.claims[0]
    assert claim.evidence[0].quote == page[start:]  # the full span, not the shortened snippet
    assert research.sources[0].url == "https://acme.example/produits"


def test_search_errors_do_not_break_parsing():
    error = NS(type="web_search_tool_result", content=NS(type="web_search_tool_result_error", error_code="max_uses_exceeded"))
    research = parse_research([query("x"), error, text("Nothing found.")])
    assert research.claims == [] and research.sources == []
