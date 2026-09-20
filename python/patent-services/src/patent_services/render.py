"""drawio figure rendering behind the draw.io desktop CLI or a docker exporter.

The figure sources are the file-first project's ``figures/source/*.drawio``
XML (the model writes them through the ordinary fs tools); rendering turns
one source into its final image — a source under a ``source`` directory
lands in that directory's parent (``figures/source/图1.drawio`` becomes
``figures/图1.png``, keeping the figures root a final-images-only surface),
while any other source renders beside itself. The backend resolves in
order: an explicit ``DSH_DRAWIO_BIN``, the PATH names ``draw.io``/``drawio``,
the per-user Windows install location — all the native draw.io Desktop
CLI — then a docker fallback running the community headless exporter with
CJK fonts (:data:`DEFAULT_DOCKER_IMAGE`, published to Docker Hub and built
from the shipped ``assets/Dockerfile.drawio``; a missing image auto-pulls,
and a failed pull fails loud with pull/build guidance). An absent backend
fails loud with install/build guidance instead of a broken render.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
import shutil

from .config import config_value
from .figures import format_findings, lint_drawio_source

#: PATH names tried for the draw.io desktop CLI, in order.
PATH_CANDIDATES = ("draw.io", "drawio")

#: Render formats the draw.io CLI exports.
FORMATS = ("png", "pdf", "svg", "jpg")

#: Per-user Windows install location of draw.io Desktop.
WINDOWS_USER_INSTALL = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "draw.io" / "draw.io.exe"

#: Seconds one render may run before failing loud.
RENDER_TIMEOUT_SECONDS = 120

#: Seconds one docker pull of the fallback image may run before failing loud:
#: the image is large, so a fresh fetch takes far longer than a render.
PULL_TIMEOUT_SECONDS = 600

#: Directory name holding a project's editable figure sources; a source here
#: renders into the parent (the figures root), keeping the root a surface of
#: final images only.
SOURCE_DIR_NAME = "source"


def resolve_output_path(source_path: Path, fmt: str) -> Path:
    """Resolve where one rendered figure lands.

    The project convention keeps ``figures/`` holding only the final images
    documents embed: editable sources live in ``figures/source/`` and
    intermediate files in ``figures/tmp/``. A source inside a ``source``
    directory therefore renders into that directory's parent; any other
    source renders beside itself (the legacy flat layout).
    """
    if source_path.parent.name == SOURCE_DIR_NAME:
        return source_path.parent.parent / source_path.with_suffix(f".{fmt}").name
    return source_path.with_suffix(f".{fmt}")

#: Image the docker fallback runs: the CJK-font overlay on the community
#: headless exporter, built from the shipped :data:`DOCKERFILE` and published
#: to Docker Hub, so a fresh machine auto-pulls it on first render instead of
#: failing. Rebuilt and re-pushed under the same tag whenever a plugin update
#: changes the Dockerfile.
DEFAULT_DOCKER_IMAGE = "q771103517/dsh-patent:latest"

#: Environment variable overriding the docker fallback image.
DOCKER_IMAGE_ENV = "DSH_DRAWIO_DOCKER_IMAGE"

#: Swaps the exporter's own runner for the bare draw.io CLI inside the image's
#: dbus/Xvfb headless plumbing: the exporter's ``-o`` is a folder, which would
#: break the output-beside-source contract.
DOCKER_RUNNER_ENV = "DRAWIO_DESKTOP_RUNNER_COMMAND_LINE=/usr/bin/drawio"

#: Shipped Dockerfile building the fallback image (CJK fonts on top of the
#: community headless drawio exporter).
DOCKERFILE = Path(__file__).resolve().parent / "assets" / "Dockerfile.drawio"

#: Candidate paths of the Edge/Chrome headless browser that rasterizes the
#: diagram-design HTML figures, tried in order before PATH.
HTML_BROWSER_CANDIDATES = (
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
)

#: Viewport of the HTML figure rasterization: wide enough for the widest
#: diagram-design canvases; the HTML is a white self-contained page whose
#: content centers itself, so extra height is harmless whitespace.
HTML_VIEWPORT = (1600, 2400)

HTML_GUIDANCE = (
    "渲染 HTML 附图需要 Edge 或 Chrome 浏览器的无头截图。"
    "未找到浏览器可执行文件，请安装 Microsoft Edge 或设置 DSH_HTML_BROWSER 指向 msedge.exe/chrome.exe。"
)


def discover_html_browser(explicit: str | None = None) -> str:
    """Resolve the headless browser executable for HTML figure rendering.

    Args:
        explicit: caller-supplied path; ``DSH_HTML_BROWSER`` is consulted when absent.

    Returns:
        The executable's absolute path.

    Raises:
        RuntimeError: with install guidance when no candidate exists.
    """
    candidate = explicit or config_value("DSH_HTML_BROWSER")
    if candidate:
        path = Path(candidate)
        if path.is_file():
            return str(path.resolve())
        raise RuntimeError(f"DSH_HTML_BROWSER 指向的浏览器可执行文件不存在：{candidate}。{HTML_GUIDANCE}")
    for path in HTML_BROWSER_CANDIDATES:
        if path.is_file():
            return str(path)
    for name in ("msedge", "chrome"):
        found = shutil.which(name)
        if found is not None:
            return found
    raise RuntimeError(HTML_GUIDANCE)


def render_html_figure(source: str, fmt: str = "png", browser: str | None = None) -> str:
    """Rasterize one self-contained HTML figure (diagram-design output) to an
    image beside it, via the Edge/Chrome headless screenshot.

    Args:
        source: the ``.html`` file path (relative paths resolve against the
            process working directory).
        fmt: ``png`` (default) or ``jpg``.
        browser: explicit browser executable; resolves via
            :func:`discover_html_browser` when absent.

    Returns:
        The written file's path.

    Raises:
        ValueError: an unknown format or a non-``.html`` source.
        RuntimeError: no browser is usable, or the screenshot failed.
    """
    if fmt not in ("png", "jpg", "jpeg"):
        raise ValueError(f"unknown HTML render format: {fmt} (png or jpg)")
    source_path = Path(source)
    if source_path.suffix.lower() != ".html":
        raise ValueError(f"not an HTML figure source (expected .html): {source}")
    if not source_path.is_file():
        raise ValueError(f"figure source not found: {source}")
    output = resolve_output_path(source_path, "png" if fmt == "png" else "jpg")
    executable = discover_html_browser(browser)
    completed = subprocess.run(
        [
            executable,
            "--headless",
            "--disable-gpu",
            f"--screenshot={output}",
            f"--window-size={HTML_VIEWPORT[0]},{HTML_VIEWPORT[1]}",
            "--hide-scrollbars",
            source_path.resolve().as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=RENDER_TIMEOUT_SECONDS,
        check=False,
    )
    if not output.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"HTML 附图渲染失败（exit {completed.returncode}）：{detail}")
    return str(output)

INSTALL_GUIDANCE = (
    "渲染 drawio 附图需要 draw.io Desktop 的命令行；未找到可执行文件。"
    "请安装 draw.io Desktop（https://github.com/jgraph/drawio-desktop/releases），"
    "或设置环境变量 DSH_DRAWIO_BIN 指向 draw.io 可执行文件的绝对路径。"
)


def resolve_drawio_binary(explicit: str | None = None) -> str:
    """Resolve the draw.io CLI executable.

    Args:
        explicit: caller-supplied path; ``DSH_DRAWIO_BIN`` is consulted when absent.

    Returns:
        The executable's absolute path.

    Raises:
        RuntimeError: with install guidance when no candidate exists.
    """
    candidate = explicit or config_value("DSH_DRAWIO_BIN")
    if candidate:
        path = Path(candidate)
        if path.is_file():
            return str(path.resolve())
        raise RuntimeError(f"DSH_DRAWIO_BIN 指向的 draw.io 可执行文件不存在：{candidate}。" + INSTALL_GUIDANCE)
    found = discover_native_binary()
    if found is not None:
        return found
    raise RuntimeError(INSTALL_GUIDANCE)


def discover_native_binary() -> str | None:
    """Find the native draw.io CLI without raising.

    Returns:
        The executable's path, or ``None`` when neither PATH nor the Windows
        install location holds one.
    """
    for name in PATH_CANDIDATES:
        found = shutil.which(name)
        if found is not None:
            return found
    if WINDOWS_USER_INSTALL.is_file():
        return str(WINDOWS_USER_INSTALL)
    return None


def render_figure(source: str, fmt: str = "png", binary: str | None = None) -> str:
    """Render one ``.drawio`` figure to ``<stem>.<fmt>`` beside it.

    The native draw.io Desktop CLI wins when discoverable (an explicit
    ``binary`` or ``DSH_DRAWIO_BIN`` is strict — a bad path fails rather than
    falling back); otherwise the docker exporter runs.

    Args:
        source: the ``.drawio`` file path (relative paths resolve against the
            process working directory).
        fmt: one of ``png`` (default), ``pdf``, ``svg``, ``jpg``.
        binary: explicit draw.io executable; resolves via
            :func:`resolve_drawio_binary` when absent.

    Returns:
        The written file's path.

    Raises:
        ValueError: an unknown format or a non-``.drawio`` source.
        RuntimeError: no backend is usable, or the render failed (its stderr
            is carried in the message).
    """
    if fmt not in FORMATS:
        raise ValueError(f"unknown render format: {fmt}")
    source_path = Path(source)
    if source_path.suffix.lower() != ".drawio":
        raise ValueError(f"not a drawio figure source (expected .drawio): {source}")
    if not source_path.is_file():
        raise ValueError(f"figure source not found: {source}")
    # The geometry gate runs before any backend work: unanchored edges,
    # waypoints clipped inside boxes, and shared bends are drawing-stage
    # faults the rendered PNG would only reveal after the fact, so an error
    # refuses the render and hands the fix list back to the model.
    findings = lint_drawio_source(source_path)
    errors = [finding for finding in findings if finding.severity == "error"]
    if errors:
        raise RuntimeError(
            f"几何自查未过（{len(errors)} 项 error），拒绝渲染。按下列发现修正 drawio 源后重试：\n"
            + format_findings(findings)
        )
    warnings = [finding for finding in findings if finding.severity == "warning"]
    suffix = f"\n{format_findings(warnings)}" if warnings else ""
    if binary or config_value("DSH_DRAWIO_BIN"):
        return _render_native(resolve_drawio_binary(binary), source_path, fmt) + suffix
    native = discover_native_binary()
    if native is not None:
        return _render_native(native, source_path, fmt) + suffix
    return _render_via_docker(source_path, fmt) + suffix


def _render_native(executable: str, source_path: Path, fmt: str) -> str:
    output = resolve_output_path(source_path, fmt)
    completed = subprocess.run(
        [executable, "--export", "--format", fmt, "--output", str(output), str(source_path)],
        capture_output=True,
        text=True,
        timeout=RENDER_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0 or not output.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"draw.io 渲染失败（exit {completed.returncode}）：{detail}")
    return str(output)


def _render_via_docker(source_path: Path, fmt: str) -> str:
    if shutil.which("docker") is None:
        raise RuntimeError(
            INSTALL_GUIDANCE
            + " 另一可选方案是 docker 容器导出，但未检测到 docker 命令："
            "请先安装并启动 Docker Desktop（https://docs.docker.com/desktop/）。"
        )
    image = config_value(DOCKER_IMAGE_ENV) or DEFAULT_DOCKER_IMAGE
    inspected = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
    )
    if inspected.returncode != 0:
        # The default image lives on Docker Hub, so a fresh machine fetches it
        # here instead of failing; the pull gets its own generous timeout
        # because the image dwarfs a render.
        try:
            pulled = subprocess.run(
                ["docker", "pull", image],
                capture_output=True,
                text=True,
                timeout=PULL_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            pulled = None
        if pulled is None or pulled.returncode != 0:
            detail = "拉取超时" if pulled is None else (pulled.stderr or pulled.stdout or "").strip()
            raise RuntimeError(
                f"docker 兜底所需的导出镜像不存在且拉取失败：{image}（{detail}）。"
                f"请检查网络后重试 docker pull {image}，或本地构建："
                f'docker build -t {image} -f "{DOCKERFILE}" "{DOCKERFILE.parent}"。'
                + INSTALL_GUIDANCE
            )
    output = resolve_output_path(source_path, fmt)
    # Source and output may live in different directories (source/ vs the
    # figures root), so the container gets one mount per directory.
    source_dir = source_path.parent.resolve()
    output_dir = output.parent.resolve()
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-e",
            DOCKER_RUNNER_ENV,
            "-v",
            f"{source_dir.as_posix()}:/data/src",
            "-v",
            f"{output_dir.as_posix()}:/data/out",
            image,
            # The container runs as root, where electron refuses to start
            # without this; success keys on the output file because the
            # image's output-filtering pipe can exit nonzero on a clean run.
            "--no-sandbox",
            # Under Xvfb the GPU process races on a software fallback and
            # sometimes never finishes compositing (a black screen, an
            # eternal export); software rendering is deterministic.
            "--disable-gpu",
            "--export",
            "--format",
            fmt,
            "--output",
            f"/data/out/{output.name}",
            f"/data/src/{source_path.name}",
        ],
        capture_output=True,
        text=True,
        timeout=RENDER_TIMEOUT_SECONDS,
        check=False,
    )
    if not output.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"draw.io 容器渲染失败（exit {completed.returncode}）：{detail}")
    return str(output)
