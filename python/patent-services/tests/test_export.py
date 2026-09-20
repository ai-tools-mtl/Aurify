"""export round-trips: build a project dir, export, read the docx back."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

from patent_services.export import (
    APPLICATION_FONT,
    APPLICATION_HEADER_FONT,
    APPLICATION_SIZE,
    DISCLOSURE_FONT,
    DISCLOSURE_SIZE,
    export_application,
    export_project,
)


def east_asia(run) -> str | None:
    rfonts = run._element.rPr.rFonts
    return None if rfonts is None else rfonts.get(qn("w:eastAsia"))


def first_line_chars(paragraph) -> str | None:
    ind = paragraph._p.pPr.find(qn("w:ind"))
    return None if ind is None else ind.get(qn("w:firstLineChars"))


def ind_attrs(paragraph) -> dict:
    ind = paragraph._p.pPr.find(qn("w:ind"))
    return {} if ind is None else dict(ind.attrib)


def build_project(root):
    (root / "chapters").mkdir(parents=True)
    (root / "patent.yml").write_text("formatVersion: 1\nname: 一种测试存储装置\nstatus: drafting\n", encoding="utf-8")
    (root / "brief.md").write_text("# 技术交底摘要\n\n现有方案过慢。\n", encoding="utf-8")
    (root / "chapters" / "01-name.md").write_text("# 名称\n\n一种测试存储装置\n", encoding="utf-8")
    (root / "chapters" / "03-background.md").write_text(
        "# 背景技术\n\n## 现状\n\n- 缺点一\n- **缺点二**：更严重\n\n普通**加粗**段落。\n", encoding="utf-8"
    )
    (root / "chapters" / "99-draft.txt").write_text("不应被收集", encoding="utf-8")
    return root


def test_export_docx_uses_the_agency_template(tmp_path):
    project = build_project(tmp_path / "project")
    output = export_project(str(project))
    assert output.endswith("exports" + "\\" + "一种测试存储装置-交底书.docx") or output.endswith(
        "exports/一种测试存储装置-交底书.docx"
    )
    document = Document(output)

    # The template's page geometry, header, and inventor table ride along;
    # its footer (page number, agency name, logo) is blanked on export.
    section = document.sections[0]
    assert round(section.top_margin.cm, 2) == 2.3
    assert round(section.left_margin.cm, 2) == 1.5
    assert section.header.paragraphs[0].text == "专利申请技术交底书"
    for footer in (section.footer, section.even_page_footer):
        footer_xml = footer._element.xml
        assert "合肥和瑞" not in footer_xml
        assert "<w:pict" not in footer_xml and "blip" not in footer_xml
        assert "PAGE" not in footer_xml
    table = document.tables[0]
    assert table.cell(0, 0).text == "专利发明人"
    assert table.cell(1, 0).text.startswith("技术交底书撰写人")
    assert table.cell(2, 1).text == "发明"

    # Chapters fill the template's numbered sections in template order.
    texts = [paragraph.text for paragraph in document.paragraphs]
    assert texts[0] == "一、名称："
    # Sections renumber sequentially over the chapters actually present.
    assert "二、背景技术：" in texts
    first_heading = document.paragraphs[0]
    assert first_heading.runs[0].font.size == DISCLOSURE_SIZE
    assert east_asia(first_heading.runs[0]) == DISCLOSURE_FONT
    assert first_heading.runs[0].font.bold is True
    assert first_heading.paragraph_format.line_spacing == 1.5

    # Body content: 楷体 body runs, two-character first-line indent, dissolved bullets.
    body = next(paragraph for paragraph in document.paragraphs if paragraph.text == "一种测试存储装置")
    assert east_asia(body.runs[0]) == DISCLOSURE_FONT
    assert body.runs[0].font.size == DISCLOSURE_SIZE
    assert first_line_chars(body) == "200"

    # Reading hierarchy: subheadings bold and unindented, bullets real
    # hanging-indent points, ** spans bold in the deliverable.
    subheading = next(paragraph for paragraph in document.paragraphs if paragraph.text == "现状")
    assert subheading.runs[0].font.bold is True
    assert first_line_chars(subheading) is None
    bullet = next(paragraph for paragraph in document.paragraphs if paragraph.text.startswith("● 缺点一"))
    ind = ind_attrs(bullet)
    assert ind[qn("w:leftChars")] == "300" and ind[qn("w:hangingChars")] == "100"
    bolded = next(run for paragraph in document.paragraphs if paragraph.text == "● 缺点二：更严重"
                  for run in paragraph.runs if run.text == "缺点二")
    assert bolded.font.bold is True
    inline = next(run for paragraph in document.paragraphs if paragraph.text == "普通加粗段落。"
                  for run in paragraph.runs if run.text == "加粗")
    assert inline.font.bold is True
    assert "● 缺点一" in texts and "● 缺点二：更严重" in texts
    assert all(paragraph.style.name != "List Bullet" for paragraph in document.paragraphs)

    # The brief stays out; non-Markdown files are not collected.
    assert "技术交底摘要" not in texts and "现有方案过慢。" not in texts
    assert "不应被收集" not in texts


def test_export_docx_appends_unknown_chapters_as_extra_sections(tmp_path):
    project = build_project(tmp_path / "project")
    (project / "chapters" / "09-extra.md").write_text("# 附加说明\n\n额外章节内容。\n", encoding="utf-8")
    output = export_project(str(project))
    document = Document(output)
    texts = [paragraph.text for paragraph in document.paragraphs]
    # Extras continue the sequential numbering after the present sections.
    assert "三、附加说明" in texts
    assert "额外章节内容。" in texts


def test_export_skips_missing_template_sections_in_template_order(tmp_path):
    project = build_project(tmp_path / "project")
    # Remove chapters 01/03: only extras and other chapters would remain —
    # instead verify a project with a single late section keeps its number.
    (project / "chapters" / "01-name.md").unlink()
    output = export_project(str(project))
    document = Document(output)
    texts = [paragraph.text for paragraph in document.paragraphs]
    assert texts[0] == "一、背景技术："


def test_export_requires_patent_yml(tmp_path):
    (tmp_path / "not-a-project").mkdir()
    with pytest.raises(ValueError, match="missing patent.yml"):
        export_project(str(tmp_path / "not-a-project"))


def test_export_requires_chapters(tmp_path):
    project = tmp_path / "empty-project"
    project.mkdir()
    (project / "patent.yml").write_text("name: empty\n", encoding="utf-8")
    (project / "brief.md").write_text("只有 brief 不再构成可导出的交底书。\n", encoding="utf-8")
    with pytest.raises(ValueError, match="nothing to export"):
        export_project(str(project))


def test_export_rejects_unknown_format(tmp_path):
    project = build_project(tmp_path / "project")
    with pytest.raises(ValueError, match="unknown export format"):
        export_project(str(project), fmt="html")


def test_export_pdf_fails_loud_without_weasyprint(tmp_path, monkeypatch):
    project = build_project(tmp_path / "project")
    monkeypatch.setitem(__import__("sys").modules, "weasyprint", None)
    import patent_services.export as export_module
    monkeypatch.setattr(export_module, "_word_com_pdf", lambda docx, pdf: (False, None))
    with pytest.raises(RuntimeError, match="weasyprint"):
        export_project(str(project), fmt="pdf")


#: A valid 1×1 transparent PNG — enough for python-docx to embed.
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c63000100000500010d0a2db4000000"
    "0049454e44ae426082"
)


def add_figures(root, captions="# 附图说明\n\n图1 为本发明所述方法的流程总览图；\n图2 为本发明系统的架构框图。\n"):
    figures = root / "figures"
    figures.mkdir(exist_ok=True)
    (root / "chapters").mkdir(exist_ok=True)
    (figures / "图1.png").write_bytes(TINY_PNG)
    (figures / "图2.png").write_bytes(TINY_PNG)
    (root / "chapters" / "08-drawings.md").write_text(captions, encoding="utf-8")
    return root


def test_export_docx_embeds_figures_with_labels_below(tmp_path):
    project = add_figures(build_project(tmp_path / "project"))
    output = export_project(str(project))
    document = Document(output)
    assert len(document.inline_shapes) == 2
    texts = [p.text for p in document.paragraphs]
    assert "图1" in texts and "图2" in texts
    # The 图N label and caption sit below each image, centered.
    label_index = texts.index("图1")
    label_paragraph = document.paragraphs[label_index]
    assert label_paragraph.paragraph_format.alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert "流程总览图" in texts[label_index + 1]


def test_export_docx_without_drawings_chapter_appends_figure_section(tmp_path):
    project = add_figures(build_project(tmp_path / "project"))
    (project / "chapters" / "08-drawings.md").unlink()
    output = export_project(str(project))
    document = Document(output)
    texts = [p.text for p in document.paragraphs]
    assert any(text.endswith("、附图") for text in texts)
    assert len(document.inline_shapes) == 2


def test_export_docx_skips_non_root_figure_files(tmp_path):
    project = add_figures(build_project(tmp_path / "project"))
    source_dir = project / "figures" / "source"
    source_dir.mkdir()
    (source_dir / "图3.png").write_bytes(TINY_PNG)
    output = export_project(str(project))
    assert len(Document(output).inline_shapes) == 2


def test_export_collects_suffixed_figure_names(tmp_path):
    project = add_figures(build_project(tmp_path / "project"))
    figures = project / "figures"
    (figures / "图1.png").rename(figures / "图1-流程总览.png")
    (figures / "图2.png").rename(figures / "图2-系统架构.png")
    output = export_project(str(project))
    document = Document(output)
    assert len(document.inline_shapes) == 2
    texts = [p.text for p in document.paragraphs]
    assert "图1" in texts and "图2" in texts


def test_export_summary_warns_when_declared_figures_missing(tmp_path):
    from patent_services.export import _export_summary

    project = add_figures(build_project(tmp_path / "project"))
    (project / "chapters" / "08-drawings.md").write_text(
        "# 附图说明\n\n图1 为本发明所述方法的流程总览图；\n图2 为本发明系统的架构框图；\n图3 为增强流程图。\n",
        encoding="utf-8",
    )
    summary = _export_summary("/tmp/out.docx", project)
    assert "内嵌附图 2 张" in summary
    assert "警告" in summary
    assert "缺 图3" in summary
    assert "图N.png" in summary

    ok = _export_summary("/tmp/out.docx", add_figures(build_project(tmp_path / "other")))
    assert "内嵌附图 2 张" in ok and "警告" not in ok


def test_export_summary_names_figure_files_the_naming_contract_rejected(tmp_path):
    from patent_services.export import _export_summary

    project = add_figures(build_project(tmp_path / "project"))
    figures = project / "figures"
    (figures / "图3.jpg").write_bytes(TINY_PNG)
    (figures / "图 4.png").write_bytes(TINY_PNG)
    (figures / "preview.png").write_bytes(TINY_PNG)
    summary = _export_summary("/tmp/out.docx", project)
    assert "内嵌附图 2 张" in summary
    assert "命名未收录：图 4.png、图3.jpg" in summary
    # A file that never looked like 图N is not the naming contract's business.
    assert "preview" not in summary


def test_export_project_stamps_a_fingerprint_sidecar_beside_the_docx(tmp_path):
    from patent_services.export import export_project
    from patent_services.fingerprint import source_fingerprint

    project = add_figures(build_project(tmp_path / "project"))
    output = Path(export_project(str(project)))
    sidecar = output.with_suffix(".fingerprint")
    assert sidecar.name == "一种测试存储装置-交底书.fingerprint"
    assert sidecar.read_text(encoding="ascii") == source_fingerprint(project)


def test_review_gate_warning_mirrors_the_loop_score_gate(tmp_path):
    from patent_services.export import review_gate_warning

    project = build_project(tmp_path / "project")
    # No report at all: the gate never passed.
    assert "还没有审查报告" in review_gate_warning(project)

    review = project / "review"
    review.mkdir()
    (review / "project.review.md").write_text("总分 85\n\n> 审查范围：整项（项目根）\n", encoding="utf-8")
    assert review_gate_warning(project) == ""

    (review / "project.review.md").write_text("总分 70\n\n> 审查范围：整项（项目根）\n", encoding="utf-8")
    assert "低于达标线 80" in review_gate_warning(project)

    # The newest report wins, a partial scope is no verdict.
    (review / "later.review.md").write_text("总分 90\n\n> 审查范围：部分（chapters）\n", encoding="utf-8")
    assert "只覆盖局部目标" in review_gate_warning(project)

    # A project threshold overrides, and the 查新不可用 marker relaxes by ten.
    (review / "later.review.md").write_text("总分 90\n\n> 审查范围：整项（项目根）\n", encoding="utf-8")
    (project / "patent.yml").write_text(
        "formatVersion: 1\nname: 一种测试存储装置\nstatus: drafting\nreviewThreshold: 95\n", encoding="utf-8"
    )
    assert "低于达标线 95" in review_gate_warning(project)
    reference = project / "reference"
    reference.mkdir()
    (reference / "prior-art.md").write_text("查新不可用：网络不可达，待补查\n", encoding="utf-8")
    # 90 clears the relaxed bar of 85 but not the configured 95 — the export
    # passes, yet the unrefreshed prior-art debt still travels with it.
    assert "查新降级债" in review_gate_warning(project)
    (review / "later.review.md").write_text("总分 80\n\n> 审查范围：整项（项目根）\n", encoding="utf-8")
    assert "已放宽 10 分" in review_gate_warning(project)
    assert "低于达标线 85" in review_gate_warning(project)
    # A clean pass above the configured bar without the marker warns nothing.
    (reference / "prior-art.md").unlink()
    (review / "later.review.md").write_text("总分 96\n\n> 审查范围：整项（项目根）\n", encoding="utf-8")
    assert review_gate_warning(project) == ""


def test_disclosure_absent_warning_keeps_the_default_deliverable_visible(tmp_path):
    from patent_services.export import disclosure_absent_warning

    project = build_application_project(tmp_path / "project")
    assert "默认交付物" in disclosure_absent_warning(project)
    exports = project / "exports"
    exports.mkdir()
    (exports / "一种测试存储装置-交底书.docx").write_bytes(b"docx")
    assert disclosure_absent_warning(project) == ""


def build_application_project(root):
    (root / "application").mkdir(parents=True)
    (root / "patent.yml").write_text("formatVersion: 1\nname: 一种测试存储装置\nstatus: application\n", encoding="utf-8")
    (root / "application" / "claims.md").write_text(
        "1. 一种测试存储装置，其特征在于，包括动态评估模块。\n"
        "   所述动态评估模块按周期计算。\n"
        "2. 根据权利要求1所述的装置，其特征在于，所述模块按周期更新。\n",
        encoding="utf-8",
    )
    (root / "application" / "description.md").write_text(
        "# 说明书\n\n## 技术领域\n\n存储领域。\n\n## 具体实施方式\n\n实施例一。\n", encoding="utf-8"
    )
    (root / "application" / "abstract.md").write_text("一种测试存储装置，属于存储领域，通过动态评估提升命中率。\n", encoding="utf-8")
    return root


def test_export_application_docx_round_trip(tmp_path):
    project = build_application_project(tmp_path / "project")
    output = export_application(str(project))
    assert output.endswith("一种测试存储装置-申请文件.docx")
    document = Document(output)

    # Submitted-package page geometry: one section per document, 2.5 cm
    # top/left margins, no page numbers anywhere.
    assert len(document.sections) == 3
    for section in document.sections:
        assert round(section.top_margin.cm, 2) == 2.5
        assert round(section.left_margin.cm, 2) == 2.5
        assert section.footer.is_linked_to_previous is True
    assert document.sections[0]._sectPr.find(qn("w:pgNumType")) is None
    for section in document.sections[1:]:
        pg_num_type = section._sectPr.find(qn("w:pgNumType"))
        assert pg_num_type is not None and pg_num_type.get(qn("w:start")) == "1"

    # The document-type labels live in centered, bottom-bordered headers.
    for section, label in zip(document.sections, ("说  明  书  摘  要", "权   利   要   求   书", "说    明    书")):
        header_paragraph = section.header.paragraphs[0]
        assert header_paragraph.text == label
        assert header_paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER
        assert header_paragraph._p.pPr.find(qn("w:pBdr")) is not None
        assert east_asia(header_paragraph.runs[0]) == APPLICATION_HEADER_FONT
        assert header_paragraph.runs[0].font.size == APPLICATION_SIZE

    # No body titles: the abstract text opens the document, and the
    # description section opens with the centered invention name.
    paragraphs = document.paragraphs
    texts = [paragraph.text for paragraph in paragraphs]
    assert texts[0] == "一种测试存储装置，属于存储领域，通过动态评估提升命中率。"
    name = next(paragraph for paragraph in paragraphs if paragraph.text == "一种测试存储装置")
    assert name.alignment == WD_ALIGN_PARAGRAPH.CENTER

    # Description subheadings (## 技术领域) render bold and unindented;
    # body runs are 宋体 四号 with a two-character first-line indent.
    field = next(paragraph for paragraph in paragraphs if paragraph.text == "技术领域")
    assert field.runs[0].font.bold is True and first_line_chars(field) is None
    claim_2 = next(paragraph for paragraph in paragraphs if paragraph.text.startswith("2."))
    assert claim_2.runs[0].font.size == APPLICATION_SIZE
    assert east_asia(claim_2.runs[0]) == APPLICATION_FONT
    assert first_line_chars(claim_2) == "200"

    # One paragraph per numbered claim — the continuation line folds in.
    assert "1. 一种测试存储装置，其特征在于，包括动态评估模块。所述动态评估模块按周期计算。" in texts
    assert "2. 根据权利要求1所述的装置，其特征在于，所述模块按周期更新。" in texts
    assert "实施例一。" in texts
    assert "一种测试存储装置，属于存储领域，通过动态评估提升命中率。" in texts


def test_export_application_skips_missing_files_in_order(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "application").mkdir()
    (project / "patent.yml").write_text("name: partial\n", encoding="utf-8")
    (project / "application" / "abstract.md").write_text("部分摘要。\n", encoding="utf-8")
    output = export_application(str(project))
    assert output.endswith("partial-申请文件.docx")
    document = Document(output)
    assert len(document.sections) == 1
    assert document.sections[0].header.paragraphs[0].text == "说  明  书  摘  要"
    texts = [paragraph.text for paragraph in document.paragraphs]
    assert texts[0] == "部分摘要。"
    assert "权利要求书" not in texts


def test_export_application_requires_document_set(tmp_path):
    project = tmp_path / "no-application"
    project.mkdir()
    (project / "patent.yml").write_text("name: bare\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no application document set"):
        export_application(str(project))


def test_export_application_requires_patent_yml(tmp_path):
    (tmp_path / "not-a-project").mkdir()
    with pytest.raises(ValueError, match="missing patent.yml"):
        export_application(str(tmp_path / "not-a-project"))


def test_export_application_rejects_unknown_format(tmp_path):
    project = build_application_project(tmp_path / "project")
    with pytest.raises(ValueError, match="unknown export format"):
        export_application(str(project), "rtf")


def test_export_application_appends_figure_sections(tmp_path):
    project = add_figures(build_application_project(tmp_path / "project"))
    output = export_application(str(project))
    document = Document(output)
    headers = [section.header.paragraphs[0].text for section in document.sections]
    assert headers == ["说  明  书  摘  要", "摘  要  附  图", "权   利   要   求   书", "说    明    书", "说  明  书  附  图"]
    # 摘要附图 shows only 图1; 说明书附图 shows the full set.
    assert len(document.inline_shapes) == 3


def test_export_application_without_figures_keeps_three_sections(tmp_path):
    output = export_application(str(build_application_project(tmp_path / "project")))
    assert len(Document(output).sections) == 3


def test_export_pdf_converts_through_word_com(tmp_path, monkeypatch):
    import patent_services.export as export_module
    project = build_project(tmp_path / "project")

    def fake_com(docx, pdf):
        from pathlib import Path
        Path(pdf).write_bytes(b"%PDF-fake")
        return True, None

    monkeypatch.setattr(export_module, "_word_com_pdf", fake_com)
    output = export_project(str(project), fmt="pdf")
    assert output.endswith("一种测试存储装置-交底书.pdf")
    assert Path(output).read_bytes().startswith(b"%PDF")
    # The docx stays beside the pdf either way.
    assert (project / "exports" / "一种测试存储装置-交底书.docx").is_file()
