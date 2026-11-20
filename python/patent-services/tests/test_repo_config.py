"""repo_config: file loading, provider resolution, token handling, redaction."""

from __future__ import annotations

import pytest

from patent_services import repo_config

CONFIG = """
# 注释必须能在对账删除后幸存
providers:
  - name: company-gitlab
    platform: gitlab
    base_url: https://gitlab.internal.example.com
    token: glpat-abcdefghij
  - name: backup
    platform: local
    base_url: /tmp/demo-repo
    declared_role: participant
default_provider: company-gitlab
limits:
  max_commits_per_scan: 150
"""


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("DSH_HOME", str(tmp_path))
    return tmp_path


def write_config(tmp_path, text: str) -> None:
    (tmp_path / "repo-mining.yaml").write_text(text, encoding="utf-8")


def test_missing_file_yields_empty_config():
    assert repo_config.load_provider_config() == {}


def test_broken_yaml_fails_loud_with_the_file_name(tmp_path):
    write_config(tmp_path, "providers: [oops\n  bad yaml: :")
    with pytest.raises(RuntimeError, match="repo-mining.yaml"):
        repo_config.load_provider_config()


def test_provider_missing_name_or_platform_is_rejected(tmp_path):
    write_config(tmp_path, "providers:\n  - platform: github\n")
    with pytest.raises(ValueError, match="name"):
        repo_config.resolve_provider(None)
    write_config(tmp_path, "providers:\n  - name: x\n    platform: svn\n")
    with pytest.raises(ValueError, match="platform"):
        repo_config.resolve_provider(None)


def test_duplicate_provider_names_are_rejected(tmp_path):
    write_config(tmp_path, "providers:\n  - name: a\n    platform: github\n  - name: a\n    platform: gitlab\n")
    with pytest.raises(ValueError, match="重复"):
        repo_config.resolve_provider("a")


def test_local_provider_requires_a_clone_path(tmp_path):
    write_config(tmp_path, "providers:\n  - name: l\n    platform: local\n")
    with pytest.raises(ValueError, match="base_url"):
        repo_config.resolve_provider("l")


def test_resolve_provider_default_and_by_name(tmp_path):
    write_config(tmp_path, CONFIG)
    assert repo_config.resolve_provider(None).name == "company-gitlab"
    assert repo_config.resolve_provider("backup").platform == "local"
    with pytest.raises(ValueError, match="company-gitlab"):
        repo_config.resolve_provider("nope")


def test_ambiguous_providers_require_a_choice(tmp_path):
    write_config(tmp_path, "providers:\n  - name: a\n    platform: github\n  - name: b\n    platform: gitee\n")
    with pytest.raises(ValueError, match="provider"):
        repo_config.resolve_provider(None)


def test_env_token_wins_over_the_file_value(tmp_path, monkeypatch):
    write_config(tmp_path, CONFIG)
    provider = repo_config.resolve_provider(None)
    monkeypatch.delenv("DSH_PATENT_REPO_TOKEN_COMPANY_GITLAB", raising=False)
    assert repo_config.resolve_token(provider) == "glpat-abcdefghij"
    monkeypatch.setenv("DSH_PATENT_REPO_TOKEN_COMPANY_GITLAB", "env-token")
    assert repo_config.resolve_token(provider) == "env-token"


def test_token_env_name_folds_punctuation(monkeypatch):
    assert repo_config.token_env_name("my-git.gitee") == "DSH_PATENT_REPO_TOKEN_MY_GIT_GITEE"


def test_redact_token_masks_everything_but_a_tail():
    assert repo_config.redact_token(None) == "（未配置）"
    assert repo_config.redact_token("short") == "****"
    assert repo_config.redact_token("glpat-abcdefghij") == "****ghij"


def test_remove_token_keeps_comments_and_neighbors(tmp_path):
    write_config(tmp_path, CONFIG)
    removed, path = repo_config.remove_token_from_file("company-gitlab")
    assert removed
    text = path.read_text(encoding="utf-8")
    assert "token:" not in text.split("backup")[0]
    assert "注释必须能" in text  # the comment survived the line surgery
    assert "glpat-abcdefghij" not in text
    again, _ = repo_config.remove_token_from_file("company-gitlab")
    assert not again


def test_remove_token_refuses_a_broken_file(tmp_path):
    write_config(tmp_path, "providers: [oops")
    with pytest.raises(RuntimeError, match="YAML"):
        repo_config.remove_token_from_file("company-gitlab")


def test_scan_limit_reads_the_config_cap(tmp_path):
    write_config(tmp_path, CONFIG)
    assert repo_config.scan_limit() == 150
    write_config(tmp_path, "providers:\n  - name: a\n    platform: github\n")
    assert repo_config.scan_limit() is None
