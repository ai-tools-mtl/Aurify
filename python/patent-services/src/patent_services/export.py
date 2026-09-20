"""Patent project → docx/pdf export.

The disclosure exporter generates on top of the agency's own 交底书 template
(``assets/disclosure-template.docx``, namespace-normalized from the 合肥和瑞
original): the template carries the page geometry, the 专利申请技术交底书
header, and the inventor information table (its footer is blanked on
export); the chapters fill the template's eight sections in its typography
(楷体_GB2312 四号, 1.5 line spacing). ``brief.md`` stays out — its content
is the same eight sections in summary form, and the template has no slot
for it.

The application exporter emits the CNIPA document set in the submitted
package's shape: one Word section per document — 说明书摘要, 权利要求书,
说明书 — each carrying its document-type label in a centered bottom-bordered
header (the body has no title paragraphs; 说明书 opens with the centered
invention name and bold section headings). Body text is 宋体 四号, 1.5 line
spacing, first-line two-character indent, no page numbers. Claims fold back
into one paragraph per numbered claim — the Markdown source's continuation
lines are readability line breaks, not paragraphs.

Markdown folding is shared: ``#`` lines carry structure the export supplies
itself, ``##`` lines become unindented sub-paragraphs, ``- `` bullets and
emphasis markers dissolve into plain paragraphs. PDF export is best-effort:
weasyprint needs system GTK libraries, so an unavailable install fails loud
with guidance instead of producing a broken file.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

import yaml
from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml.parser import OxmlElement
from docx.shared import Cm, Pt

from .fingerprint import source_fingerprint

#: A Markdown chapter file's level-1 heading, or None when the file opens
#: with other content and the filename provides the heading.
_HEADING1 = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_BULLET = re.compile(r"^[-*]\s+(.*)$")
_EMPHASIS = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CLAIM = re.compile(r"^\d+[.、]\s*")

#: The agency disclosure template shipped as the disclosure export's base
#: document (identical to the agency original except for the ISO-strict →
#: transitional namespace normalization WPS's save left it in).
DISCLOSURE_TEMPLATE = Path(__file__).with_name("assets") / "disclosure-template.docx"

#: The template's eight sections in template order, keyed by chapter-file
#: slug (the stem minus its ``NN-`` prefix). Headings quote the template.
DISCLOSURE_SECTIONS = (
    ("name", "名称："),
    ("field", "所属技术领域："),
    ("background", "背景技术："),
    ("problem", "现有技术的缺点是什么？针对这些缺点，说明本发明要解决的技术问题："),
    ("solution", "发明内容（应该结合图形详细阐述该技术方案）："),
    ("effect", "有益效果"),
    ("key-points", "本发明的关键点和欲保护点是什么？"),
    ("drawings", "附图"),
)

#: The disclosure template's body typography: 楷体_GB2312 四号. Latin text
#: rides Times New Roman — the template docDefaults' ascii font, set
#: run-explicitly so exports built from a blank document inherit it too.
LATIN_FONT = "Times New Roman"
DISCLOSURE_FONT = "楷体_GB2312"
DISCLOSURE_SIZE = Pt(14)

#: The bullet marker for Markdown list items — GB2312-safe so the template
#: fonts render it without substitution.
BULLET_MARK = "●"

_CHINESE_DIGITS = "零一二三四五六七八九"

#: Figure images live at the figures root (``figures/图N.png`` — sources in
#: ``figures/source/`` are not deliverables). Bare ``图N.png`` and suffixed
#: ``图N-名称.png`` names both count; anything else (previews, sources) never
#: embeds, so a naming miss shows up as a zero-figure export rather than a
#: silent half-deliverable.
_FIGURE_FILE = re.compile(r"^图(\d+)(?:-.+)?\.png$", re.IGNORECASE)

#: One 附图说明 chapter line naming a figure: ``图1 为本发明所述方法的流程总览图；``
_FIGURE_CAPTION = re.compile(r"图(\d+)\s*[为是][:：]?\s*([^；。\n]+)")

#: Figure-like names at the figures root that the strict contract rejects
#: (``图3.jpg``, ``图 4.png``) — named in the export warning because they
#: embed nothing yet look like figures to a human.
_FIGURE_LOOKALIKE = re.compile(r"^图\s*\d+")

#: Embedded figure width on export — fits the template's text column with margin.
FIGURE_WIDTH = Cm(14)


def _collect_figures(root: Path) -> list[tuple[int, Path, str | None]]:
    """Collect the project's final figure images in figure-number order.

    Only top-level ``figures/图N.png`` files count (the directory convention
    keeps editable sources under ``figures/source/`` and intermediates under
    ``figures/tmp/``). Captions come from ``chapters/08-drawings.md``'s
    ``图N 为……`` lines; a figure without a matching line carries no caption.
    """
    figures_dir = root / "figures"
    if not figures_dir.is_dir():
        return []
    numbered: list[tuple[int, Path]] = []
    for path in figures_dir.glob("*.png"):
        if (match := _FIGURE_FILE.match(path.name)) is not None:
            numbered.append((int(match.group(1)), path))
    numbered.sort()
    captions: dict[int, str] = {}
    drawings = root / "chapters" / "08-drawings.md"
    if drawings.is_file():
        for match in _FIGURE_CAPTION.finditer(drawings.read_text(encoding="utf-8")):
            captions.setdefault(int(match.group(1)), match.group(2).strip())
    return [(number, path, captions.get(number)) for number, path in numbered]


def _export_summary(written: str, root: Path) -> str:
    """Describe an export's embedded figure set so a silent zero-figure
    deliverable cannot pass for complete: the returned path carries the
    collected count, plus a warning naming exactly which declared figures are
    missing and which files at the figures root look like figures but never
    matched the naming contract (图3.jpg, 图 3.png — they embed nothing)."""
    figures = _collect_figures(root)
    figures_dir = root / "figures"
    drawings = root / "chapters" / "08-drawings.md"
    declared: set[int] = set()
    if drawings.is_file():
        declared = {int(m.group(1)) for m in _FIGURE_CAPTION.finditer(drawings.read_text(encoding="utf-8"))}
    collected = {number for number, _, _ in figures}
    missing = sorted(declared - collected)
    mismatched = sorted(
        path.name for path in figures_dir.iterdir()
        if path.is_file() and _FIGURE_LOOKALIKE.match(path.name) and not _FIGURE_FILE.match(path.name)
    ) if figures_dir.is_dir() else []
    notes: list[str] = []
    if missing:
        notes.append(f"缺 图{'、图'.join(str(n) for n in missing)}（成品须命名 图N.png 或 图N-名称.png），缺的图没有进文档")
    if mismatched:
        notes.append(f"疑似附图但命名未收录：{'、'.join(mismatched)}")
    note = "".join(f"；警告：{note}" for note in notes)
    return f"{written}（内嵌附图 {len(figures)} 张{note}）"


#: The review score line a report carries: ``总分 81``.
_REVIEW_SCORE = re.compile(r"总分\s*(\d+)")

#: The scope stamp marking a report as partial (never the whole-project verdict).
_REVIEW_PARTIAL = "审查范围：部分"

#: The degradation marker in reference/prior-art.md that relaxes the bar.
_PRIOR_ART_UNAVAILABLE = "查新不可用"

#: Default score bar, mirroring the loop assessor's (patent.yml reviewThreshold overrides).
_REVIEW_THRESHOLD = 80

#: How far the bar drops while the prior-art search is marked unreachable.
_DEGRADED_DELTA = 10


def review_gate_warning(root: Path) -> str:
    """Warn when the disclosure export goes out before the review score gate
    passed — a soft guard, not a blocker: the loop tool stays the authority,
    this only keeps an unreviewed export from presenting itself as final.

    Mirrors the loop's rule: newest ``*.review.md`` wins, a partial-scope
    report is no verdict, ``reviewThreshold`` in patent.yml overrides the
    default bar, and the 查新不可用 marker relaxes it by ten. A pass under
    the relaxed bar still warns — the unrefreshed prior-art debt travels
    with the deliverable.
    """
    review_dir = root / "review"
    reports = sorted(review_dir.glob("*.review.md")) if review_dir.is_dir() else []
    if not reports:
        return "提醒：review/ 下还没有审查报告——交底书尚未过审查分数门，建议先跑 patent_review 审查达标后再交付。"
    latest = max(reports, key=lambda path: path.stat().st_mtime)
    text = latest.read_text(encoding="utf-8")
    score_match = _REVIEW_SCORE.search(text)
    if score_match is None:
        return f"提醒：最新审查报告 {latest.name} 没有可解析的总分——重跑审查后再交付。"
    if _REVIEW_PARTIAL in text:
        return f"提醒：最新审查报告 {latest.name} 只覆盖局部目标——整项审查未过，交底书可能尚未达标。"
    threshold = _REVIEW_THRESHOLD
    manifest_path = root / "patent.yml"
    if manifest_path.is_file():
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        configured = manifest.get("reviewThreshold")
        if isinstance(configured, (int, float)) and 0 <= configured <= 100:
            threshold = int(configured)
    prior_art = root / "reference" / "prior-art.md"
    degraded = prior_art.is_file() and _PRIOR_ART_UNAVAILABLE in prior_art.read_text(encoding="utf-8")
    effective = max(0, threshold - _DEGRADED_DELTA) if degraded else threshold
    score = int(score_match.group(1))
    if score < effective:
        relaxed = "（查新不可用，已放宽 10 分）" if degraded else ""
        return f"提醒：最新审查总分 {score} 低于达标线 {effective}{relaxed}——导出物未达审查线，建议修订重审后再交付。"
    if degraded:
        return (
            "提醒：交底书带着未清偿的查新降级债——审查按放宽 10 分的达标线放行（检索通道当时不可用）。"
            "通道恢复后按 patent-research 补检索 reference/prior-art.md、删除「查新不可用」标记，"
            "并把分数审回未放宽的达标线。"
        )
    return ""


def disclosure_absent_warning(root: Path) -> str:
    """Warn when the application set exports while the disclosure (the default
    deliverable) was never exported — the application set has its own
    preconditions, and skipping the disclosure must be a visible choice."""
    exports_dir = root / "exports"
    if exports_dir.is_dir() and any(exports_dir.glob("*-交底书.docx")):
        return ""
    return "提醒：exports/ 下还没有交底书导出物（默认交付物）——确认跳过交底书直接导申请文件是有意推进。"


def _add_figure(document, path: Path, number: int, caption: str | None, *, east_asia: str, size: Pt) -> None:
    """Append one centered figure with its 图N label (and caption) below.

    The insertion discipline from the figure-design skill: the 图N label sits
    below the image, centered — never inside the image, never above it. The
    image and label paragraphs carry keep-with-next so a page break can never
    separate a figure body from its 图N label and caption.
    """
    document.add_picture(str(path), width=FIGURE_WIDTH)
    picture_paragraph = document.paragraphs[-1]
    picture_paragraph.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    picture_paragraph.paragraph_format.keep_with_next = True
    _add_paragraph(document, f"图{number}", east_asia=east_asia, size=size, indent=None, centered=True)
    document.paragraphs[-1].paragraph_format.keep_with_next = True
    if caption:
        _add_paragraph(document, caption, east_asia=east_asia, size=size, indent=None, centered=True)


def _plain(markdown_text: str) -> str:
    """Strip Markdown emphasis markers for plain text output."""
    return _EMPHASIS.sub(lambda match: match.group(1) or match.group(2) or match.group(3) or "", markdown_text)


def _light(markdown_text: str) -> str:
    """Strip single-emphasis and code markers, keeping ``**bold**`` spans
    for :func:`_emphasis_runs` to turn into bold runs."""
    return re.sub(r"(?<!\*)\*(?!\*)|`", "", markdown_text)


def _emphasis_runs(markdown_text: str) -> list[tuple[str, bool]]:
    """Split Markdown text into (text, bold) runs.

    ``**bold**`` survives as a bold run — the deliverable keeps the
    drafting emphasis; single ``*`` and `` `` markers dissolve.
    """
    runs: list[tuple[str, bool]] = []
    for index, segment in enumerate(_BOLD.split(markdown_text)):
        segment = _EMPHASIS.sub(lambda match: match.group(1) or match.group(2) or match.group(3) or "", segment)
        if segment:
            runs.append((segment, index % 2 == 1))
    return runs


def _chinese_numeral(number: int) -> str:
    """Render 1..99 as a Chinese numeral (一, 八, 十一, 二十三); else digits."""
    if not 1 <= number <= 99:
        return str(number)
    tens, ones = divmod(number, 10)
    parts = []
    if tens == 1:
        parts.append("十")
    elif tens > 1:
        parts.append(_CHINESE_DIGITS[tens] + "十")
    if ones:
        parts.append(_CHINESE_DIGITS[ones])
    return "".join(parts)


def _chapter_title(path: Path, body: str) -> str:
    heading = _HEADING1.search(body)
    if heading is not None:
        return heading.group(1).strip()
    return path.stem


def _add_paragraph(document, text: str, *, east_asia: str, size: Pt, indent: str | None = "first",
                   centered: bool = False, page_break_before: bool = False, bold: bool = False,
                   space_before: Pt | None = None):
    """Append one paragraph in the target typography and return it.

    ``indent``: ``"first"`` sets the two-character first-line indent,
    ``"bullet"`` a one-character hanging indent under a three-character left
    edge (for the ``●`` marker), ``None`` no indent. Spacing is 1.5 lines
    with no before/after unless ``space_before``; ``bold`` and any
    ``**bold**`` spans in ``text`` become bold runs.
    """
    paragraph = document.add_paragraph()
    format_ = paragraph.paragraph_format
    format_.line_spacing = 1.5
    format_.space_before = space_before or Pt(0)
    format_.space_after = Pt(0)
    if page_break_before:
        format_.page_break_before = True
    if centered:
        format_.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if indent:
        ind = paragraph._p.get_or_add_pPr().get_or_add_ind()
        if indent == "bullet":
            ind.set(qn("w:leftChars"), "300")
            ind.set(qn("w:left"), str(size.twips * 3))
            ind.set(qn("w:hangingChars"), "100")
            ind.set(qn("w:hanging"), str(size.twips))
        else:
            ind.set(qn("w:firstLineChars"), "200")
            ind.set(qn("w:firstLine"), str(size.twips * 2))
    for segment_text, segment_bold in (_emphasis_runs(text) or [(text, False)]):
        run = paragraph.add_run(segment_text)
        rfonts = run._element.get_or_add_rPr().get_or_add_rFonts()
        rfonts.set(qn("w:ascii"), LATIN_FONT)
        rfonts.set(qn("w:hAnsi"), LATIN_FONT)
        rfonts.set(qn("w:eastAsia"), east_asia)
        rfonts.set(qn("w:hint"), "eastAsia")
        run.font.size = size
        if bold or segment_bold:
            run.font.bold = True
    return paragraph


def _markdown_paragraphs(body: str, *, keep_subheadings: bool) -> list[tuple[str, str]]:
    """Fold a Markdown body into (text, kind) paragraphs.

    Kind is ``"subheading"`` (a ``## `` line, unindented and bold),
    ``"bullet"`` (a ``- `` line, rendered with the ``●`` marker), or
    ``"paragraph"`` (plain, first-line indent). ``# `` lines carry structure
    the export supplies itself and are dropped.
    """
    paragraphs: list[tuple[str, str]] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("# "):
            continue
        if keep_subheadings and line.startswith("## "):
            paragraphs.append((_plain(line[3:].strip()), "subheading"))
        elif (bullet := _BULLET.match(line)) is not None:
            paragraphs.append((_light(bullet.group(1)), "bullet"))
        else:
            paragraphs.append((_light(line), "paragraph"))
    return paragraphs


def _claim_paragraphs(body: str) -> list[str]:
    """Fold the claims source into one paragraph per numbered claim."""
    claims: list[str] = []
    for raw_line in body.splitlines():
        line = _plain(raw_line.strip())
        if not line or line.startswith("#"):
            continue
        if _CLAIM.match(line) or not claims:
            claims.append(line)
        else:
            claims[-1] += line
    return claims


def _collect_disclosure_sections(root: Path) -> list[tuple[str, str]]:
    """Map ``chapters/*.md`` onto the template's sections, in template order.

    Chapters whose slug is not one of the eight template sections append as
    extra numbered sections in file order.
    """
    chapters = root / "chapters"
    if not chapters.is_dir():
        return []
    known_slugs = {key for key, _ in DISCLOSURE_SECTIONS}
    matched: dict[str, str] = {}
    extras: list[tuple[Path, str]] = []
    for path in sorted(chapters.glob("*.md")):
        body = path.read_text(encoding="utf-8")
        slug = path.stem.split("-", 1)[1] if "-" in path.stem else path.stem
        if slug in known_slugs:
            matched[slug] = body
        else:
            extras.append((path, body))
    sections = [(heading, matched[key]) for key, heading in DISCLOSURE_SECTIONS if key in matched]
    sections.extend((_chapter_title(path, body), body) for path, body in extras)
    return sections


def _blank_footer(footer) -> None:
    """Drop a footer's content, keeping one empty paragraph (schema minimum)."""
    footer.is_linked_to_previous = False
    for paragraph in list(footer.paragraphs):
        paragraph._element.getparent().remove(paragraph._element)
    for table in list(footer.tables):
        table._element.getparent().remove(table._element)
    footer.add_paragraph()


def _template_document() -> Document:
    """Open the agency template and strip its guidance text, keeping the
    inventor table and the section (page geometry, header). The template's
    footer — page number, agency name, logo — is blanked on export: the
    deliverable leaves without the agency's branding."""
    document = Document(str(DISCLOSURE_TEMPLATE))
    body = document.element.body
    table = body.find(qn("w:tbl"))
    if table is None:
        raise RuntimeError(f"disclosure template is missing the inventor table: {DISCLOSURE_TEMPLATE}")
    for child in list(body):
        if child is not table and child.tag != qn("w:sectPr"):
            body.remove(child)
    section = document.sections[0]
    for footer in (section.footer, section.even_page_footer):
        _blank_footer(footer)
    return document


def _markdown_to_html(body: str, *, keep_subheadings: bool = True,
                      images: list[tuple[int, Path, str | None]] | None = None) -> str:
    """Render one Markdown body to simple HTML for weasyprint; ``images``
    (when given) append as centered ``<img>`` + 图N caption blocks after the
    text — the HTML path of the insertion discipline."""
    parts: list[str] = []
    for text, kind in _markdown_paragraphs(body, keep_subheadings=keep_subheadings):
        if kind == "subheading":
            parts.append(f"<h3>{escape(text)}</h3>")
        elif kind == "bullet":
            text = f"{BULLET_MARK} {text}"
        runs = "".join(f"<strong>{escape(segment)}</strong>" if bold else escape(segment)
                       for segment, bold in _emphasis_runs(text))
        if kind != "subheading":
            parts.append(f"<p>{runs}</p>")
    for number, path, caption in images or []:
        parts.append(f"<p style='text-align:center'><img src='{escape(path.resolve().as_uri())}' "
                     f"style='width:{FIGURE_WIDTH.cm}cm'></p>")
        parts.append(f"<p style='text-align:center'>图{number}</p>")
        if caption:
            parts.append(f"<p style='text-align:center'>{escape(caption)}</p>")
    return "\n".join(parts)


_PDF_CSS = (
    "<style>body{font-family:'KaiTi','楷体_GB2312',Kaiti SC,serif;font-size:14pt;}"
    "h2{font-size:14pt;}" "h3{font-size:14pt;font-weight:normal;}"
    "p{line-height:1.5;text-indent:2em;margin:0;}</style>"
)


def _word_com_pdf(docx_path: Path, pdf_path: Path) -> tuple[bool, str | None]:
    """Convert one docx to pdf via hidden-window Word COM (Windows).

    Returns ``(True, None)`` on success, ``(False, None)`` when Word or
    pywin32 is simply unavailable (the caller falls back to weasyprint), or
    ``(False, detail)`` when Word was present but the conversion failed.
    """
    try:
        import win32com.client  # noqa: PLC0415 - optional Windows-only dependency
    except ImportError:
        return False, None
    word = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Open(str(docx_path), ReadOnly=True)
        document.SaveAs2(str(pdf_path), FileFormat=17)
        document.Close(False)
        document = None
    except Exception as error:  # noqa: BLE001 - any COM failure is a fallback signal
        return False, str(error)
    finally:
        if word is not None:
            word.Quit()
    return pdf_path.is_file(), None


_WEASYPRINT_UNAVAILABLE = (
    "PDF 导出需要 Word（Windows，自动转换）或 weasyprint 及其 GTK 系统库，当前环境两者都不可用；"
    "请先导出 docx 后用 Word 另存为 PDF，或在安装 weasyprint 后重试。"
)


def export_project(project_dir: str, fmt: str = "docx") -> str:
    """Export one patent project to ``exports/<name>-交底书.<fmt>`` on the
    agency template.

    The chapters fill the template's eight sections (一、名称 through 八、附图)
    in template order; chapters outside the eight append as extra numbered
    sections. Returns the written file's path. Raises ``ValueError`` for an
    unknown format, a directory without ``patent.yml``, or a project with no
    chapters, and ``RuntimeError`` with install guidance when PDF export is
    requested without weasyprint.
    """
    if fmt not in ("docx", "pdf"):
        raise ValueError(f"unknown export format: {fmt}")
    root = Path(project_dir)
    manifest_path = root / "patent.yml"
    if not manifest_path.is_file():
        raise ValueError(f"not a patent project (missing patent.yml): {root}")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    name = str(manifest.get("name") or root.name)

    sections = _collect_disclosure_sections(root)
    if not sections:
        raise ValueError(f"nothing to export (no chapters/*.md): {root}")

    exports_dir = root / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    figures = _collect_figures(root)
    docx_path = _build_disclosure_docx(root, exports_dir, name, sections, figures)

    if fmt == "docx":
        return str(docx_path)

    # PDF: hidden-window Word COM first (the template's typography survives
    # verbatim); weasyprint's HTML re-render is the non-Windows fallback, and
    # the docx stays beside the pdf either way.
    pdf_path = exports_dir / f"{name}-交底书.pdf"
    converted, detail = _word_com_pdf(docx_path, pdf_path)
    if converted:
        return str(pdf_path)
    try:
        from weasyprint import HTML
    except ImportError as cause:
        raise RuntimeError(_WEASYPRINT_UNAVAILABLE + (f"（Word 转换失败：{detail}）" if detail else "")) from cause
    html = [f"<html><head><meta charset='utf-8'><title>{escape(name)}</title>{_PDF_CSS}</head><body>"]
    for heading, body in sections:
        html.append(f"<h2>{escape(heading)}</h2>")
        html.append(_markdown_to_html(body, images=figures))
    html.append("</body></html>")
    HTML(string="\n".join(html), base_url=str(root)).write_pdf(str(pdf_path))
    return str(pdf_path)

def _build_disclosure_docx(root: Path, exports_dir: Path, name: str, sections: list[tuple[str, str]],
                           figures: list[tuple[int, Path, str | None]]) -> Path:
    """Build the disclosure docx on the agency template and return its path."""
    document = _template_document()
    figures = _collect_figures(root)
    for index, (heading, body) in enumerate(sections, start=1):
        _add_paragraph(document, f"{_chinese_numeral(index)}、{heading}",
                       east_asia=DISCLOSURE_FONT, size=DISCLOSURE_SIZE, bold=True, space_before=Pt(10))
        for text, kind in _markdown_paragraphs(body, keep_subheadings=True):
            if kind == "subheading":
                _add_paragraph(document, text, east_asia=DISCLOSURE_FONT, size=DISCLOSURE_SIZE,
                               indent=None, bold=True, space_before=Pt(6))
            elif kind == "bullet":
                _add_paragraph(document, f"{BULLET_MARK} {text}", east_asia=DISCLOSURE_FONT,
                               size=DISCLOSURE_SIZE, indent="bullet")
            else:
                _add_paragraph(document, text, east_asia=DISCLOSURE_FONT, size=DISCLOSURE_SIZE, indent="first")
        if heading == "附图":
            for number, path, caption in figures:
                _add_figure(document, path, number, caption, east_asia=DISCLOSURE_FONT, size=DISCLOSURE_SIZE)
    if figures and all(existing_heading != "附图" for existing_heading, _ in sections):
        _add_paragraph(document, f"{_chinese_numeral(len(sections) + 1)}、附图",
                       east_asia=DISCLOSURE_FONT, size=DISCLOSURE_SIZE, bold=True, space_before=Pt(10))
        for number, path, caption in figures:
            _add_figure(document, path, number, caption, east_asia=DISCLOSURE_FONT, size=DISCLOSURE_SIZE)
    output = exports_dir / f"{name}-交底书.docx"
    document.save(output)
    # The loop's export gate reads this digest sidecar instead of trusting
    # mtimes (see fingerprint.py for the cross-language contract).
    (exports_dir / f"{name}-交底书.fingerprint").write_bytes(source_fingerprint(root).encode("ascii"))
    return str(output)


#: The application document set in the submitted package's order: 说明书摘要,
#: 权利要求书, 说明书 (the package's two figure documents — 摘要附图,
#: 说明书附图 — have no source under application/ and are skipped).
APPLICATION_FILES = ("abstract.md", "claims.md", "description.md")


def _collect_application(root: Path) -> list[tuple[str, str]]:
    """Read the application/ document set in fixed order; missing files skip."""
    application = root / "application"
    sources: list[tuple[str, str]] = []
    for filename in APPLICATION_FILES:
        path = application / filename
        if path.is_file():
            sources.append((filename, path.read_text(encoding="utf-8")))
    return sources


#: The Chinese document-set heading each application file exports under.
APPLICATION_TITLES = {
    "claims.md": "权利要求书", "description.md": "说明书", "abstract.md": "说明书摘要",
    "abstract-figures": "摘要附图", "figures": "说明书附图",
}

#: The document-type label each application section carries in its centered,
#: bottom-bordered header, copied verbatim (spacing included) from the
#: submitted package; the body carries no title paragraphs.
APPLICATION_HEADERS = {
    "abstract.md": "说  明  书  摘  要",
    "claims.md": "权   利   要   求   书",
    "description.md": "说    明    书",
    "abstract-figures": "摘  要  附  图",
    "figures": "说  明  书  附  图",
}

#: The sections that restart page numbering in the submitted package.
_APPLICATION_RESTARTS_PAGES = {"claims.md", "description.md"}

#: The application set's typography: 黑体 四号 section labels in the header,
#: 宋体 四号 body (Latin in Times New Roman).
APPLICATION_FONT = "宋体"
APPLICATION_HEADER_FONT = "黑体"
APPLICATION_SIZE = Pt(14)


def _application_document() -> Document:
    """A blank document in the submitted package's shape: A4 with 2.5/1.5/
    2.5/1.5 margins, a 312 line grid, Times New Roman + 宋体 defaults, and
    no footer (the package shows no page numbers)."""
    document = Document()
    style = document.styles["Normal"]
    style.font.name = LATIN_FONT
    style.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), APPLICATION_FONT)
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(2.5), Cm(1.5)
    section.left_margin, section.right_margin = Cm(2.5), Cm(1.5)
    section.header_distance, section.footer_distance = Cm(1.5), Cm(1.75)
    doc_grid = section._sectPr.find(qn("w:docGrid"))
    if doc_grid is None:
        doc_grid = OxmlElement("w:docGrid")
        section._sectPr.append(doc_grid)
    doc_grid.set(qn("w:linePitch"), "312")
    return document


def _label_header(section, label: str) -> None:
    """Give one section the centered, bottom-bordered document-type label."""
    header = section.header
    header.is_linked_to_previous = False
    paragraph = header.paragraphs[0]
    paragraph.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    ppr = paragraph._p.get_or_add_pPr()
    p_border = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for key, value in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "auto")):
        bottom.set(qn(key), value)
    p_border.append(bottom)
    jc = ppr.find(qn("w:jc"))
    if jc is not None:
        jc.addprevious(p_border)
    else:
        ppr.append(p_border)
    run = paragraph.add_run(label)
    rfonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    for key in ("w:ascii", "w:hAnsi", "w:eastAsia"):
        rfonts.set(qn(key), APPLICATION_HEADER_FONT)
    rfonts.set(qn("w:hint"), "eastAsia")
    run.font.size = APPLICATION_SIZE


def export_application(project_dir: str, fmt: str = "docx") -> str:
    """Export the application document set to ``exports/<name>-申请文件.<fmt>``.

    The application files export in the submitted package's shape: one Word
    section per document — 说明书摘要, 权利要求书 (one paragraph per numbered
    claim, continuation lines folded in), 说明书 (opening with the centered
    invention name, bold unindented section headings) — each carrying its
    document-type label in a centered header, in 宋体 四号 with a two-character
    first-line indent; 权利要求书 and 说明书 restart page numbering, and no
    page numbers are shown. When the project has final figure images, the
    submitted package's two figure documents join the set: 摘要附图 (图1)
    after the abstract and 说明书附图 (all figures, 图N labeled below each
    image) after the description. Returns the written file's path. Raises
    ``ValueError`` for an unknown format, a directory without ``patent.yml``,
    or a project without any application file; PDF converts through
    hidden-window Word COM (falling back to weasyprint) exactly like
    :func:`export_project`.
    """
    if fmt not in ("docx", "pdf"):
        raise ValueError(f"unknown export format: {fmt}")
    root = Path(project_dir)
    manifest_path = root / "patent.yml"
    if not manifest_path.is_file():
        raise ValueError(f"not a patent project (missing patent.yml): {root}")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    name = str(manifest.get("name") or root.name)

    sources: list[tuple[str, str | None]] = _collect_application(root)
    if not sources:
        raise ValueError(f"nothing to export (no application document set): {root}")
    figures = _collect_figures(root)
    if figures:
        # The submitted package's two figure documents: 图1 rides beside the
        # abstract (摘要附图), the full set closes the 说明书 (说明书附图).
        sources = [(key, body) for key, body in sources]
        abstract_at = next((i for i, (key, _) in enumerate(sources) if key == "abstract.md"), len(sources) - 1)
        sources.insert(abstract_at + 1, ("abstract-figures", None))
        sources.append(("figures", None))

    exports_dir = root / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    docx_path = _build_application_docx(root, exports_dir, name, sources, figures)

    if fmt == "docx":
        return str(docx_path)

    pdf_path = exports_dir / f"{name}-申请文件.pdf"
    converted, detail = _word_com_pdf(docx_path, pdf_path)
    if converted:
        return str(pdf_path)
    try:
        from weasyprint import HTML
    except ImportError as cause:
        raise RuntimeError(_WEASYPRINT_UNAVAILABLE + (f"（Word 转换失败：{detail}）" if detail else "")) from cause
    html = [f"<html><head><meta charset='utf-8'><title>{escape(name)}</title>{_PDF_CSS}</head><body>"]
    for index, (key, body) in enumerate(sources):
        html.append(f"<h1 style='page-break-before:{'always' if index else 'auto'};text-align:center'>"
                    f"{escape(APPLICATION_TITLES[key])}</h1>")
        if key == "claims.md":
            html.extend(f"<p>{escape(claim)}</p>" for claim in _claim_paragraphs(body or ""))
        elif key in ("abstract-figures", "figures"):
            shown = figures[:1] if key == "abstract-figures" else figures
            for number, path, caption in shown:
                html.append(f"<p style='text-align:center'><img src='{escape(path.resolve().as_uri())}' "
                            f"style='width:{FIGURE_WIDTH.cm}cm'></p>")
                html.append(f"<p style='text-align:center'>图{number}</p>")
                if caption:
                    html.append(f"<p style='text-align:center'>{escape(caption)}</p>")
        else:
            html.append(_markdown_to_html(body or ""))
    html.append("</body></html>")
    HTML(string="\n".join(html), base_url=str(root)).write_pdf(str(pdf_path))
    return str(pdf_path)


def _build_application_docx(root: Path, exports_dir: Path, name: str,
                            sources: list[tuple[str, str | None]],
                            figures: list[tuple[int, Path, str | None]]) -> Path:
    """Build the application docx in the submitted package's shape."""
    document = _application_document()
    for index, (key, body) in enumerate(sources):
        if index:
            # Clones the previous section's geometry; headers are labeled
            # after the sections exist so the clones never share a part.
            document.add_section(WD_SECTION_START.NEW_PAGE)
        if key in _APPLICATION_RESTARTS_PAGES:
            sect_pr = document.sections[-1]._sectPr
            if sect_pr.find(qn("w:pgNumType")) is None:
                pg_num_type = OxmlElement("w:pgNumType")
                pg_num_type.set(qn("w:start"), "1")
                doc_grid = sect_pr.find(qn("w:docGrid"))
                if doc_grid is not None:
                    doc_grid.addprevious(pg_num_type)
                else:
                    sect_pr.append(pg_num_type)
        if key == "claims.md":
            for claim in _claim_paragraphs(body or ""):
                _add_paragraph(document, claim, east_asia=APPLICATION_FONT, size=APPLICATION_SIZE, indent="first")
        elif key in ("abstract-figures", "figures"):
            shown = figures[:1] if key == "abstract-figures" else figures
            for number, path, caption in shown:
                _add_figure(document, path, number, caption, east_asia=APPLICATION_FONT, size=APPLICATION_SIZE)
        else:
            if key == "description.md":
                _add_paragraph(document, name, east_asia=APPLICATION_FONT, size=APPLICATION_SIZE, indent=None,
                               centered=True)
            for text, kind in _markdown_paragraphs(body or "", keep_subheadings=True):
                if kind == "subheading":
                    _add_paragraph(document, text, east_asia=APPLICATION_FONT, size=APPLICATION_SIZE,
                                   indent=None, bold=True)
                elif kind == "bullet":
                    _add_paragraph(document, f"{BULLET_MARK} {text}", east_asia=APPLICATION_FONT,
                                   size=APPLICATION_SIZE, indent="bullet")
                else:
                    _add_paragraph(document, text, east_asia=APPLICATION_FONT, size=APPLICATION_SIZE, indent="first")
    for section, (key, _) in zip(document.sections, sources):
        _label_header(section, APPLICATION_HEADERS[key])
    output = exports_dir / f"{name}-申请文件.docx"
    document.save(output)
    (exports_dir / f"{name}-申请文件.fingerprint").write_bytes(source_fingerprint(root).encode("ascii"))
    return output
