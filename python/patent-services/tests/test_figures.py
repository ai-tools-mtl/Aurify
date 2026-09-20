"""Geometry lint over drawio sources: anchors, waypoints, corridors."""

from __future__ import annotations

import textwrap

import pytest

from patent_services.figures import format_findings, lint_drawio_source


def write_drawio(tmp_path, cells: str, extra_model: str = "") -> None:
    """Write one minimal drawio file with the given mxCell XML."""
    body = textwrap.dedent(f"""
        <mxfile><diagram><mxGraphModel><root>
          <mxCell id="0"/><mxCell id="1" parent="0"/>
          {cells}
          {extra_model}
        </root></mxGraphModel></diagram></mxfile>
    """)
    (tmp_path / "f.drawio").write_text(body, encoding="utf-8")


TWO_BOXES = """
<mxCell id="A" value="登记表" vertex="1" parent="1">
  <mxGeometry x="40" y="40" width="120" height="60" as="geometry"/>
</mxCell>
<mxCell id="B" value="判定器" vertex="1" parent="1">
  <mxGeometry x="40" y="240" width="120" height="60" as="geometry"/>
</mxCell>
"""


def edge(ident: str, style: str, points: list[tuple[int, int]] | None = None) -> str:
    waypoints = (
        f'<Array as="points">' + "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in points) + "</Array>"
        if points
        else ""
    )
    return (
        f'<mxCell id="{ident}" style="{style}" edge="1" parent="1" source="A" target="B">'
        f'<mxGeometry relative="1" as="geometry">{waypoints}</mxGeometry></mxCell>'
    )


ANCHORED = "edgeStyle=orthogonalEdgeStyle;exitX=0.5;exitY=1;entryX=0.5;entryY=0;"


def test_clean_anchored_edge_passes(tmp_path):
    write_drawio(tmp_path, TWO_BOXES + edge("E1", ANCHORED))
    findings = lint_drawio_source(tmp_path / "f.drawio")
    assert findings == []
    assert "几何自查通过" in format_findings(findings)


def test_unanchored_edge_warns(tmp_path):
    write_drawio(tmp_path, TWO_BOXES + edge("E1", "edgeStyle=orthogonalEdgeStyle;"))
    findings = lint_drawio_source(tmp_path / "f.drawio")
    assert [(f.severity, f.kind) for f in findings] == [("warning", "unanchored-edge")]
    assert "exitX" in findings[0].message


def test_waypoint_inside_a_box_is_an_error(tmp_path):
    # A 的框是 (40,40)-(160,100)：拐点 (100,70) 深入框内。
    write_drawio(tmp_path, TWO_BOXES + edge("E1", ANCHORED, points=[(100, 70)]))
    findings = lint_drawio_source(tmp_path / "f.drawio")
    kinds = [(f.severity, f.kind) for f in findings]
    assert ("error", "waypoint-in-box") in kinds
    assert any("登记表" in f.message for f in findings)


def test_waypoint_in_a_nested_box_uses_absolute_geometry(tmp_path):
    nested = TWO_BOXES + textwrap.dedent("""
    <mxCell id="G" value="组" vertex="1" parent="1">
      <mxGeometry x="300" y="40" width="200" height="140" as="geometry"/>
    </mxCell>
    <mxCell id="C" value="成员" vertex="1" parent="G">
      <mxGeometry x="20" y="20" width="80" height="40" as="geometry"/>
    </mxCell>
    """)
    # C 的绝对框是 (320,60)-(400,100)：拐点 (360,80) 在其中。
    write_drawio(tmp_path, nested + edge("E1", ANCHORED, points=[(360, 80)]))
    findings = lint_drawio_source(tmp_path / "f.drawio")
    assert any("成员" in f.message and f.kind == "waypoint-in-box" for f in findings)


def test_shared_waypoint_between_two_edges_is_an_error(tmp_path):
    two_edges = TWO_BOXES + edge("E1", ANCHORED, points=[(200, 120)]) + edge(
        "E2", ANCHORED + "exitX=1;exitY=0.5;entryX=1;entryY=0.5;", points=[(200, 120)]
    )
    write_drawio(tmp_path, two_edges)
    findings = lint_drawio_source(tmp_path / "f.drawio")
    assert any(f.kind == "shared-waypoint" and f.severity == "error" for f in findings)


def test_parallel_runs_in_one_corridor_warn(tmp_path):
    # 两条边各有一段 y=160 的水平长线，投影重叠远超阈值。
    two_edges = TWO_BOXES + edge("E1", ANCHORED + "exitX=0;exitY=0.5;", points=[(20, 160), (360, 160)]) + edge(
        "E2", ANCHORED + "exitX=1;exitY=0.5;", points=[(170, 161), (380, 161)]
    )
    write_drawio(tmp_path, two_edges)
    findings = lint_drawio_source(tmp_path / "f.drawio")
    assert any(f.kind == "overlapping-run" and f.severity == "warning" for f in findings)


def test_missing_file_fails_loud(tmp_path):
    with pytest.raises(ValueError, match="figure source not found"):
        lint_drawio_source(tmp_path / "ghost.drawio")


def test_unparseable_xml_fails_loud(tmp_path):
    (tmp_path / "bad.drawio").write_text("<mxfile><diagram>", encoding="utf-8")
    with pytest.raises(ValueError, match="XML 解析失败"):
        lint_drawio_source(tmp_path / "bad.drawio")
