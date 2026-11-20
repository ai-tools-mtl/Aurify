"""repo_scan: role-gated fact collection over the demo repo, ledger discipline."""

from __future__ import annotations

import yaml

import pytest

from patent_services.repo_scan import append_scan_ledger, mining_dir_for, scan_repo


@pytest.fixture(autouse=True)
def mining_home(tmp_path, monkeypatch, local_provider):
    """DSH_HOME pointed at a repo-mining.yaml whose local provider binds the demo repo."""
    monkeypatch.setenv("DSH_HOME", str(tmp_path))
    write_config(tmp_path, local_provider, "admin")
    return tmp_path


def write_config(home, provider, declared_role: str) -> None:
    config = {
        "providers": [
            {
                "name": provider.name,
                "platform": "local",
                "base_url": provider.base_url,
                "declared_role": declared_role,
            }
        ],
        "default_provider": provider.name,
    }
    (home / "repo-mining.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")


def test_scan_report_carries_role_facts_and_discipline(tmp_path):
    report = scan_repo(None, "demo-repo", str(tmp_path))
    assert "仓库挖掘事实：demo-repo" in report
    assert "角色：管理员" in report and "声明" in report
    assert "本人提交匹配：1/2" in report  # 张三's init commit is the connected identity's
    assert "模块聚类" in report and "src" in report
    assert "热点文件" in report and "src/engine.py" in report
    assert "v0.1.0" in report
    assert "产出纪律（管理员）" in report and "不能自封" in report
    assert "本人最近提交" in report  # the participant-style own-corpus slice renders for admins too


def test_scan_appends_the_repository_ledger(tmp_path):
    first = scan_repo(None, "demo-repo", str(tmp_path))
    second = scan_repo(None, "demo-repo", str(tmp_path))
    ledger = mining_dir_for(str(tmp_path), "demo-repo") / "ledger.md"
    assert f"（扫描已记录到 {ledger}）" in first
    text = ledger.read_text(encoding="utf-8")
    assert text.count("## ") == 2
    assert text.index("扫描：demo-repo") < text.rindex("扫描：demo-repo")


def test_missing_mining_dir_refuses_upfront(tmp_path):
    with pytest.raises(ValueError, match="挖掘目录不存在"):
        scan_repo(None, "demo-repo", str(tmp_path / "nowhere"))


def test_request_above_the_role_cap_is_clamped_with_a_note(tmp_path):
    report = scan_repo(None, "demo-repo", str(tmp_path), max_commits=500)
    assert "超出" in report and "已按角色上限执行" in report


def test_observer_role_declares_lead_only_output(tmp_path, local_provider):
    write_config(tmp_path, local_provider, "observer")
    report = scan_repo(None, "demo-repo", str(tmp_path))
    assert "角色：观察者" in report
    assert "线索级产出" in report


def test_ledger_append_requires_an_existing_root(tmp_path):
    with pytest.raises(ValueError, match="挖掘目录不存在"):
        append_scan_ledger(str(tmp_path / "nowhere"), "demo-repo", "summary")
