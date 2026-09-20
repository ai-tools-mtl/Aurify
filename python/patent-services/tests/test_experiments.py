"""run_experiment validation, docker command shape, and the run log ledger."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from patent_services.experiments import run_experiment


@pytest.fixture
def experiment_dir(tmp_path):
    """A project with one experiment ready to run."""
    directory = tmp_path / "proj" / "experiments" / "throughput-baseline"
    directory.mkdir(parents=True)
    (directory / "run.py").write_text("print('acc=0.93')", encoding="utf-8")
    return directory


@pytest.fixture
def docker_env(tmp_path, monkeypatch):
    """A docker CLI on PATH whose inspect says the image exists."""
    monkeypatch.delenv("DSH_PATENT_EXPERIMENT_IMAGE", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
    )


def test_success_runs_in_experiment_dir_and_records_the_log(docker_env, tmp_path, experiment_dir, monkeypatch):
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="acc=0.93\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_experiment(str(tmp_path / "proj"), "throughput-baseline")
    run_cmd = commands[-1]
    assert run_cmd[:6] == ["docker", "run", "--rm", "-v", f"{(tmp_path / 'proj').resolve().as_posix()}:/workspace", "-w"]
    assert run_cmd[6] == "/workspace/experiments/throughput-baseline"
    assert run_cmd[7] == "q771103517/dsh-patent-experiment:latest"
    assert run_cmd[8:10] == ["sh", "-c"]
    assert "python run.py" in run_cmd[10]
    assert "acc=0.93" in result
    log = experiment_dir / "results" / "run-log.md"
    assert log.is_file()
    text = log.read_text(encoding="utf-8")
    assert "q771103517/dsh-patent-experiment:latest" in text
    assert "退出码：0" in text
    assert "acc=0.93" in text


def test_requirements_install_chains_before_the_command(docker_env, tmp_path, experiment_dir, monkeypatch):
    (experiment_dir / "requirements.txt").write_text("networkx\n", encoding="utf-8")
    scripts = []

    def fake_run(cmd, **kwargs):
        if cmd[1] == "run":
            scripts.append(cmd[cmd.index("-c") + 1])
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_experiment(str(tmp_path / "proj"), "throughput-baseline")
    assert "pip install" in scripts[0]
    assert "-r requirements.txt" in scripts[0]
    assert "python run.py" in scripts[0]


def test_failure_still_records_the_log_and_carries_the_tail(docker_env, tmp_path, experiment_dir, monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd[1] == "run":
            return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="Traceback: boom\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="exit 2"):
        run_experiment(str(tmp_path / "proj"), "throughput-baseline")
    text = (experiment_dir / "results" / "run-log.md").read_text(encoding="utf-8")
    assert "退出码：2" in text
    assert "Traceback: boom" in text


def test_timeout_records_and_names_the_budget(docker_env, tmp_path, experiment_dir, monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd[1] == "run":
            raise subprocess.TimeoutExpired(cmd, 30, output="partial output".encode())
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="超时"):
        run_experiment(str(tmp_path / "proj"), "throughput-baseline", timeout_seconds=30)
    text = (experiment_dir / "results" / "run-log.md").read_text(encoding="utf-8")
    assert "退出码：超时" in text
    assert "partial output" in text


def test_missing_image_pulls_then_runs(tmp_path, experiment_dir, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[2] == "inspect":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="missing")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_experiment(str(tmp_path / "proj"), "throughput-baseline")
    assert calls[0][1:3] == ["image", "inspect"]
    assert calls[1] == ["docker", "pull", "q771103517/dsh-patent-experiment:latest"]


def test_failed_pull_names_the_local_build(tmp_path, monkeypatch):
    (tmp_path / "proj" / "experiments" / "throughput-baseline").mkdir(parents=True)
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="network down")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="docker build"):
        run_experiment(str(tmp_path / "proj"), "throughput-baseline")


def test_missing_docker_cli_gives_desktop_guidance(tmp_path, monkeypatch):
    (tmp_path / "proj" / "experiments" / "throughput-baseline").mkdir(parents=True)
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="Docker Desktop"):
        run_experiment(str(tmp_path / "proj"), "throughput-baseline")


def test_image_override_env(tmp_path, experiment_dir, monkeypatch):
    monkeypatch.setenv("DSH_PATENT_EXPERIMENT_IMAGE", "local/experiment:dev")
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_experiment(str(tmp_path / "proj"), "throughput-baseline")
    run_cmd = commands[-1]
    assert run_cmd[7] == "local/experiment:dev"


def test_slug_must_be_one_safe_segment(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    for bad in ("../evil", "a/b", ".hidden", ""):
        with pytest.raises(ValueError, match="单个目录名"):
            run_experiment(str(tmp_path), bad)


def test_missing_experiment_directory(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    with pytest.raises(ValueError, match="实验目录不存在"):
        run_experiment(str(tmp_path), "ghost")


def test_missing_project_directory(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    with pytest.raises(ValueError, match="项目目录不存在"):
        run_experiment(str(tmp_path / "nowhere"), "any")


def test_timeout_out_of_range(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    (tmp_path / "experiments" / "tiny").mkdir(parents=True)
    with pytest.raises(ValueError, match="timeout_seconds"):
        run_experiment(str(tmp_path), "tiny", timeout_seconds=1)


@pytest.mark.parametrize(
    "command",
    [
        "python run.py",
        "python3 run.py --trials 100",
        "python -m pytest -q",
        'python run.py --name "two words"',
    ],
)
def test_command_policy_accepts_single_python_calls(tmp_path, monkeypatch, command):
    monkeypatch.delenv("DSH_EXPERIMENT_ALLOW_ANY_COMMAND", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    (tmp_path / "experiments" / "sim").mkdir(parents=True)
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
    )
    assert run_experiment(str(tmp_path), "sim", command=command)


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /workspace",
        "sh run.sh",
        "bash -c 'python run.py'",
        "python run.py && python plot_results.py",
        "python run.py; ls",
        "python run.py | tee results/log.txt",
        "python run.py > results/out.txt",
        "python run.py $(whoami)",
        "python run.py `id`",
        "python run.py\nrm -rf .",
        "",
    ],
)
def test_command_policy_rejects_shell_operators_and_non_python(tmp_path, monkeypatch, command):
    monkeypatch.delenv("DSH_EXPERIMENT_ALLOW_ANY_COMMAND", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    (tmp_path / "experiments" / "sim").mkdir(parents=True)
    with pytest.raises(ValueError, match="命令不被接受") as excinfo:
        run_experiment(str(tmp_path), "sim", command=command)
    assert "DSH_EXPERIMENT_ALLOW_ANY_COMMAND" in str(excinfo.value)


def test_command_policy_escape_hatch_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DSH_EXPERIMENT_ALLOW_ANY_COMMAND", "1")
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    (tmp_path / "experiments" / "sim").mkdir(parents=True)
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
    )
    assert run_experiment(str(tmp_path), "sim", command="bash run.sh && python run.py")


@pytest.mark.parametrize("command", ["python -c 'print(1)'", "python3 -c print(1)"])
def test_command_policy_rejects_inline_code(tmp_path, monkeypatch, command):
    monkeypatch.delenv("DSH_EXPERIMENT_ALLOW_ANY_COMMAND", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    (tmp_path / "experiments" / "sim").mkdir(parents=True)
    with pytest.raises(ValueError, match="python -c"):
        run_experiment(str(tmp_path), "sim", command=command)


def _capturing_run(sink):
    def _run(cmd, **kwargs):
        sink.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")
    return _run


def test_requirements_install_defaults_to_wheels_only(tmp_path, monkeypatch):
    monkeypatch.delenv("DSH_EXPERIMENT_PIP_ALLOW_SOURCE", raising=False)
    monkeypatch.delenv("DSH_EXPERIMENT_ALLOW_ANY_COMMAND", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    experiment = tmp_path / "experiments" / "sim"
    experiment.mkdir(parents=True)
    (experiment / "requirements.txt").write_text("numpy\n", encoding="utf-8")
    sink: list = []
    monkeypatch.setattr(subprocess, "run", _capturing_run(sink))
    assert run_experiment(str(tmp_path), "sim")
    assert "--only-binary :all:" in sink[-1][-1]


def test_requirements_install_allows_source_with_the_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("DSH_EXPERIMENT_PIP_ALLOW_SOURCE", "1")
    monkeypatch.delenv("DSH_EXPERIMENT_ALLOW_ANY_COMMAND", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    experiment = tmp_path / "experiments" / "sim"
    experiment.mkdir(parents=True)
    (experiment / "requirements.txt").write_text("numpy\n", encoding="utf-8")
    sink: list = []
    monkeypatch.setattr(subprocess, "run", _capturing_run(sink))
    assert run_experiment(str(tmp_path), "sim")
    assert "--only-binary" not in sink[-1][-1]
