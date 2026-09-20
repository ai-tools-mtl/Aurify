"""Deterministic geometry lint for ``.drawio`` figure sources.

The figure-design skill's drawing disciplines name three recurring geometry
faults that a rendered PNG only reveals after the fact: edges left to the
auto-router (the "line turns a random corner" fault), waypoints clipped
inside the boxes they route around, and parallel runs sharing one corridor
(the overlapping-segment fault, typically two edges reusing the same bend).
:func:`lint_drawio_source` checks the XML directly — before any render — so
the model fixes the geometry at the drawing stage. ``render_drawio_figure``
runs the same lint and refuses to render on a finding of severity ``error``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

#: A waypoint this close to a box edge still counts as inside it (px slack).
BOX_MARGIN = 6.0

#: Two points this close count as the same point (shared bend / anchor).
SAME_POINT_EPSILON = 1.5

#: Two parallel runs this close (px) with this much overlap (px) warn.
CORRIDOR_EPSILON = 2.0
CORRIDOR_MIN_OVERLAP = 12.0

#: Cell style keys naming an explicit connection anchor.
EXIT_KEYS = ("exitX", "exitY")
ENTRY_KEYS = ("entryX", "entryY")


@dataclass(frozen=True)
class Finding:
    """One geometry fault, phrased for the model to act on.

    Attributes:
        severity: ``error`` blocks the render; ``warning`` rides along.
        kind: short fault name (``unanchored-edge`` and friends).
        message: human-readable line with the fix baked in.
    """

    severity: str
    kind: str
    message: str


@dataclass(frozen=True)
class _Box:
    """A vertex's absolute geometry and its visible label."""

    x: float
    y: float
    w: float
    h: float
    label: str


@dataclass(frozen=True)
class _Edge:
    """One connection with its resolved polyline, when fully anchored.

    ``points`` is ``None`` for edges without explicit anchors on both ends —
    their geometry is the auto-router's business, reported as a warning
    instead of being guessed at.
    """

    ident: str
    source: str
    target: str
    points: tuple[tuple[float, float], ...] | None


def _style_dict(style: str | None) -> dict[str, str]:
    """Split a drawio ``style`` attribute into its key/value pairs."""
    if not style:
        return {}
    pairs: dict[str, str] = {}
    for chunk in style.split(";"):
        if "=" in chunk:
            key, _, value = chunk.partition("=")
            pairs[key.strip()] = value.strip()
        elif chunk.strip():
            pairs[chunk.strip()] = ""
    return pairs


def _absolute_geometry(cells: dict[str, ET.Element]) -> dict[str, tuple[float, float]]:
    """Resolve each cell's absolute (x, y) offset by walking its parents.

    Child geometries are relative to their parent container, so a box inside
    a group only carries its absolute position once every ancestor's offset
    is summed in.
    """
    offsets: dict[str, tuple[float, float]] = {}

    def offset_of(ident: str, seen: frozenset[str] = frozenset()) -> tuple[float, float]:
        if ident in offsets:
            return offsets[ident]
        if ident in seen or ident not in cells:
            return (0.0, 0.0)
        cell = cells[ident]
        parent = cell.get("parent")
        px, py = offset_of(parent, seen | {ident}) if parent else (0.0, 0.0)
        geometry = cell.find("mxGeometry")
        if geometry is None or cell.get("vertex") != "1":
            offsets[ident] = (px, py)
        else:
            x = float(geometry.get("x", "0") or 0)
            y = float(geometry.get("y", "0") or 0)
            offsets[ident] = (px + x, py + y)
        return offsets[ident]

    for ident in cells:
        offset_of(ident)
    return offsets


def _parse(source: Path) -> tuple[dict[str, _Box], list[_Edge], dict[str, str]]:
    """Read one drawio file into labeled boxes, edges, and edge styles."""
    root = ET.parse(source).getroot()
    cells = {cell.get("id", ""): cell for cell in root.iter("mxCell") if cell.get("id")}
    offsets = _absolute_geometry(cells)
    boxes: dict[str, _Box] = {}
    styles: dict[str, str] = {}
    for ident, cell in cells.items():
        geometry = cell.find("mxGeometry")
        if cell.get("vertex") == "1" and geometry is not None:
            ox, oy = offsets[ident]
            boxes[ident] = _Box(
                x=ox,
                y=oy,
                w=float(geometry.get("width", "0") or 0),
                h=float(geometry.get("height", "0") or 0),
                label=(cell.get("value") or ident).strip() or ident,
            )
        if cell.get("source") and cell.get("target"):
            styles[ident] = cell.get("style") or ""
    edges: list[_Edge] = []
    for ident, style in styles.items():
        cell = cells[ident]
        source = cell.get("source", "")
        target = cell.get("target", "")
        style_map = _style_dict(style)
        if not all(style_map.get(key) is not None for key in (*EXIT_KEYS, *ENTRY_KEYS)):
            edges.append(_Edge(ident, source, target, None))
            continue
        waypoints = [
            (float(point.get("x", "0") or 0), float(point.get("y", "0") or 0))
            for array in cell.iter("Array")
            if array.get("as") == "points"
            for point in array.findall("mxPoint")
        ]
        points = (
            _anchor(boxes[source], style_map, EXIT_KEYS),
            *waypoints,
            _anchor(boxes[target], style_map, ENTRY_KEYS),
        )
        edges.append(_Edge(ident, source, target, points))
    return boxes, edges, styles


def _anchor(box: _Box, style: dict[str, str], keys: tuple[str, str]) -> tuple[float, float]:
    """Absolute position of a 0..1 relative anchor on one box."""
    fx = float(style.get(keys[0], "0.5") or 0.5)
    fy = float(style.get(keys[1], "0.5") or 0.5)
    return (box.x + fx * box.w, box.y + fy * box.h)


def _inside(point: tuple[float, float], box: _Box, margin: float = BOX_MARGIN) -> bool:
    """Whether a point sits within a box (with slack for its border)."""
    x, y = point
    return box.x - margin <= x <= box.x + box.w + margin and box.y - margin <= y <= box.y + box.h + margin


def _runs(points: tuple[tuple[float, float], ...]) -> list[tuple[str, float, float, float]]:
    """Decompose a polyline into axis-aligned runs.

    Each run is ``(axis, fixed, lo, hi)``: horizontal runs fix ``y``, vertical
    runs fix ``x``; ``lo``/``hi`` are the moving extent in order. Diagonal
    segments (a fault in their own right, but rare here) are skipped.
    """
    runs: list[tuple[str, float, float, float]] = []
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if abs(y1 - y2) <= 0.5 and abs(x1 - x2) > 0.5:
            runs.append(("h", y1, min(x1, x2), max(x1, x2)))
        elif abs(x1 - x2) <= 0.5 and abs(y1 - y2) > 0.5:
            runs.append(("v", x1, min(y1, y2), max(y1, y2)))
    return runs


def lint_drawio_source(source: str | Path) -> list[Finding]:
    """Lint one ``.drawio`` figure source for the skill's geometry faults.

    Args:
        source: path to the ``.drawio`` file.

    Returns:
        The findings, errors first; empty when the geometry is clean.

    Raises:
        ValueError: the file is missing or not parseable drawio XML.
    """
    path = Path(source)
    if not path.is_file():
        raise ValueError(f"figure source not found: {source}")
    try:
        boxes, edges, _styles = _parse(path)
    except ET.ParseError as error:
        raise ValueError(f"drawio XML 解析失败（{error}）：{source}") from error
    findings: list[Finding] = []

    for edge in edges:
        if edge.points is None:
            findings.append(Finding(
                "warning", "unanchored-edge",
                f"边 {edge.ident} 未写显式锚点（exitX/exitY/entryX/entryY）——drawio 自动布线会自由生成拐点，"
                "这是「线突然转弯」的根源；补齐两端锚点，需要拐弯时手写 mxPoint 放在框外通道上",
            ))

    for edge in edges:
        if edge.points is None:
            continue
        waypoints = edge.points[1:-1]
        for index, point in enumerate(waypoints, start=1):
            for box in boxes.values():
                if _inside(point, box):
                    findings.append(Finding(
                        "error", "waypoint-in-box",
                        f"边 {edge.ident} 的第 {index} 个拐点 ({point[0]:.0f},{point[1]:.0f}) 落在节点「{box.label}」框内"
                        "——拐点必须在框外，移到行/列通道上再折",
                    ))

    by_point: dict[tuple[float, float], list[tuple[_Edge, int]]] = {}
    for edge in edges:
        if edge.points is None:
            continue
        for index, point in enumerate(edge.points):
            snapped = (round(point[0] / SAME_POINT_EPSILON), round(point[1] / SAME_POINT_EPSILON))
            by_point.setdefault(snapped, []).append((edge, index))
    for bucket in by_point.values():
        ids = {edge.ident for edge, _ in bucket}
        if len(ids) > 1:
            point = bucket[0][0].points[bucket[0][1]]
            kind = "shared-waypoint" if all(0 < index < len(edge.points) - 1 for edge, index in bucket) else "shared-anchor"
            label = "拐点" if kind == "shared-waypoint" else "端点锚点"
            findings.append(Finding(
                "error" if kind == "shared-waypoint" else "warning", kind,
                f"边 {'、'.join(sorted(ids))} 共用同一个{label} ({point[0]:.0f},{point[1]:.0f})"
                "——共用拐点是线段搭接重叠的主要来源，各边错开坐标（通道间距 ≥16px）或分点进出",
            ))

    anchored = [edge for edge in edges if edge.points is not None and len(edge.points) >= 2]
    for i, one in enumerate(anchored):
        for two in anchored[i + 1:]:
            for axis_one, fixed_one, lo_one, hi_one in _runs(one.points):
                for axis_two, fixed_two, lo_two, hi_two in _runs(two.points):
                    if axis_one != axis_two:
                        continue
                    overlap = min(hi_one, hi_two) - max(lo_one, lo_two)
                    if abs(fixed_one - fixed_two) <= CORRIDOR_EPSILON and overlap >= CORRIDOR_MIN_OVERLAP:
                        findings.append(Finding(
                            "warning", "overlapping-run",
                            f"边 {one.ident} 与边 {two.ident} 的平行线段共走廊（{'y' if axis_one == 'h' else 'x'}≈"
                            f"{fixed_one:.0f}，重叠约 {overlap:.0f}px）——同向多股线各走各的通道，错开 ≥16px",
                        ))
    return sorted(findings, key=lambda finding: (finding.severity != "error", finding.kind))


def format_findings(findings: list[Finding]) -> str:
    """Render the findings as the model-facing block."""
    if not findings:
        return "几何自查通过：无锚点缺失、无拐点入框、无共用拐点、无共走廊平行线。"
    errors = sum(1 for finding in findings if finding.severity == "error")
    warnings = len(findings) - errors
    lines = [f"几何自查：{len(findings)} 项发现（{errors} error / {warnings} warning）"]
    lines.extend(f"[{finding.severity}] {finding.message}" for finding in findings)
    return "\n".join(lines)
