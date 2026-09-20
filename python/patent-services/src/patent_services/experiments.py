"""Patent simulation experiments in a docker runner with an automatic run log.

The experiment code lives file-first in the project (the model writes it
through the ordinary fs tools) under ``experiments/<slug>/`` — one directory
per experiment with its entry script, ``requirements.txt`` for the deps
beyond the image's baked stack, and ``results/`` for every run artifact.
:func:`run_experiment` executes one experiment in the docker image
(:data:`DEFAULT_EXPERIMENT_IMAGE`, published to Docker Hub and built from the
shipped ``assets/Dockerfile.experiment`` — a Python scientific stack with CJK
fonts, so matplotlib renders Chinese labels without tofu; a missing image
auto-pulls, and a failed pull fails loud with pull/build guidance) with the
project mounted at ``/workspace``. Every invocation — success or failure —
appends one record (timestamp, image, command, exit code, output tail) to the
experiment's ``results/run-log.md``, the run ledger the persona points
every quoted number at.
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import os
import re
import subprocess
from pathlib import Path
import shutil

from .config import config_value

#: The experiment slug: one path segment under ``experiments/``, nothing more.
SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: Commands the runner accepts, executed by ``sh -c`` inside the container.
DEFAULT_COMMAND = "python run.py"

#: Bounds of the caller-supplied timeout: long enough for real simulations,
#: short enough that a hung run cannot stall a session for hours.
MIN_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 7200

#: Seconds one docker pull of the runner image may run before failing loud:
#: the image carries the scientific stack, so a fresh fetch dwarfs a run.
PULL_TIMEOUT_SECONDS = 600

#: Image the runner executes: the CJK-font Python scientific stack, built
#: from the shipped :data:`DOCKERFILE` and published to Docker Hub, so a
#: fresh machine auto-pulls it on first use instead of failing. Rebuilt and
#: re-pushed under the same tag whenever the baked stack changes.
DEFAULT_EXPERIMENT_IMAGE = "q771103517/dsh-patent-experiment:latest"

#: Environment variable overriding the docker runner image.
DOCKER_IMAGE_ENV = "DSH_PATENT_EXPERIMENT_IMAGE"

#: Environment variable admitting arbitrary shell commands again. The default
#: policy keeps the model-facing surface a single ``python`` invocation; a
#: human who wants full shell freedom opts in explicitly.
ALLOW_ANY_COMMAND_ENV = "DSH_EXPERIMENT_ALLOW_ANY_COMMAND"

#: Shell operators a validated command may never carry: the runner accepts
#: ``python <args>``, not a pipeline. Each character is a separate escape
#: route (chaining, substitution, redirection), so one shared deny set.
FORBIDDEN_COMMAND_CHARS = ";&|`$()<>\n\r\t"

COMMAND_GUIDANCE = (
    "run_experiment 的 command 只接受单个 python 调用"
    "（如 python run.py、python3 -m pytest -q），不得携带 shell 运算符"
    "（; & | ` $ ( ) < > 或换行）。确需其他命令时由用户设置"
    f" {ALLOW_ANY_COMMAND_ENV}=1 显式放行。"
)

#: Shipped Dockerfile building the runner image (CJK fonts on top of the
#: Python scientific stack).
DOCKERFILE = Path(__file__).resolve().parent / "assets" / "Dockerfile.experiment"

#: How much of a run's combined output travels back to the model and into the
#: run log: enough to carry the numbers, small enough to protect the context.
OUTPUT_TAIL_CHARS = 4000

#: Where the run ledger lives, relative to the experiment directory.
RUN_LOG_NAME = "run-log.md"

#: Optional plotting script: when present, a successful run re-executes it so
#: the figures under ``results/`` always reflect the latest numbers.
PLOT_SCRIPT_NAME = "plot_results.py"

DOCKER_GUIDANCE = (
    "运行仿真实验需要 docker 容器（保证环境一致、可复现）。未检测到 docker 命令："
    "请先安装并启动 Docker Desktop（https://docs.docker.com/desktop/）。"
    "调试期间可以本地跑（bash/pwsh），但正式写进交底书的数据必须经 run_experiment 重跑落档。"
)


def validate_experiment(project_dir: Path, experiment: str) -> Path:
    """Resolve and validate one experiment directory.

    Args:
        project_dir: the patent project directory holding ``experiments/``.
        experiment: the experiment slug (a single path segment).

    Returns:
        The experiment directory's absolute path.

    Raises:
        ValueError: the slug is not a single safe path segment, or the
            directory does not exist under ``experiments/``.
    """
    if not SLUG_PATTERN.match(experiment):
        raise ValueError(
            f"实验名必须是单个目录名（字母、数字、点、下划线、连字符）：{experiment}"
        )
    directory = project_dir / "experiments" / experiment
    if not directory.is_dir():
        raise ValueError(f"实验目录不存在：{directory}（先在 experiments/ 下建好实验再运行）")
    return directory


def validate_command(command: str) -> None:
    """Accept only a single ``python`` invocation with plain arguments.

    The command runs through ``sh -c`` inside a container that mounts the
    whole project read-write, so a free-form string is an arbitrary-code
    surface the model can reach (directly, or through injected instructions
    in fetched patent pages). The default policy narrows it to what the
    documented flow needs — one python call, no shell operators;
    :data:`ALLOW_ANY_COMMAND_ENV` is the human escape hatch.

    Args:
        command: the caller-supplied command.

    Raises:
        ValueError: the command is not a single python invocation, or it
            carries shell operators.
    """
    if config_value(ALLOW_ANY_COMMAND_ENV) == "1":
        return
    stripped = command.strip()
    words = stripped.split()
    if not words or words[0] not in ("python", "python3") or any(
        char in stripped for char in FORBIDDEN_COMMAND_CHARS
    ):
        raise ValueError(f"命令不被接受：{command!r}。{COMMAND_GUIDANCE}")


def run_experiment(
    project_dir: str,
    experiment: str,
    command: str = DEFAULT_COMMAND,
    timeout_seconds: int = 1800,
) -> str:
    """Run one experiment in the docker runner and record it in the run log.

    The project directory mounts at ``/workspace``; the container's working
    directory is the experiment directory, so the script's relative writes
    land in ``results/`` naturally. When the experiment has a
    ``requirements.txt``, it installs before the command runs. The run log
    records the invocation even when it fails or times out.

        Args:
            project_dir: the patent project directory (absolute path recommended).
            experiment: the experiment slug under ``experiments/``.
            command: one ``python`` invocation with plain arguments to run
                there (default ``python run.py``); shell operators are
                rejected unless ``DSH_EXPERIMENT_ALLOW_ANY_COMMAND=1``.
            timeout_seconds: wall-clock budget, 30-7200 (default 1800).

        Returns:
            The run's combined output tail, followed by the run log's path.

        Raises:
            ValueError: a bad slug, a missing experiment directory, an
                out-of-range timeout, or a command outside the single-python
                policy.
        RuntimeError: docker is unusable, the runner image is missing and
            cannot be pulled, or the command failed (its output tail is
            carried in the message).
    """
    if not MIN_TIMEOUT_SECONDS <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout_seconds 必须在 {MIN_TIMEOUT_SECONDS}-{MAX_TIMEOUT_SECONDS} 之间：{timeout_seconds}"
        )
    root = Path(project_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"项目目录不存在：{project_dir}")
    directory = validate_experiment(root, experiment)
    validate_command(command)
    image = config_value(DOCKER_IMAGE_ENV) or DEFAULT_EXPERIMENT_IMAGE
    ensure_image(image)
    script = f'if [ -f requirements.txt ]; then pip install --no-input -q -r requirements.txt; fi; {command}'
    started = _datetime.datetime.now().astimezone()
    timed_out = False
    try:
        completed = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{root.as_posix()}:/workspace",
                "-w",
                f"/workspace/experiments/{experiment}",
                image,
                "sh",
                "-c",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        code: int | None = completed.returncode
        output = (completed.stdout or "") + (completed.stderr or "")
    except subprocess.TimeoutExpired as expired:
        timed_out = True
        code = None
        output = _as_text(expired.stdout or "") + _as_text(expired.stderr or "")
    tail = output.strip()[-OUTPUT_TAIL_CHARS:]
    fingerprint = code_fingerprint(directory)
    append_run_log(directory, started, image, command, code, tail, fingerprint)
    if timed_out:
        raise RuntimeError(
            f"实验超时（>{timeout_seconds}s）：{experiment}。已记入运行日志；"
            f"优化脚本或提高 timeout_seconds 后重跑。输出尾部：\n{tail}"
        )
    if code != 0:
        raise RuntimeError(
            f"实验运行失败（exit {code}）：{experiment}。已记入运行日志。输出尾部：\n{tail}"
        )
    plot_note = ""
    plot_script = directory / PLOT_SCRIPT_NAME
    if plot_script.is_file():
        plot_started = _datetime.datetime.now().astimezone()
        plot_command = f"python {PLOT_SCRIPT_NAME}"
        plot = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{root.as_posix()}:/workspace",
                "-w",
                f"/workspace/experiments/{experiment}",
                image,
                "sh",
                "-c",
                plot_command,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        plot_tail = ((plot.stdout or "") + (plot.stderr or "")).strip()[-OUTPUT_TAIL_CHARS:]
        append_run_log(directory, plot_started, image, plot_command, plot.returncode, plot_tail, fingerprint)
        figures = sorted(
            str(path.relative_to(directory))
            for path in (directory / "results").glob("*.png")
        )
        plot_note = (
            f"\n出图（exit {plot.returncode}）：{'、'.join(figures) if figures else '未产出 PNG'}\n"
            if plot.returncode == 0
            else f"\n出图失败（exit {plot.returncode}），输出尾部：\n{plot_tail}\n"
        )
    log_path = directory / "results" / RUN_LOG_NAME
    return f"实验完成（exit 0）。输出尾部：\n{tail}{plot_note}\n\n运行记录：{log_path}"


def _as_text(raw: str | bytes) -> str:
    """Decode one captured-output chunk to text, whatever flavor arrived."""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw


def code_fingerprint(directory: Path) -> str:
    r"""Hash the experiment's code files so every run-log entry anchors its numbers.

    Args:
        directory: the experiment directory; everything except ``results/``
            (the run artifacts) participates in the hash.

    Returns:
        ``sha256:<hex>`` over the sorted (relative path, content) pairs.
    """
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or "results" in path.relative_to(directory).parts:
            continue
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()[:16]}"


def append_run_log(
    directory: Path,
    started: _datetime.datetime,
    image: str,
    command: str,
    code: int | None,
    tail: str,
    fingerprint: str | None = None,
) -> Path:
    """Append one run record to the experiment's run log.

    Args:
        directory: the experiment directory; the log lives at
            ``results/run-log.md`` beside the run artifacts.
        started: the invocation's local time with offset.
        image: the docker image the run used.
        command: the shell command the run executed.
        code: the exit code, or ``None`` for a timeout.
        tail: the combined output's tail chars.
        fingerprint: the experiment code's hash, anchoring the numbers to the
            exact code version that produced them.

    Returns:
        The run log's path.
    """
    results = directory / "results"
    results.mkdir(parents=True, exist_ok=True)
    log_path = results / RUN_LOG_NAME
    fingerprint_note = f"\n- 代码指纹：`{fingerprint}`" if fingerprint else ""
    header = (
        f"\n## {started.isoformat(timespec='seconds')}\n\n"
        f"- 镜像：`{image}`\n"
        f"- 命令：`{command}`\n"
        f"- 退出码：{'超时' if code is None else code}{fingerprint_note}\n"
    )
    body = f"- 输出尾部：\n\n```text\n{tail}\n```\n" if tail else ""
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(header + body)
    return log_path


def ensure_image(image: str) -> None:
    """Make the runner image present, pulling it when missing.

    Args:
        image: the image reference to inspect or pull.

    Raises:
        RuntimeError: the docker CLI is absent, or the image is missing and
            the pull fails (with pull/build guidance in the message).
    """
    if shutil.which("docker") is None:
        raise RuntimeError(DOCKER_GUIDANCE)
    inspected = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
    )
    if inspected.returncode == 0:
        return
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
            f"实验镜像不存在且拉取失败：{image}（{detail}）。"
            f"请检查网络后重试 docker pull {image}，或本地构建："
            f'docker build -t {image} -f "{DOCKERFILE}" "{DOCKERFILE.parent}"。'
        )
