"""Write a Report to a formatted .docx file."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from research.models import Bullet, Report

LABELS = {
    "en": {
        "title": "Company research: {}", "prepared": "Prepared {} · model: {}", "clues": "Input clues",
        "company": "Company", "summary": "Summary", "confidence": "Confidence",
        "levels": {"high": "High", "medium": "Medium", "low": "Low"},
        "none": "No verified information found.", "unverified": "Unverified leads",
        "unverified_intro": "Mentioned in a source, but the quoted text does not confirm it. Check before using.",
        "gaps": "Information gaps", "next": "Suggested next steps", "sources": "Sources and evidence",
        "kinds": {"official": "official record", "company": "company's own site",
                  "third_party": "third party", "unclassified": "unclassified"},
        "page_date": "page date", "method": "Method", "searches": "Searches run:",
        "removed": "{} statement(s) removed because no source supported them.",
        "footer": "Prepared with an AI-assisted workflow. Verify key facts against the sources listed.",
        "banner": "DEMO - sample data about a fictional company, not real research",
    },
    "zh": {
        "title": "公司调研报告：{}", "prepared": "生成日期 {} · 模型：{}", "clues": "输入线索",
        "company": "公司", "summary": "结论摘要", "confidence": "可信度",
        "levels": {"high": "高", "medium": "中", "low": "低"},
        "none": "未找到经核实的信息。", "unverified": "未核实线索",
        "unverified_intro": "来源中提到，但引用原文无法证实。使用前请自行核实。",
        "gaps": "信息缺口", "next": "建议下一步", "sources": "来源与证据",
        "kinds": {"official": "官方记录", "company": "公司自有网站", "third_party": "第三方", "unclassified": "未分类"},
        "page_date": "页面日期", "method": "调研方法", "searches": "执行的搜索：",
        "removed": "已删除 {} 条没有来源支持的内容。",
        "footer": "本报告由 AI 辅助流程生成，关键事实请对照所列来源核实。",
        "banner": "DEMO 演示 - 虚构公司的样例数据，并非真实调研",
    },
}
CLUES_ZH = {"Website": "网址", "Location": "地点", "Contact name": "联系人", "Job title": "职位",
            "Phone": "电话", "Email": "邮箱", "Where we met": "认识场合", "Notes": "备注"}


def write_docx(report: Report, output_dir: Path) -> Path:
    lang = report.brief.language if report.brief.language in LABELS else "en"
    t = LABELS[lang]
    doc = Document()
    if lang == "zh":
        for name in ("Normal", "Title", "Heading 1"):
            doc.styles[name].element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Microsoft YaHei")

    if report.demo:
        _banner(doc, t["banner"])
    doc.add_heading(t["title"].format(report.brief.company), level=0)
    doc.add_paragraph(t["prepared"].format(date.today().isoformat(), report.model))

    doc.add_heading(t["clues"], level=1)
    doc.add_paragraph(f"{t['company']}: {report.brief.company}", style="List Bullet")
    for label, value in report.brief.clues():
        doc.add_paragraph(f"{CLUES_ZH.get(label, label) if lang == 'zh' else label}: {value}", style="List Bullet")

    doc.add_heading(t["summary"], level=1)
    _bullets(doc, report.summary, t["none"])
    p = doc.add_paragraph()
    p.add_run(f"{t['confidence']}: {t['levels'].get(report.confidence, report.confidence)}").bold = True
    if report.confidence_reason:
        p.add_run(f" - {report.confidence_reason}")

    for section in report.sections:
        doc.add_heading(section.heading, level=1)
        _bullets(doc, section.bullets, t["none"])

    if report.unverified:
        doc.add_heading(t["unverified"], level=1)
        doc.add_paragraph().add_run(t["unverified_intro"]).italic = True
        _bullets(doc, report.unverified, t["none"])
    _plain_list(doc, t["gaps"], report.gaps, "List Bullet")
    _plain_list(doc, t["next"], report.next_steps, "List Number")

    doc.add_heading(t["sources"], level=1)
    for s in report.sources:
        p = doc.add_paragraph()
        p.add_run(f"[{s.number}] {s.title}").bold = True
        meta = t["kinds"].get(s.kind, s.kind) + (f", {t['page_date']} {s.page_age}" if s.page_age else "")
        p.add_run(f"  ({meta})")
        _link(doc.add_paragraph(), s.url)
        for quote in s.quotes:
            q = doc.add_paragraph()
            q.paragraph_format.left_indent = Pt(18)
            q.add_run(f"“{quote}”").italic = True

    doc.add_heading(t["method"], level=1)
    _plain_list(doc, None, report.queries, "List Bullet", intro=t["searches"])
    if report.removed:
        doc.add_paragraph(t["removed"].format(report.removed))

    doc.sections[0].footer.paragraphs[0].text = t["footer"]
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"\W+", "-", report.brief.company).strip("-")[:50] or "report"
    suffix = ("_zh" if lang == "zh" else "") + ("_DEMO" if report.demo else "")
    path = output_dir / f"{slug}_{date.today().isoformat()}{suffix}.docx"
    doc.save(path)
    return path


def _bullets(doc, bullets: list[Bullet], empty: str) -> None:
    if not bullets:
        doc.add_paragraph().add_run(empty).italic = True
    for b in bullets:
        refs = "".join(f"[{n}]" for n in b.refs)
        doc.add_paragraph(f"{b.text} {refs}" + (f" - {b.note}" if b.note else ""), style="List Bullet")


def _plain_list(doc, heading: str | None, items: list[str], style: str, intro: str = "") -> None:
    if not items:
        return
    if heading:
        doc.add_heading(heading, level=1)
    if intro:
        doc.add_paragraph(intro)
    for item in items:
        doc.add_paragraph(item, style=style)


def _banner(doc, text: str) -> None:
    """A white-on-red paragraph across the top of the first page."""
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold, run.font.size, run.font.color.rgb = True, Pt(14), RGBColor(0xFF, 0xFF, 0xFF)
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:fill"), "C00000")
    p._p.get_or_add_pPr().append(shading)


def _link(paragraph, url: str) -> None:
    """Add a clickable hyperlink (python-docx has no public API for this)."""
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True))
    run, props = OxmlElement("w:r"), OxmlElement("w:rPr")
    for tag, val in (("w:color", "0563C1"), ("w:u", "single")):
        el = OxmlElement(tag)
        el.set(qn("w:val"), val)
        props.append(el)
    text = OxmlElement("w:t")
    text.text = url
    run.append(props)
    run.append(text)
    link.append(run)
    paragraph._p.append(link)
