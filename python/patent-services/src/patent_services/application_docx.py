"""Template-based rendering of the application document set.

The application set exports on the agency's application template
(``assets/application-template.docx``): five Word sections — 说明书摘要,
摘要附图, 权利要求书, 说明书, 说明书附图 — each keeping the template's own
centered page header, 楷体 body typography, list-numbered claims and
per-section page numbering. Content paragraphs are built by cloning
prototype paragraphs found in the template body at runtime, so no
typography is rebuilt in code: a template refresh re-styles every export.

Source contract (defined by the patent-application skill): description.md
folds ``## `` sections and ``### `` subsections into bold headings (a later
``# `` heading folds in and yields a warning, never a silent drop);
``$$...$$`` lines render as centered formula paragraphs; ``_{...}`` and
``^{...}`` render as sub/superscript; ``**bold**`` keeps emphasis;
claims.md is one ``N. ``-prefixed paragraph per claim — the prefix is
stripped and the template's list numbering renumbers the claims.
"""

from copy import deepcopy
import re
from pathlib import Path

from docx import Document
from docx.image.image import Image
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm
from docx.text.paragraph import Paragraph

APPLICATION_TEMPLATE = Path(__file__).with_name("assets") / "application-template.docx"

_FIGURE_WIDTH_CM = 15.5
_FIGURE_MAX_HEIGHT_CM = 22.5

#: These two mirror export.py's heading/claim line contracts — keep in sync.
_ATX_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_BULLET = re.compile(r"^[-*]\s+(.*)$")
_CLAIM_PREFIX = re.compile(r"^\d+[.、]\s*")
_LEAD_NUMBERING = re.compile(
    r"^(?:"
    r"[（(][0-9一二三四五六七八九十]{1,3}[)）]"
    r"|[一二三四五六七八九十]{1,3}[、.．]"
    r"|\d{1,2}(?:\.\d{1,2})+(?:[、.．:：]|\s)"
    r"|\d{1,2}(?![.:：]?\d)(?:[、.．:：]|\s)"
    r")\s*"
)
_FORMULA_LINE = re.compile(r"^\$\$(.+)\$\$$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE_MARK = re.compile(r"`+")

#: w:pPr child order (schema subset) for inserting elements legally.
_PPR_RANK = {qn(f"w:{name}"): index for index, name in enumerate((
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl",
    "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens",
    "kinsoku", "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE",
    "autoSpaceDN", "bidi", "adjustRightInd", "snapToGrid", "spacing", "ind",
    "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc", "textDirection",
    "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle",
    "rPr", "sectPr", "pPrChange",
))}

#: w:rPr child order (schema subset) for inserting b / vertAlign legally.
_RPR_RANK = {qn(f"w:{name}"): index for index, name in enumerate((
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike",
    "dstrike", "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid",
    "vanish", "webHidden", "color", "spacing", "w", "kern", "position", "sz",
    "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign",
    "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath",
))}

_W14_PARA_ID = "{http://schemas.microsoft.com/office/word/2010/wordml}paraId"
_W14_TEXT_ID = "{http://schemas.microsoft.com/office/word/2010/wordml}textId"


def _ordered_insert(parent, element, rank):
    """Insert ``element`` into ``parent`` at its schema position."""
    own = rank[element.tag]
    for child in parent:
        label = rank.get(child.tag)
        if label is not None and label > own:
            child.addprevious(element)
            return
    parent.append(element)


def _para_text(paragraph) -> str:
    return "".join(node.text or "" for node in paragraph.iter(qn("w:t")))


def _is_bold(paragraph) -> bool:
    if paragraph.findall(f"{qn('w:pPr')}/{qn('w:rPr')}/{qn('w:b')}"):
        return True
    return any(rpr.find(qn("w:b")) is not None for rpr in paragraph.iter(qn("w:rPr")))


def _strip_part_ids(paragraph):
    for attr in (_W14_PARA_ID, _W14_TEXT_ID):
        paragraph.attrib.pop(attr, None)


def _find_skeleton(body):
    """Locate the template's prototype paragraphs and section breaks.

    Detection is positional + structural against the template we ship: the
    four section-ending paragraphs carry ``w:sectPr`` inside ``w:pPr``, the
    trailing body-level ``w:sectPr`` closes the drawings section, and each
    kind of content paragraph is the first of its kind inside its section
    span. Any drift in the shipped template is a RuntimeError, not a silent
    mis-style.
    """
    paragraphs = body.findall(qn("w:p"))
    section_paras = [p for p in paragraphs if p.pPr is not None and p.pPr.find(qn("w:sectPr")) is not None]
    if len(section_paras) != 4:
        raise RuntimeError(
            f"application template must carry exactly four section-break paragraphs, "
            f"found {len(section_paras)}: {APPLICATION_TEMPLATE}")
    bounds = [paragraphs.index(p) for p in section_paras]

    def span(index):
        start = 0 if index == 0 else bounds[index - 1] + 1
        return paragraphs[start:bounds[index]]

    def first_with_text(pool, what):
        for p in pool:
            if _para_text(p).strip():
                return p
        raise RuntimeError(f"application template: no {what} paragraph found")

    claim_protos = [p for p in span(2) if p.pPr is not None and p.pPr.find(qn("w:numPr")) is not None]
    if not claim_protos:
        raise RuntimeError("application template: no numbered claim paragraph found")

    title = first_with_text(span(3), "description title")
    after_title = span(3)[span(3).index(title) + 1:]
    heading = next((p for p in after_title if _is_bold(p) and _para_text(p).strip()), None)
    body_proto = next((p for p in after_title
                       if not _is_bold(p) and _para_text(p).strip() and p.pPr is not None
                       and p.pPr.find(qn("w:ind")) is not None), None)
    if heading is None or body_proto is None:
        raise RuntimeError("application template: heading/body prototype paragraph not found")

    empty = next((p for p in span(0) if not _para_text(p).strip()), None)
    if empty is None:
        raise RuntimeError("application template: no empty spacer paragraph found")

    return {
        "abstract": first_with_text(span(0), "abstract body"),
        "empty": empty,
        "note": first_with_text(span(1), "abstract-figure note"),
        "claim": claim_protos[0],
        "title": title,
        "heading": heading,
        "body": body_proto,
        "label": first_with_text(paragraphs[bounds[-1] + 1:], "figure label"),
        "sections": section_paras,
        "final_sect": body.find(qn("w:sectPr")),
    }


def _parse_rich(text):
    """Split text into (segment, subscript-or-superscript) runs.

    ``_{...}``/``^{...}`` nest: a superscript may itself carry subscripts
    (e.g. ``2^{-Δt_{i}/τ_{0}}``).
    """
    segments = []

    def emit(chunk, mode):
        if chunk:
            segments.append((chunk, mode))

    def walk(source, mode):
        buffer = []
        index = 0
        while index < len(source):
            if source[index] in "_^" and index + 1 < len(source) and source[index + 1] == "{":
                emit("".join(buffer), mode)
                buffer = []
                depth, cursor = 1, index + 2
                while cursor < len(source) and depth:
                    if source[cursor] == "{":
                        depth += 1
                    elif source[cursor] == "}":
                        depth -= 1
                    cursor += 1
                walk(source[index + 2:cursor - 1], "subscript" if source[index] == "_" else "superscript")
                index = cursor
            else:
                buffer.append(source[index])
                index += 1
        emit("".join(buffer), mode)

    walk(text, None)
    return segments


def _bold_runs(text):
    """Split on ``**bold**`` spans; returns (segment, bold) pairs."""
    parts = _BOLD.split(text)
    return [(part, index % 2 == 1) for index, part in enumerate(parts) if part]


def _content_runs(text, proto_rpr):
    """Build ``w:r`` elements for ``text`` styled after the prototype run."""
    runs = []
    for chunk, bold in _bold_runs(text):
        for sub, vert in _parse_rich(chunk):
            # The prototype's own bold (a heading style) is inherited, not
            # stripped; ``**`` markers only ever add bold on top of it.
            rpr = deepcopy(proto_rpr) if proto_rpr is not None else OxmlElement("w:rPr")
            proto_bold = rpr.find(qn("w:b")) is not None
            for existing in rpr.findall(qn("w:vertAlign")):
                rpr.remove(existing)
            if bold and not proto_bold:
                _ordered_insert(rpr, OxmlElement("w:b"), _RPR_RANK)
            if vert:
                vert_el = OxmlElement("w:vertAlign")
                vert_el.set(qn("w:val"), vert)
                _ordered_insert(rpr, vert_el, _RPR_RANK)
            run = OxmlElement("w:r")
            run.append(rpr)
            t = OxmlElement("w:t")
            t.set(qn("xml:space"), "preserve")
            t.text = sub
            run.append(t)
            runs.append(run)
    return runs


def _clone_with_text(proto, text):
    """Clone a prototype paragraph, replacing its runs with ``text`` runs."""
    clone = deepcopy(proto)
    _strip_part_ids(clone)
    for child in list(clone):
        if child.tag in (qn("w:r"), qn("w:hyperlink"), qn("w:proofErr")):
            clone.remove(child)
    proto_rpr = proto.find(f"{qn('w:r')}/{qn('w:rPr')}")
    if proto_rpr is None:
        proto_rpr = proto.find(f"{qn('w:pPr')}/{qn('w:rPr')}")
    for run in _content_runs(text, proto_rpr):
        clone.append(run)
    return clone


def _set_jc(paragraph, value):
    jc = paragraph.pPr.find(qn("w:jc"))
    if jc is not None:
        jc.set(qn("w:val"), value)
    else:
        element = OxmlElement("w:jc")
        element.set(qn("w:val"), value)
        _ordered_insert(paragraph.pPr, element, _PPR_RANK)


def _drop_first_line_indent(paragraph):
    ind = paragraph.pPr.find(qn("w:ind"))
    if ind is not None:
        for attr in (qn("w:firstLine"), qn("w:firstLineChars")):
            ind.attrib.pop(attr, None)


def _figure_size_cm(path: Path) -> tuple[float, float]:
    """Fit one figure inside the drawings-section text area, keeping aspect.

    Landscape figures ride at the section's text width; portrait figures cap
    on height so the 图N caption below stays on the same page.
    """
    image = Image.from_file(str(path))
    ratio = image.px_height / image.px_width
    if ratio >= 1.0:
        height = min(_FIGURE_MAX_HEIGHT_CM, _FIGURE_WIDTH_CM * ratio)
        return height / ratio, height
    return _FIGURE_WIDTH_CM, _FIGURE_WIDTH_CM * ratio


def _image_paragraph(document, path: Path, *, page_break_before: bool):
    """Append one centered figure paragraph; python-docx wires the image part."""
    paragraph_el = OxmlElement("w:p")
    ppr = OxmlElement("w:pPr")
    paragraph_el.append(ppr)
    _ordered_insert(ppr, OxmlElement("w:keepNext"), _PPR_RANK)
    if page_break_before:
        _ordered_insert(ppr, OxmlElement("w:pageBreakBefore"), _PPR_RANK)
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center")
    _ordered_insert(ppr, jc, _PPR_RANK)
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:line"), "500")
    spacing.set(qn("w:lineRule"), "atLeast")
    _ordered_insert(ppr, spacing, _PPR_RANK)
    document.element.body.append(paragraph_el)
    paragraph = Paragraph(paragraph_el, document)
    run = paragraph.add_run()
    width_cm, height_cm = _figure_size_cm(path)
    run.add_picture(str(path), width=Cm(width_cm), height=Cm(height_cm))


def _fold_description(body_text: str):
    """Fold description.md into (text, kind) paragraphs plus warnings.

    Kinds: ``section``/``subsection`` (bold headings), ``formula`` (centered
    ``$$...$$``), ``paragraph``. A later ``# `` heading folds in as a
    subsection and yields a warning — same contract as the disclosure export.
    """
    folded: list[tuple[str, str]] = []
    warnings: list[str] = []
    title_seen = False
    for raw_line in body_text.splitlines():
        line = _CODE_MARK.sub("", raw_line.strip())
        if not line:
            continue
        heading = _ATX_HEADING.match(line)
        if heading is not None:
            level, text = len(heading.group(1)), heading.group(2).strip()
            if not text:
                continue
            if level == 1 and not title_seen:
                title_seen = True
                continue
            text = _LEAD_NUMBERING.sub("", text) or text
            folded.append((text, "subsection" if level >= 3 else "section"))
            if level == 1:
                warnings.append(text)
            continue
        if (formula := _FORMULA_LINE.match(line)) is not None:
            folded.append((formula.group(1).strip(), "formula"))
            continue
        if (bullet := _BULLET.match(line)) is not None:
            folded.append((f"● {bullet.group(1).strip()}", "paragraph"))
            continue
        folded.append((line, "paragraph"))
    return folded, warnings


def _fold_claims(body_text: str):
    """Fold claims.md into one text per claim, ``N. `` prefixes stripped —
    the template's list numbering renumbers."""
    claims: list[str] = []
    for raw_line in body_text.splitlines():
        line = _CODE_MARK.sub("", raw_line.strip())
        if not line or line.startswith("#"):
            continue
        if _CLAIM_PREFIX.match(line) or not claims:
            claims.append(_CLAIM_PREFIX.sub("", line, count=1))
        else:
            claims[-1] += line
    return claims


def build_application_document(name: str, sources, figures) -> tuple[Document, list[str]]:
    """Render the application set on the agency template; return (document,
    warnings).

    ``sources`` is the ordered (key, markdown-or-None) list assembled by
    :func:`patent_services.export.export_application`; ``figures`` is the
    (number, path, caption) list from ``figures/``. Each present document
    kind closes with its own template section paragraph (keeping that
    section's header and page numbering); the trailing body sectPr joins
    only when the drawings section is present, so the last present section
    always carries its own header.
    """
    document = Document(str(APPLICATION_TEMPLATE))
    body = document.element.body
    skeletons = _find_skeleton(body)

    for child in list(body):
        body.remove(child)

    warnings: list[str] = []
    section_of = {"abstract.md": 0, "abstract-figures": 1, "claims.md": 2, "description.md": 3}
    for key, content in sources:
        if key == "abstract.md":
            for line in content.splitlines():
                line = line.strip()
                if line:
                    body.append(_clone_with_text(skeletons["abstract"], line))
        elif key == "abstract-figures":
            body.append(_clone_with_text(skeletons["note"], _para_text(skeletons["note"]).strip()))
            _image_paragraph(document, figures[0][1], page_break_before=False)
        elif key == "claims.md":
            for claim in _fold_claims(content):
                body.append(_clone_with_text(skeletons["claim"], claim))
        elif key == "description.md":
            body.append(_clone_with_text(skeletons["title"], name))
            folded, folded_warnings = _fold_description(content)
            warnings.extend(f"说明书：多余一级标题「{text}」已按小节折叠——源文件请改用「## 」" for text in folded_warnings)
            for text, kind in folded:
                if kind in ("section", "subsection"):
                    body.append(_clone_with_text(skeletons["heading"], text))
                elif kind == "formula":
                    clone = _clone_with_text(skeletons["body"], text)
                    _set_jc(clone, "center")
                    _drop_first_line_indent(clone)
                    body.append(clone)
                else:
                    body.append(_clone_with_text(skeletons["body"], text))
        elif key == "figures":
            for index, (number, path, _caption) in enumerate(figures):
                _image_paragraph(document, path, page_break_before=index > 0)
                body.append(_clone_with_text(skeletons["label"], f"图{number}"))
        body.append(deepcopy(skeletons["empty"]))
        if key in section_of:
            body.append(deepcopy(skeletons["sections"][section_of[key]]))
    if any(key == "figures" for key, _ in sources):
        body.append(skeletons["final_sect"])
    return document, warnings
