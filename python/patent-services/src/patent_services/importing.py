"""Existing-document import: a Word patent document → project source files.

The plugin's writing flow starts from scratch (idea → brief → chapters); an
inventor or agency often arrives with an existing document instead. The
import splits that document at its section headings, maps the sections onto
the project's chapter files (``chapters/01-name.md`` … ``08-drawings.md``),
seeds ``brief.md``'s five core sections from the mapped bodies, and creates a
minimal ``patent.yml`` when the project has none — after which the normal
loop (chapters → figures → review → export) takes over with the gaps made
explicit instead of papered over.

Section recognition is prefix-matching on the Chinese section names the
agency template and the CNIPA description use, not document-structure
guessing: a heading counts when its text (leading numbering stripped) starts
with a known keyword and stays short. Numbered level-1 headings that match
no keyword become extra chapters (``09-`` onward); deeper numbered headings
fold into ``## ``/``### `` Markdown inside the chapter they landed in. What
cannot be mapped honestly (claims and abstracts — application-set material
to be rewritten from the chapters, tables, embedded images) is named in the
return value, never silently dropped or re-invented.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from docx import Document
from docx.oxml.ns import qn

from .parsing import _heading_level

#: Section keyword table in chapter order: slug, chapter file, chapter title,
#: and the heading prefixes that map to it. Prefix match on the
#: numbering-stripped heading text — ``附图说明`` and ``附图`` both land on
#: drawings, and the agency template's long four-section heading lands on
#: problem via its ``现有技术的缺点`` prefix.
_IMPORT_SECTIONS = (
    ("name", "01-name.md", "发明名称", ("发明名称", "名称")),
    ("field", "02-field.md", "所属技术领域", ("所属技术领域", "技术领域")),
    ("background", "03-background.md", "背景技术", ("背景技术", "现有技术")),
    ("problem", "04-problem.md", "技术问题", ("现有技术的缺点", "技术问题", "发明目的")),
    ("solution", "05-solution.md", "发明内容（技术方案）", ("发明内容", "技术方案")),
    ("effect", "06-effect.md", "有益效果", ("有益效果",)),
    ("key-points", "07-key-points.md", "关键点与保护范围",
     ("关键点", "欲保护点", "保护点", "保护范围", "本发明的关键点")),
    ("drawings", "08-drawings.md", "附图说明", ("附图说明", "附图")),
)

#: Application-set material the import must not absorb into chapters: claims
#: and abstracts are rewritten from the chapters later (patent-application),
#: so their sections are skipped and named in the report instead.
_SKIP_PREFIXES = ("权利要求", "说明书摘要", "摘要附图", "摘要")

#: A section heading stays short — a body paragraph that happens to open with
#: a keyword (``技术问题贯穿始终…``) must not split the document.
_HEADING_MAX_CHARS = 60

#: Unmapped top-level shapes: Chinese-numeral/章 numbering (``九、``/``第三章``)
#: and the description-section names CNIPA descriptions use beyond the mapped
#: keywords. Arabic enumerations (``1.``) never create sections — patent prose
#: numbers its paragraphs with them.
_EXTRA_HEADING = re.compile(r"^(?:第[一二三四五六七八九十百千]+[章节]|[一二三四五六七八九十]{1,3}、)")
_EXTRA_SECTION_NAMES = ("具体实施方式", "实施方式", "实施例")

#: Leading document numbering when matching headings: ``一、`` ``12.`` ``（3）``
#: ``1.2`` ``第一章`` — the conventions the three-level parser recognizes.
_LEAD_NUMBERING = re.compile(
    r"^(?:第[一二三四五六七八九十百千]+[章节]|[\d一二三四五六七八九十]{1,3}[、.．)）]"
    r"|[（(][0-9一二三四五六七八九十]{1,3}[)）]|\d{1,2}(?:\.\d{1,2})+)\s*[:：]?\s*"
)

#: Word list bullets and common literal markers that fold into Markdown bullets.
_BULLET_PREFIX = re.compile(r"^[●•·▪◦‣○－—–-]\s*")

#: Slug for an unmapped level-1 section (a ``09-``-onward extra chapter).
_EXTRA_SLUG = re.compile(r"[^\w\u4e00-\u9fff]+")

#: A CN publication number in imported prose — the loop's prior-art ledger
#: gate will demand an entry for each; the import names this up front.
_PUBLICATION_NUMBER = re.compile(r"CN\s?\d{7,9}\s?[ABUYS]")


def _strip_numbering(text: str) -> str:
    """Drop a heading's leading document numbering and trailing colon."""
    return _LEAD_NUMBERING.sub("", text).rstrip("：:").strip()


def _match_section(text: str) -> tuple[str, str, str] | None:
    """Match a stripped heading text against the section table (prefix, ordered).

    Longest keyword wins: the problem chapter's ``现有技术的缺点`` must beat
    the background chapter's ``现有技术`` on the agency template's long
    four-section heading, or the problem section lands inside background.
    """
    best: tuple[int, str, str, str] | None = None
    for slug, filename, title, keywords in _IMPORT_SECTIONS:
        for keyword in keywords:
            if text.startswith(keyword) and (best is None or len(keyword) > best[0]):
                best = (len(keyword), slug, filename, title)
    if best is None:
        return None
    return best[1], best[2], best[3]


def _is_skip_title(text: str) -> bool:
    """Whether a section is application-set material to skip, not import.

    Claims and abstracts belong to the application set and get rewritten from
    the chapters (patent-application) — absorbing them into a chapter would
    fork the source of truth.
    """
    return any(text.startswith(prefix) for prefix in _SKIP_PREFIXES)


def _is_section_heading(paragraph) -> bool:
    """Whether a paragraph splits the document into sections.

    True when the numbering- and colon-stripped text prefix-matches a known
    section keyword — or an application-set title (claims, abstracts) the
    import must recognize in order to skip it — or carries an unmistakable
    top-level shape of its own (Chinese-numeral numbering like ``九、``, a
    Word heading style, or a known description-section name) with no
    sentence-ending punctuation; body enumerations (``1. xxx。``) never
    qualify. Keyword matching keeps the split at the document's real top
    level: style or numbering recognition alone would shred a document at
    every ``3.1``-style subheading.
    """
    return _section_kind(paragraph) is not None


def _section_kind(paragraph) -> str | None:
    """Classify a paragraph as a section split: ``chapter``/``skip``/``extra``."""
    text = paragraph.text.strip()
    if not text or len(text) > _HEADING_MAX_CHARS:
        return None
    stripped = _strip_numbering(text)
    if _is_skip_title(stripped):
        return "skip"
    # A sentence-ending body (``关键点在意图声明与分层仲裁。``) never splits —
    # headline punctuation (``：`` ``？``, or none) does. Checked before the
    # keyword match: keyword prefixes hit plenty of body sentences.
    if text.endswith(("。", "；", "，", ",", ";")):
        return None
    if _match_section(stripped) is not None:
        return "chapter"
    if _EXTRA_HEADING.match(text) or _any_prefix(stripped, _EXTRA_SECTION_NAMES):
        return "extra"
    style = (paragraph.style.name or "")
    if "heading" in style.lower() or "标题" in style:
        # Only a level-1 heading style starts a chapter (an unmapped one
        # continues as an extra ``09-`` chapter); level 2/3 stay in the
        # current section — the fold emits them as ``## ``/``### `` lines.
        # A heading style without a trailing level digit keeps the old
        # conservative no-split behavior.
        level = re.search(r"(\d+)\s*$", style.rstrip())
        return "extra" if level is not None and level.group(1) == "1" else None
    return None


def _any_prefix(text: str, prefixes) -> bool:
    return any(text == prefix or text.startswith(prefix) for prefix in prefixes)


def _fold_runs(paragraph) -> str:
    """Fold a paragraph's runs into Markdown, keeping bold spans as ``**…**``."""
    parts: list[tuple[str, bool]] = []
    for run in paragraph.runs:
        text = run.text
        if not text:
            continue
        bold = bool(run.bold)
        if parts and parts[-1][1] == bold:
            parts[-1] = (parts[-1][0] + text, bold)
        else:
            parts.append((text, bold))
    return "".join(f"**{text.strip()}**" if bold and text.strip() else text for text, bold in parts)


def _fold_paragraph(paragraph) -> str:
    """Fold one body paragraph to a Markdown line ('' for blanks).

    List paragraphs (Word numbering) and literal bullet markers become
    ``- `` Markdown bullets; deeper headings fold to ``## ``/``### `` with
    their text verbatim — renumbering is the export's job, not the import's.
    Embedded images are dropped: figures follow the figure discipline, they
    are not extracted.
    """
    text = _fold_runs(paragraph).strip()
    if not text:
        return ""
    level = _heading_level(paragraph)
    if level is not None and 2 <= level <= 3:
        # Headings carry no bold markers — their level already means emphasis;
        # the body text below them stays verbatim.
        return f"{'#' * level} {paragraph.text.strip()}"
    numbered = paragraph._p.pPr is not None and paragraph._p.pPr.find(qn("w:numPr")) is not None
    marker = _BULLET_PREFIX.match(text)
    if numbered or marker:
        return "- " + (text[marker.end():] if marker else text)
    return text


#: One parsed section: kind (``chapter``/``extra``/``skip``/``preamble``),
#: target filename when known, section title, and the Markdown body (the
#: chapter title line is not part of the body — it is written from the title).
class _Section:
    __slots__ = ("kind", "filename", "title", "lines")

    def __init__(self, kind: str, filename: str | None, title: str) -> None:
        self.kind = kind
        self.filename = filename
        self.title = title
        self.lines: list[str] = []


def split_document(path: str) -> tuple[list[_Section], dict[str, int]]:
    """Split one docx at its section headings.

    Returns ``(sections, stats)`` in document order — mapped sections carry
    their chapter filename, extras are named in the report and numbered at
    write time, skips are application-set material, and a leading
    ``preamble`` holds anything before the first heading. stats carries
    table/image counts for the report.
    """
    document = Document(path)
    stats = {"tables": len(document.tables), "images": len(document.inline_shapes)}
    sections: list[_Section] = []
    current = _Section("preamble", None, "序言")

    def close() -> None:
        if current.kind == "preamble" and not any(line for line in current.lines):
            return
        sections.append(current)

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        kind = _section_kind(paragraph) if text else None
        if kind is not None:
            close()
            stripped = _strip_numbering(text)
            if kind == "skip":
                current = _Section("skip", None, stripped)
            elif kind == "chapter":
                _slug, filename, title = _match_section(stripped)
                current = _Section("chapter", filename, title)
            else:
                current = _Section("extra", None, stripped)
            continue
        folded = _fold_paragraph(paragraph)
        if folded:
            current.lines.extend(["", folded])
        elif not text and current.lines and current.lines[-1] != "":
            current.lines.append("")
    close()
    return sections, stats


def import_patent_document(project_dir: str, document_path: str, name: str | None = None,
                           overwrite: bool = False) -> str:
    """Import an existing Word patent document into a patent project.

    Splits the document at its section headings, writes the mapped sections
    into ``chapters/01-name.md`` … ``08-drawings.md`` (unmapped level-1
    sections continue as ``09-`` extra chapters, numbered after whatever the
    project already has), seeds ``brief.md``'s five core sections from the
    mapped bodies, and creates a minimal ``patent.yml`` when absent — the
    flow's gates then name every remaining gap explicitly. Chapters/brief
    with existing non-empty content refuse the import unless ``overwrite`` is
    set: an import is a starting point, not a blind replacement.

    Returns a Chinese summary: what mapped where, skipped application-set
    material, empty-chapter gaps the flow must fill, table/image counts, and
    the prior-art reminder when imported prose quotes publication numbers.
    """
    root = Path(project_dir)
    source = Path(document_path)
    if not source.is_file():
        raise ValueError(f"document not found: {source}")
    if source.suffix.lower() != ".docx":
        raise ValueError(f"只支持 .docx（得到 {source.name}）——.doc/.wps/.pdf 请先另存为 .docx 再导入")

    sections, stats = split_document(str(source))
    if not any(section.kind in ("chapter", "extra") for section in sections):
        raise ValueError(f"{source.name} 里没有匹配到任何章节标题（名称/技术领域/背景技术/技术问题/发明内容/"
                         f"有益效果/关键点/附图）——确认这是专利交底书或说明书类文档；"
                         f"拿不准时先调 parse_disclosure_docx 看解析效果")

    chapters_dir = root / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    # Group section bodies by target file; duplicate sections of the same
    # chapter (修订残留文档常见) append instead of overwrite. Extra chapters
    # number after whatever the project already carries.
    files_by_slug = {slug: filename for slug, filename, _t, _kw in _IMPORT_SECTIONS}
    titles_by_file = {filename: title for _s, filename, title, _kw in _IMPORT_SECTIONS}
    grouped: dict[str, list[str]] = {}
    skipped: list[str] = []
    extras: list[tuple[str, str]] = []
    numbered = [int(path.stem[:2]) for path in chapters_dir.glob("*.md") if path.stem[:2].isdigit()]
    next_extra = max([8, *numbered]) + 1
    for section in sections:
        if section.kind == "chapter":
            grouped.setdefault(section.filename, []).append("\n".join(section.lines).strip())
        elif section.kind == "extra":
            slug_part = _EXTRA_SLUG.sub("-", section.title).strip("-").lower()[:20] or "extra"
            filename = f"{next_extra:02d}-{slug_part}.md"
            next_extra += 1
            titles_by_file[filename] = section.title
            grouped.setdefault(filename, []).append("\n".join(section.lines).strip())
            extras.append((filename, section.title))
        elif section.kind == "skip":
            skipped.append(section.title)

    # Every standard chapter lands as a file — mapped sections with content,
    # the rest as bare placeholders the flow's chapter gate names explicitly.
    for filename in files_by_slug.values():
        if filename not in grouped:
            grouped[filename] = [""]

    # Refuse before writing anything: a chapter target with existing
    # non-empty content blocks the whole import unless the caller passed
    # overwrite. An existing non-empty brief only skips the brief seeding —
    # the interview's record is never a reason to refuse chapter import.
    def has_content(filename: str) -> bool:
        target = chapters_dir / filename
        return target.is_file() and target.read_text(encoding="utf-8").strip() != ""

    blocked = [filename for filename in grouped if has_content(filename) and not overwrite]
    if blocked:
        raise ValueError(f"目标章节已有内容，未写入（导入是起点不是盲目覆盖）："
                         f"{'、'.join(f'chapters/{filename}' for filename in blocked)}；"
                         f"确认覆盖请带 overwrite=true")

    written: list[tuple[str, str, int]] = []
    for filename, bodies in sorted(grouped.items()):
        text = "\n\n".join(body for body in bodies if body.strip())
        (chapters_dir / filename).write_text(f"# {titles_by_file[filename]}\n\n{text}\n",
                                             encoding="utf-8", newline="\n")
        written.append((filename, titles_by_file[filename], len([body for body in bodies if body.strip()])))

    return _finish_import(root, source, name, overwrite, grouped, written, extras, skipped, stats)


def _finish_import(root: Path, source: Path, name: str | None, overwrite: bool,
                   grouped: dict[str, list[str]], written: list[tuple[str, str, int]],
                   extras: list[tuple[str, str]], skipped: list[str], stats: dict[str, int]) -> str:
    """Seed brief.md/patent.yml and compose the import report."""
    slug_by_file = {filename: slug for slug, filename, _t, _kw in _IMPORT_SECTIONS}
    brief_bodies: dict[str, str] = {}
    for filename, bodies in grouped.items():
        slug = slug_by_file.get(filename)
        if slug in ("field", "background", "problem", "solution", "effect"):
            brief_bodies[slug] = "\n\n".join(body for body in bodies if body.strip())

    brief_path = root / "brief.md"
    brief_written = False
    if overwrite or not brief_path.is_file() or brief_path.read_text(encoding="utf-8").strip() == "":
        lines = [f"# 技术交底摘要（导入自 {source.name}）", "",
                 "> 本摘要由已有文档导入生成，作为修订起点；五方对齐与查新补强按 patent-init / patent-research 继续。", ""]
        for slug, heading in (("field", "技术领域"), ("background", "背景技术"), ("problem", "技术问题"),
                              ("solution", "发明内容"), ("effect", "有益效果")):
            lines.extend([f"## {heading}", "", brief_bodies.get(slug, ""), ""])
        brief_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
        brief_written = True

    manifest_path = root / "patent.yml"
    manifest_created = False
    if not manifest_path.is_file():
        name_body = next((body for filename, bodies in sorted(grouped.items())
                          if filename == "01-name.md" for body in bodies if body.strip()), None)
        import_name = name or (name_body.splitlines()[0].strip() if name_body else None) or source.stem
        # Serialized, not interpolated: a name like ``方法: 系统`` written raw
        # into the manifest is a YAML ScannerError that later reads choke on.
        manifest_path.write_text(
            yaml.safe_dump({"formatVersion": 1, "name": import_name, "status": "drafting"},
                           allow_unicode=True, sort_keys=False),
            encoding="utf-8", newline="\n")
        manifest_created = True

    lines = [f"已导入 {source.name} → {root}："]
    for filename, title, count in written:
        state = f"{count} 节内容" if count else "空占位（原文档无对应节，流程会点名补齐）"
        lines.append(f"- {title} → chapters/{filename}（{state}）")
    if extras:
        lines.append("- 未映射到八章节的一级节：" + "、".join(f"{title}（chapters/{filename}）"
                                                       for filename, title in extras))
    if skipped:
        lines.append("- 属申请文件材料、未导入（后续按 patent-application 从章节重写）："
                     + "、".join(sorted(set(skipped))))
    if stats["tables"]:
        lines.append(f"- 原文档含 {stats['tables']} 个表格，未导入（信息栏表格随导出模板自带）")
    if stats["images"]:
        lines.append(f"- 原文档含 {stats['images']} 张嵌入图片，未导入——附图按 patent-figure-design 纪律重绘后落入 figures/")
    prose = "\n".join(body for bodies in grouped.values() for body in bodies)
    if _PUBLICATION_NUMBER.search(prose):
        lines.append("- 导入内容引用了公开号（CN…）：每个号必须按 patent-research 记入 reference/prior-art.md，"
                     "否则流程 chapters 门会拦截")
    if brief_written:
        lines.append("- brief.md 已按导入内容生成五维骨架")
    if manifest_created:
        lines.append("- 已建档 patent.yml（status: drafting）")
    lines.append("- 导入是修订起点：交付物只能来自重新导出，不要把原文档当导出物")
    return "\n".join(lines)
