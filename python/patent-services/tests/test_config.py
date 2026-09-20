"""Optional settings resolve env-first, then ~/.dsh/patent-services.yaml."""

from __future__ import annotations

import textwrap

import pytest

from patent_services.config import config_file, config_value, load_options


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An isolated $DSH_HOME holding no settings file yet."""
    monkeypatch.setenv("DSH_HOME", str(tmp_path))
    for key in ("DSH_EXPERIMENT_ALLOW_ANY_COMMAND", "DSH_DRAWIO_BIN", "DSH_PATENT_EXPERIMENT_IMAGE"):
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def write_settings(home, body: str) -> None:
    config_file().write_text(textwrap.dedent(body), encoding="utf-8")


def test_missing_file_yields_nothing(home):
    assert load_options() == {}
    assert config_value("DSH_DRAWIO_BIN") is None


def test_file_key_resolves_from_the_snake_form(home):
    write_settings(home, """
        drawio_bin: D:/tools/draw.io.exe
        experiment_image: local/experiment:dev
    """)
    assert config_value("DSH_DRAWIO_BIN") == "D:/tools/draw.io.exe"
    assert config_value("DSH_PATENT_EXPERIMENT_IMAGE") == "local/experiment:dev"


def test_env_beats_the_file(home, monkeypatch):
    write_settings(home, "drawio_bin: D:/from/file.exe\n")
    monkeypatch.setenv("DSH_DRAWIO_BIN", "D:/from/env.exe")
    assert config_value("DSH_DRAWIO_BIN") == "D:/from/env.exe"


def test_yaml_true_normalizes_to_the_env_one_form(home):
    write_settings(home, "experiment_allow_any_command: true\n")
    assert config_value("DSH_EXPERIMENT_ALLOW_ANY_COMMAND") == "1"


def test_yaml_false_and_empty_string_mean_unset(home):
    write_settings(home, """
        experiment_allow_any_command: false
        drawio_bin: ""
    """)
    assert config_value("DSH_EXPERIMENT_ALLOW_ANY_COMMAND") is None
    assert config_value("DSH_DRAWIO_BIN") is None


def test_broken_yaml_is_tolerated_as_empty(home):
    config_file().write_text("drawio_bin: [unclosed\n  - broken", encoding="utf-8")
    assert load_options() == {}
    assert config_value("DSH_DRAWIO_BIN") is None


def test_default_home_without_env(tmp_path, monkeypatch):
    monkeypatch.delenv("DSH_HOME", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config_file() == tmp_path / ".dsh" / "patent-services.yaml"


def test_the_experiments_policy_reads_through_the_config_file(home):
    from patent_services.experiments import validate_command
    write_settings(home, "experiment_allow_any_command: true\n")
    # The escape hatch now flips via the file, not only via setx.
    assert validate_command("bash run.sh") is None


def test_the_experiment_image_reads_through_the_config_file(home, tmp_path, monkeypatch):
    from patent_services import experiments
    write_settings(home, "experiment_image: local/experiment:dev\n")
    monkeypatch.setattr("shutil.which", lambda name: "docker.exe" if name == "docker" else None)
    commands = []

    import subprocess as sp

    def fake_run(cmd, **kwargs):
        commands.append(list(cmd))
        return sp.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(sp, "run", fake_run)
    (tmp_path / "proj" / "experiments" / "sim").mkdir(parents=True)
    experiments.run_experiment(str(tmp_path / "proj"), "sim")
    assert commands[-1][7] == "local/experiment:dev"
