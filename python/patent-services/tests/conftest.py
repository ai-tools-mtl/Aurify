"""Shared fixtures for the mining tests: a real temporary git repository.

The local adapter and the scan/evidence flows are exercised against a genuine
clone built in tmp_path — two commits by two authors across two modules, one
tag — so history parsing, attribution, and evidence reconciliation run on
real git output, not fixtures of it.
"""

from __future__ import annotations

import subprocess

import pytest


def run_git(repo_dir, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo_dir), *args], check=True, capture_output=True)


@pytest.fixture
def demo_repo(tmp_path):
    """A temp git repo: 张三's initial engine commit (tag v0.1.0), then 李四's
    cache-layer commit touching engine.py and adding cache.py."""
    repo_dir = tmp_path / "demo-repo"
    repo_dir.mkdir()
    run_git(repo_dir, "init")
    run_git(repo_dir, "symbolic-ref", "HEAD", "refs/heads/main")
    run_git(repo_dir, "config", "user.name", "张三")
    run_git(repo_dir, "config", "user.email", "zhang@example.com")
    src = repo_dir / "src"
    src.mkdir()
    (src / "engine.py").write_text("value = 1\n", encoding="utf-8")
    docs = repo_dir / "docs"
    docs.mkdir()
    (docs / "README.md").write_text("# demo\n", encoding="utf-8")
    run_git(repo_dir, "add", ".")
    run_git(repo_dir, "commit", "-m", "init engine module")
    run_git(repo_dir, "tag", "v0.1.0")
    (src / "engine.py").write_text("value = 2\n", encoding="utf-8")
    (src / "cache.py").write_text("cache = {}\n", encoding="utf-8")
    run_git(repo_dir, "add", ".")
    run_git(repo_dir, "-c", "user.name=李四", "-c", "user.email=li@example.com", "commit", "-m", "add cache layer")
    return repo_dir


@pytest.fixture
def local_provider(demo_repo):
    """A local-platform provider bound to the demo repo, declared admin."""
    from patent_services.repo_config import Provider

    return Provider(
        name="demo-local",
        platform="local",
        base_url=str(demo_repo),
        token=None,
        declared_role="admin",
    )
