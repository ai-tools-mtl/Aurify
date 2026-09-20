"""render_figure resolution and command construction, with a faked CLI."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from patent_services.render import render_figure, render_html_figure, resolve_drawio_binary


@pytest.fixture
def drawio_env(tmp_path, monkeypatch):
    """A fake draw.io executable that writes the requested output file."""
    fake = tmp_path / "draw.io.exe"
    fake.write_text("", encoding="utf-8")
    script = tmp_path / "fake-cli.py"
    script.write_text(
        "import sys, pathlib\n"
        "args = sys.argv[1:]\n"
        "output = args[args.index('--output') + 1]\n"
        "pathlib.Path(output).write_bytes(b'fake-image')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DSH_DRAWIO_BIN", str(fake))
    real_run = subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kwargs: _fake_run(cmd, script, kwargs, real_run))
    return tmp_path


def _fake_run(cmd, script, kwargs, real_run):
    argv = ["python", str(script)] + cmd[1:]
    return real_run(argv, **{**kwargs, "capture_output": True, "text": True, "check": False})


def test_render_writes_output_beside_source(drawio_env, tmp_path):
    source = tmp_path / "fig1.drawio"
    source.write_text("<mxfile/>", encoding="utf-8")
    output = render_figure(str(source))
    assert output.endswith("fig1.png")
    assert __import__("pathlib").Path(output).read_bytes() == b"fake-image"


def test_render_formats(drawio_env, tmp_path):
    source = tmp_path / "fig2.drawio"
    source.write_text("<mxfile/>", encoding="utf-8")
    assert render_figure(str(source), "pdf").endswith("fig2.pdf")


def test_render_from_source_dir_lands_in_figures_root(drawio_env, tmp_path):
    source = tmp_path / "figs" / "source" / "fig9.drawio"
    source.parent.mkdir(parents=True)
    source.write_text("<mxfile/>", encoding="utf-8")
    output = render_figure(str(source))
    assert __import__("pathlib").Path(output) == tmp_path / "figs" / "fig9.png"


def test_render_rejects_unknown_format(drawio_env, tmp_path):
    source = tmp_path / "fig3.drawio"
    source.write_text("<mxfile/>", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown render format"):
        render_figure(str(source), "webp")


def test_render_rejects_non_drawio_source(drawio_env, tmp_path):
    source = tmp_path / "fig4.png"
    source.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="not a drawio figure source"):
        render_figure(str(source))


def test_render_requires_existing_source(drawio_env, tmp_path):
    with pytest.raises(ValueError, match="figure source not found"):
        render_figure(str(tmp_path / "missing.drawio"))


def test_missing_binary_fails_loud_with_guidance(tmp_path, monkeypatch):
    monkeypatch.delenv("DSH_DRAWIO_BIN", raising=False)
    monkeypatch.setattr("patent_services.render.WINDOWS_USER_INSTALL", tmp_path / "nowhere.exe")
    monkeypatch.setattr("shutil.which", lambda name: None)
    source = tmp_path / "fig.drawio"
    source.write_text("<mxfile/>", encoding="utf-8")
    with pytest.raises(RuntimeError, match="draw.io Desktop"):
        render_figure(str(source))


def test_explicit_env_path_must_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("DSH_DRAWIO_BIN", str(tmp_path / "ghost.exe"))
    with pytest.raises(RuntimeError, match="不存在"):
        resolve_drawio_binary()


def test_path_lookup_wins_over_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("DSH_DRAWIO_BIN", raising=False)
    monkeypatch.setattr("patent_services.render.WINDOWS_USER_INSTALL", tmp_path / "nowhere.exe")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/drawio" if name == "drawio" else None)
    assert resolve_drawio_binary() == "/usr/bin/drawio"


def _docker_only_env(tmp_path, monkeypatch):
    """No native draw.io CLI; only a docker command answers on PATH."""
    monkeypatch.delenv("DSH_DRAWIO_BIN", raising=False)
    monkeypatch.delenv("DSH_DRAWIO_DOCKER_IMAGE", raising=False)
    monkeypatch.setattr("patent_services.render.WINDOWS_USER_INSTALL", tmp_path / "nowhere.exe")
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)


def test_docker_fallback_exports_beside_source(tmp_path, monkeypatch):
    _docker_only_env(tmp_path, monkeypatch)
    commands = []
    source = tmp_path / "figs" / "fig5.drawio"
    source.parent.mkdir()
    source.write_text("<mxfile/>", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        commands.append(list(cmd))
        if cmd[1] == "run":
            output_name = Path(cmd[cmd.index("--output") + 1]).name
            (source.parent / output_name).write_bytes(b"fake-image")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = render_figure(str(source), "svg")
    assert output.endswith("fig5.svg")
    inspect, run = commands
    assert inspect == ["docker", "image", "inspect", "q771103517/dsh-patent:latest"]
    assert run[:9] == [
        "docker",
        "run",
        "--rm",
        "-e",
        "DRAWIO_DESKTOP_RUNNER_COMMAND_LINE=/usr/bin/drawio",
        "-v",
        f"{source.parent.resolve().as_posix()}:/data/src",
        "-v",
        f"{source.parent.resolve().as_posix()}:/data/out",
    ]
    assert run[9:] == [
        "q771103517/dsh-patent:latest",
        "--no-sandbox",
        "--disable-gpu",
        "--export",
        "--format",
        "svg",
        "--output",
        "/data/out/fig5.svg",
        "/data/src/fig5.drawio",
    ]


def test_docker_fallback_without_docker_cli_names_both_remedies(tmp_path, monkeypatch):
    monkeypatch.delenv("DSH_DRAWIO_BIN", raising=False)
    monkeypatch.setattr("patent_services.render.WINDOWS_USER_INSTALL", tmp_path / "nowhere.exe")
    monkeypatch.setattr("shutil.which", lambda name: None)
    source = tmp_path / "fig6.drawio"
    source.write_text("<mxfile/>", encoding="utf-8")
    with pytest.raises(RuntimeError) as raised:
        render_figure(str(source))
    assert "draw.io Desktop" in str(raised.value)
    assert "Docker Desktop" in str(raised.value)


def test_docker_fallback_missing_image_fails_loud_with_build_command(tmp_path, monkeypatch):
    _docker_only_env(tmp_path, monkeypatch)
    monkeypatch.setenv("DSH_DRAWIO_DOCKER_IMAGE", "registry.internal/drawio:fonts")
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="No such image")

    monkeypatch.setattr(subprocess, "run", fake_run)
    source = tmp_path / "fig7.drawio"
    source.write_text("<mxfile/>", encoding="utf-8")
    with pytest.raises(RuntimeError) as raised:
        render_figure(str(source))
    text = str(raised.value)
    assert "registry.internal/drawio:fonts" in text
    assert "docker build" in text
    assert "draw.io Desktop" in text
    assert commands[0][:3] == ["docker", "image", "inspect"]


def test_docker_fallback_pulls_missing_image_before_run(tmp_path, monkeypatch):
    _docker_only_env(tmp_path, monkeypatch)
    commands = []
    source = tmp_path / "fig8.drawio"
    source.write_text("<mxfile/>", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        commands.append(list(cmd))
        if cmd[1] == "run":
            output_name = Path(cmd[cmd.index("--output") + 1]).name
            (source.parent / output_name).write_bytes(b"fake-image")
        # The inspect misses, which is what sends the flow into the pull.
        return subprocess.CompletedProcess(cmd, 0 if cmd[1] != "image" else 1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = render_figure(str(source), "png")
    assert output.endswith("fig8.png")
    assert [command[1] for command in commands] == ["image", "pull", "run"]


def test_docker_fallback_from_source_dir_mounts_both_dirs(tmp_path, monkeypatch):
    _docker_only_env(tmp_path, monkeypatch)
    commands = []
    source = tmp_path / "figs" / "source" / "fig10.drawio"
    source.parent.mkdir(parents=True)
    source.write_text("<mxfile/>", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        commands.append(list(cmd))
        if cmd[1] == "run":
            out_host = next(arg[: -len(":/data/out")] for arg in cmd if arg.endswith(":/data/out"))
            (Path(out_host) / Path(cmd[cmd.index("--output") + 1]).name).write_bytes(b"fake-image")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = render_figure(str(source), "png")
    assert __import__("pathlib").Path(output) == tmp_path / "figs" / "fig10.png"
    run = commands[1]
    assert run[5:9] == [
        "-v",
        f"{(tmp_path / 'figs' / 'source').resolve().as_posix()}:/data/src",
        "-v",
        f"{(tmp_path / 'figs').resolve().as_posix()}:/data/out",
    ]
    assert run[16:] == ["/data/out/fig10.png", "/data/src/fig10.drawio"]


def test_render_html_figure_screenshots_beside_source(tmp_path, monkeypatch):
    browser = tmp_path / "msedge.exe"
    browser.write_text("", encoding="utf-8")
    monkeypatch.setenv("DSH_HTML_BROWSER", str(browser))
    monkeypatch.delenv("DSH_DRAWIO_BIN", raising=False)
    commands = []
    source = tmp_path / "figs" / "source" / "图6.html"
    source.parent.mkdir(parents=True)
    source.write_text("<html><body>x</body></html>", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        commands.append(list(cmd))
        out = Path(cmd[3].split("=", 1)[1])
        out.write_bytes(b"fake-png")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = render_html_figure(str(source))
    assert __import__("pathlib").Path(output) == tmp_path / "figs" / "图6.png"
    argv = commands[0]
    assert argv[0] == str(browser)
    assert argv[1] == "--headless"
    assert argv[3].startswith("--screenshot=")
    assert argv[5] == "--hide-scrollbars"
    assert argv[6] == source.resolve().as_uri()


def test_render_html_figure_rejects_unknown_source_and_format(tmp_path, monkeypatch):
    browser = tmp_path / "msedge.exe"
    browser.write_text("", encoding="utf-8")
    monkeypatch.setenv("DSH_HTML_BROWSER", str(browser))
    source = tmp_path / "fig.html"
    source.write_text("<html></html>", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown HTML render format"):
        render_html_figure(str(source), "webp")
    with pytest.raises(ValueError, match="not an HTML figure source"):
        render_html_figure(str(tmp_path / "fig.drawio"))


def test_render_html_figure_without_browser_fails_loud(tmp_path, monkeypatch):
    monkeypatch.delenv("DSH_HTML_BROWSER", raising=False)
    monkeypatch.setattr("patent_services.render.HTML_BROWSER_CANDIDATES", ())
    monkeypatch.setattr(shutil, "which", lambda name: None)
    source = tmp_path / "fig.html"
    source.write_text("<html></html>", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Edge 或 Chrome"):
        render_html_figure(str(source))


TWO_BOXES = (
    '<mxCell id="A" value="登记表" vertex="1" parent="1">'
    '<mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>'
    '<mxCell id="B" value="判定器" vertex="1" parent="1">'
    '<mxGeometry x="40" y="240" width="120" height="60" as="geometry"/></mxCell>'
)


def _drawio(edges: str) -> str:
    return (
        '<mxfile><diagram><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
        + TWO_BOXES + edges + "</root></mxGraphModel></diagram></mxfile>"
    )


ANCHORED = "edgeStyle=orthogonalEdgeStyle;exitX=0.5;exitY=1;entryX=0.5;entryY=0;"


def test_render_refuses_geometry_errors_before_the_cli(drawio_env, tmp_path):
    # 拐点 (100,70) 深入 A 框 (40,40)-(160,100) 内：error 拒渲染，CLI 根本不跑。
    source = tmp_path / "fig-bad.drawio"
    source.write_text(_drawio(
        f'<mxCell id="E1" style="{ANCHORED}" edge="1" parent="1" source="A" target="B">'
        '<mxGeometry relative="1" as="geometry"><Array as="points">'
        '<mxPoint x="100" y="70"/></Array></mxGeometry></mxCell>'
    ), encoding="utf-8")
    with pytest.raises(RuntimeError, match="几何自查未过"):
        render_figure(str(source))
    assert not (tmp_path / "fig-bad.png").exists()


def test_render_succeeds_and_appends_geometry_warnings(drawio_env, tmp_path):
    source = tmp_path / "fig-loose.drawio"
    source.write_text(_drawio(
        f'<mxCell id="E1" style="edgeStyle=orthogonalEdgeStyle;" edge="1" parent="1" '
        'source="A" target="B"><mxGeometry relative="1" as="geometry"/></mxCell>'
    ), encoding="utf-8")
    result = render_figure(str(source))
    assert result.splitlines()[0].endswith("fig-loose.png")
    assert "unanchored-edge" not in result  # warning 附注按人话写，不透出内部名
    assert "显式锚点" in result
