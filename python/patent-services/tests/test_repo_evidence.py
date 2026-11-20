"""repo_evidence: candidate evidence reconciliation against the real demo repo."""

from __future__ import annotations

import yaml

import pytest

from patent_services.repo_adapters import build_adapter
from patent_services.repo_config import Provider
from patent_services.repo_evidence import verify_candidate


@pytest.fixture(autouse=True)
def mining_home(tmp_path, monkeypatch, local_provider):
    monkeypatch.setenv("DSH_HOME", str(tmp_path))
    config = {
        "providers": [
            {
                "name": local_provider.name,
                "platform": "local",
                "base_url": local_provider.base_url,
                "declared_role": "admin",
            }
        ],
        "default_provider": local_provider.name,
    }
    (tmp_path / "repo-mining.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return tmp_path


@pytest.fixture
def evidence_shas(local_provider):
    adapter = build_adapter(local_provider)
    return [commit["sha"] for commit in adapter.list_commits("demo-repo", 10)]


def write_candidate(tmp_path, sha: str, author: str = "李四", path: str = "src/cache.py",
                    inventors: tuple = ("李四",)) -> str:
    inventor_lines = "\n".join(f"- {name}（候选理由）" for name in inventors)
    text = (
        "仓库: demo-repo\n"
        "平台: demo-local\n"
        "角色: admin\n"
        "\n"
        "# 挖掘候选：独立缓存层\n"
        "\n"
        "点子：把缓存从引擎中独立成模块……\n"
        "\n"
        "## 证据链\n"
        "\n"
        f"- {sha} ｜ {author} ｜ {path}\n"
        "\n"
        "## 发明人候选\n"
        "\n"
        f"{inventor_lines}\n"
    )
    candidate = tmp_path / "candidates" / "cache.md"
    candidate.parent.mkdir(exist_ok=True)
    candidate.write_text(text, encoding="utf-8")
    return str(candidate)


def test_genuine_evidence_passes(tmp_path, evidence_shas):
    candidate = write_candidate(tmp_path, evidence_shas[0])
    verdict = verify_candidate(candidate)
    assert "对账通过" in verdict
    assert "1 条证据全部命中" in verdict
    assert "发明人候选 1 人均在证据作者之中" in verdict


def test_wrong_author_fails_with_the_real_one_named(tmp_path, evidence_shas):
    candidate = write_candidate(tmp_path, evidence_shas[0], author="王五")
    verdict = verify_candidate(candidate)
    assert "作者不符" in verdict and "李四" in verdict
    assert "对账失败" in verdict


def test_wrong_path_fails_listing_what_actually_changed(tmp_path, evidence_shas):
    candidate = write_candidate(tmp_path, evidence_shas[0], path="docs/none.md")
    verdict = verify_candidate(candidate)
    assert "未改动此文件" in verdict
    assert "对账失败" in verdict


def test_invented_sha_cannot_reconcile(tmp_path, evidence_shas):
    candidate = write_candidate(tmp_path, "deadbeef000")
    verdict = verify_candidate(candidate)
    assert "取不到该提交" in verdict
    assert "对账失败" in verdict


def test_inventor_outside_the_evidence_authors_fails(tmp_path, evidence_shas):
    candidate = write_candidate(tmp_path, evidence_shas[0], inventors=("王五",))
    verdict = verify_candidate(candidate)
    assert "不在证据 commit 作者中" in verdict
    assert "对账失败" in verdict


def test_missing_repo_field_is_a_template_fault(tmp_path):
    candidate = tmp_path / "candidates" / "x.md"
    candidate.parent.mkdir()
    candidate.write_text("- abc1234def ｜ 某人 ｜ a.py\n", encoding="utf-8")
    with pytest.raises(ValueError, match="仓库"):
        verify_candidate(candidate)


def test_no_evidence_rows_is_rejected(tmp_path, evidence_shas):
    candidate = tmp_path / "candidates" / "empty.md"
    candidate.parent.mkdir()
    candidate.write_text("仓库: demo-repo\n平台: demo-local\n\n（没有证据）\n", encoding="utf-8")
    with pytest.raises(ValueError, match="证据行"):
        verify_candidate(candidate)


def test_missing_candidate_file(tmp_path):
    with pytest.raises(ValueError, match="不存在"):
        verify_candidate(str(tmp_path / "nowhere.md"))
