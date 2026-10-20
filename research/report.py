"""Write a Report to a compact .docx: a one-page overview, then details and sources."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from research.models import Item, Report

GREY = RGBColor(0x6B, 0x6B, 0x6B)
LABELS = {
    "en": {
        "facts": {"what_they_do": "What they do", "business_type": "Business type", "location": "Location",
                  "registration": "Registration", "customers": "Customers & markets", "size": "Size",
                  "identity_check": "Identity check"},
        "prepared": "Prepared {}", "confidence": "Confidence", "levels": {"high": "high", "medium": "medium", "low": "low"},
        "bottom_line": "Bottom line", "key_facts": "Key facts", "products": "Products & brands", "category": "Category",
        "recent": "Recent activity", "risks": "Risks & red flags", "unverified": "Unverified leads",
        "lead": "Lead", "why": "Why it isn't confirmed", "other": "Similarly named but different companies (not used):",
        "gaps": "Information gaps", "next": "Suggested next steps", "sources": "Sources and evidence",
        "not_found": "Not found", "none_found": "None found.",
        "kinds": {"official": "official record", "company": "company's own site", "third_party": "third party",
                  "unclassified": "unclassified"},
        "input": "Input", "method": "Method: {} searches · {} pages seen · {} cited · {} removed · model {}",
        "searches": "Searches", "company": "Company",
        "clues": {},
        "footer": "Prepared with an AI-assisted workflow. Verify key facts against the sources listed.",
        "banner": "DEMO - sample data about a fictional company, not real research",
    },
    "zh": {
        "facts": {"what_they_do": "业务概述", "business_type": "公司类型", "location": "地点", "registration": "注册信息",
                  "customers": "客户与市场", "size": "规模", "identity_check": "身份核实"},
        "prepared": "生成于 {}", "confidence": "可信度", "levels": {"high": "高", "medium": "中", "low": "低"},
        "bottom_line": "一句话结论", "key_facts": "关键信息", "products": "产品与品牌", "category": "类别",
        "recent": "近期动态", "risks": "风险与疑点", "unverified": "未核实线索",
        "lead": "线索", "why": "未证实原因", "other": "名称相近但并非同一家的公司（未采用）：",
        "gaps": "信息缺口", "next": "建议下一步", "sources": "来源与证据",
        "not_found": "未找到", "none_found": "未发现。",
        "kinds": {"official": "官方记录", "company": "公司自有网站", "third_party": "第三方", "unclassified": "未分类"},
        "input": "输入", "method": "调研方法：搜索 {} 次 · 浏览 {} 个网页 · 引用 {} 个 · 删除 {} 条 · 模型 {}",
        "searches": "搜索词", "company": "公司",
        "clues": {"Website": "网址", "Location": "地点", "Contact name": "联系人", "Job title": "职位", "Phone": "电话",
                  "Email": "邮箱", "Where we met": "认识场合", "Notes": "备注"},
        "footer": "本报告由 AI 辅助流程生成，关键事实请对照所列来源核实。",
        "banner": "DEMO 演示 - 虚构公司的样例数据，并非真实调研",
    },
}


def write_docx(report: Report, output_dir: Path) -> Path:
    lang = report.brief.language if report.brief.language in LABELS else "en"
    t = LABELS[lang]
    doc = Document()
    _set_up(doc, lang)

    if report.demo:
        p = doc.add_paragraph()
        _run(p, t["banner"], size=12, bold=True, colour=RGBColor(0xFF, 0xFF, 0xFF))
        _shade(p._p.get_or_add_pPr(), "C00000")
    p = doc.add_paragraph()
    _run(p, report.brief.company, size=16, bold=True)
    meta = [report.brief.location, report.brief.website, t["prepared"].format(date.today().isoformat()),
            f"{t['confidence']}: {t['levels'].get(report.confidence, report.confidence)}"]
    _run(doc.add_paragraph(), " · ".join(m for m in meta if m), size=9, colour=GREY)

    p = doc.add_paragraph()
    _run(p, f"{t['bottom_line']}: ", bold=True)
    for item in report.summary:
        _run(p, item.text + " ")
        _refs(p, item.refs)
        _run(p, " ")
    if report.confidence_reason:
        _run(doc.add_paragraph(), f"{t['confidence']}: {report.confidence_reason}", size=9, italic=True, colour=GREY)

    doc.add_heading(t["key_facts"], level=1)
    _table(doc, [(t["facts"].get(f.label, f.label), f) for f in report.key_facts], t["not_found"], (3.6, 14.4))
    doc.add_heading(t["products"], level=1)
    _table(doc, [(p.label, p) for p in report.products], t["none_found"], (3.6, 14.4))
    doc.add_heading(t["recent"], level=1)
    _table(doc, [(r.label or "-", r) for r in report.recent], t["none_found"], (2.6, 15.4))
    doc.add_heading(t["risks"], level=1)
    _table(doc, [("!", r) for r in report.risks], t["none_found"], (0.8, 17.2))

    leads = [u for u in report.unverified if u.label != "other"]
    others = sorted({n for u in report.unverified if u.label == "other" for n in u.refs})
    if leads or others:
        doc.add_heading(t["unverified"], level=1)
    if leads:
        table = _grid(doc, len(leads) + 1, (9, 9))
        _fill(table.cell(0, 0), t["lead"], bold=True)
        _fill(table.cell(0, 1), t["why"], bold=True)
        for i, lead in enumerate(leads, start=1):
            _fill(table.cell(i, 0), lead.text, lead.refs)
            _fill(table.cell(i, 1), lead.note, colour=GREY)
    if others:  # similarly named companies: one line, not a row each
        titles = {s.number: s.title for s in report.sources}
        p = doc.add_paragraph()
        _run(p, f"{t['other']} ", size=9, bold=True)
        _run(p, "; ".join(f"{_short(titles.get(n, ''), 60)} [{n}]" for n in others), size=9, colour=GREY)

    doc.add_paragraph()  # keeps this table from joining the one above
    table = _grid(doc, 2, (9, 9))
    for col, (title, lines) in enumerate([(t["gaps"], report.gaps), (t["next"], report.next_steps)]):
        _fill(table.cell(0, col), title, bold=True)
        cell = table.cell(1, col)
        _fill(cell, "")
        for n, line in enumerate(lines, start=1):
            _run(cell.add_paragraph() if n > 1 else cell.paragraphs[0], f"{n}. {line}" if col else f"• {line}", size=9)

    doc.add_heading(t["sources"], level=1)
    for s in report.sources:
        p = doc.add_paragraph()
        _run(p, f"[{s.number}] {_short(s.title, 100)}", size=8, bold=True)
        meta = t["kinds"].get(s.kind, s.kind) + (f", {s.page_age}" if s.page_age else "")
        _run(p, f"  ({meta})  ", size=8, colour=GREY)
        _link(p, s.url)
        if s.quotes:
            q = doc.add_paragraph()
            q.paragraph_format.left_indent = Cm(0.6)
            # Quotes from a fully read page can be long; the full text is one click away.
            _run(q, " · ".join(f"“{_short(x, 300)}”" for x in s.quotes), size=8, italic=True, colour=GREY)

    clues = [f"{t['company']}: {report.brief.company}"] + [
        f"{t['clues'].get(label, label)}: {value}" for label, value in report.brief.clues()]
    _run(doc.add_paragraph(), f"{t['input']} - " + " · ".join(clues), size=8, colour=GREY)
    _run(doc.add_paragraph(), t["method"].format(len(report.queries), report.pages_seen, len(report.sources),
                                                report.removed, report.model), size=8, colour=GREY)
    if report.queries:
        _run(doc.add_paragraph(), f"{t['searches']}: " + "; ".join(report.queries), size=8, colour=GREY)

    footer = doc.sections[0].footer.paragraphs[0]
    _run(footer, t["footer"], size=8, colour=GREY)
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"\W+", "-", report.brief.company).strip("-")[:50] or "report"
    suffix = ("_zh" if lang == "zh" else "") + ("_DEMO" if report.demo else "")
    path = output_dir / f"{slug}_{date.today().isoformat()}{suffix}.docx"
    doc.save(path)
    return path


def _set_up(doc, lang: str) -> None:
    """Narrow margins, 10pt body, small headings, tight spacing."""
    for section in doc.sections:
        section.left_margin = section.right_margin = Cm(1.8)
        section.top_margin = section.bottom_margin = Cm(1.6)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Calibri", Pt(10)
    normal.paragraph_format.space_after, normal.paragraph_format.line_spacing = Pt(2), 1.0
    heading = doc.styles["Heading 1"]
    heading.font.size = Pt(12)
    heading.paragraph_format.space_before, heading.paragraph_format.space_after = Pt(8), Pt(3)
    if lang == "zh":
        for style in (normal, heading):
            style.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Microsoft YaHei")


def _run(p, text: str, size: float | None = None, bold=False, italic=False, colour: RGBColor | None = None):
    run = p.add_run(text)
    run.bold, run.italic = bold, italic
    if size:
        run.font.size = Pt(size)
    if colour:
        run.font.color.rgb = colour
    return run


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def _refs(p, refs: list[int]) -> None:
    if refs:
        _run(p, "".join(f"[{n}]" for n in refs), size=8, colour=GREY)


def _grid(doc, rows: int, widths_cm: tuple[float, ...]):
    table = doc.add_table(rows=rows, cols=len(widths_cm))
    table.style, table.autofit = "Table Grid", False
    for row in table.rows:
        for cell, width in zip(row.cells, widths_cm):
            cell.width = Cm(width)
    return table


def _fill(cell, text: str, refs: list[int] = (), bold=False, italic=False, colour=None) -> None:
    p = cell.paragraphs[0]
    _run(p, text + (" " if refs else ""), bold=bold, italic=italic, colour=colour)
    _refs(p, list(refs))


def _table(doc, rows: list[tuple[str, Item]], empty: str, widths_cm: tuple[float, float]) -> None:
    """Two-column label | text [n] table. An item with no text shows as "Not found"."""
    if not rows:
        _run(doc.add_paragraph(), empty, italic=True, colour=GREY)
        return
    table = _grid(doc, len(rows), widths_cm)
    for (label, item), row in zip(rows, table.rows):
        _fill(row.cells[0], label, bold=True)
        _shade(row.cells[0]._tc.get_or_add_tcPr(), "F2F2F2")
        if item.text:
            _fill(row.cells[1], item.text, item.refs)
        else:
            _fill(row.cells[1], empty, italic=True, colour=GREY)


def _shade(properties, fill: str) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:fill"), fill)
    properties.append(shading)


def _link(paragraph, url: str) -> None:
    """Add a clickable hyperlink (python-docx has no public API for this)."""
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True))
    run, props = OxmlElement("w:r"), OxmlElement("w:rPr")
    for tag, val in (("w:color", "0563C1"), ("w:u", "single"), ("w:sz", "16")):
        el = OxmlElement(tag)
        el.set(qn("w:val"), val)
        props.append(el)
    text = OxmlElement("w:t")
    text.text = url
    run.append(props)
    run.append(text)
    link.append(run)
    paragraph._p.append(link)
