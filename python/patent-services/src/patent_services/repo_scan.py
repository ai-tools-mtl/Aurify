"""Role-gated repository fact collection for patent mining.

The scan collects facts — commit statistics, module clusters, hotspot files,
merged PRs, releases, contributors — and states the role's attribution
discipline alongside them. It never invents a candidate idea: interpretation
belongs to the model steered by the patent-mining skill; this module's job is
to make every fact traceable and every budget binding. Caps resolve through
repo_roles' matrix intersected with the config limit, so no prompt can push a
scan past the role's budget, and every scan appends the repository's mining
ledger — the durable half of the story, like search-history.md.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from .repo_adapters import build_adapter
from .repo_config import load_provider_config, resolve_provider, scan_limit
from .repo_roles import (
    detail_cap,
    describe_role,
    effective_commit_cap,
    role_discipline_lines,
)

#: The mining workspace's directory name inside the user's mining_dir:
#: each repository keeps one subdirectory with its ledger and candidates.
LEDGER_ROOT_NAME = "repo-mining"

#: The scan ledger's name inside a repository's mining directory.
SCAN_LEDGER_NAME = "ledger.md"

#: Report sizes: the facts stay readable — the model deep-reads single
#: commits through repo_read_object when it needs more.
TOP_HOTSPOTS = 10
TOP_MODULES = 8
TOP_AUTHORS = 10
TOP_PULLS = 10
TOP_RELEASES = 5
TOP_CONTRIBUTORS = 10


def mining_dir_for(mining_dir: str, full_name: str) -> Path:
    """One repository's mining directory: ``<mining_dir>/repo-mining/<owner>__<repo>``."""
    slug = full_name.strip().strip("/").replace("/", "__")
    return Path(mining_dir) / LEDGER_ROOT_NAME / slug


def append_scan_ledger(mining_dir: str, full_name: str, summary: str) -> Path:
    """Append one scan's summary to the repository's mining ledger.

    Args:
        mining_dir: the user-provided workspace directory (must exist — a
            missing one is refused, mirroring the search ledger's contract).
        full_name: the scanned repository (owner/repo).
        summary: the scan's headline facts, recorded verbatim.

    Returns:
        The ledger file's path.

    Raises:
        ValueError: the mining directory does not exist.
    """
    root = Path(mining_dir)
    if not root.is_dir():
        raise ValueError(f"挖掘目录不存在：{mining_dir}（先建好目录再扫描，账本不落无根之地）")
    directory = mining_dir_for(mining_dir, full_name)
    directory.mkdir(parents=True, exist_ok=True)
    ledger = directory / SCAN_LEDGER_NAME
    stamp = datetime.now().isoformat(timespec="seconds")
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(f"## {stamp} ｜ {summary}\n\n")
    return ledger


def format_commit_detail(commit: dict) -> str:
    """Render one deep-read commit: who/when/what plus the touched-file table.

    Patch excerpts follow their file when the platform provided them; the
    local adapter leaves them empty and the note says so.
    """
    lines = [
        f"commit {commit.get('sha', '')} ｜ {commit.get('author_name', '')} <{commit.get('author_email', '')}> ｜ {commit.get('date', '')}",
        commit.get("message", ""),
    ]
    if commit.get("web_url"):
        lines.append(f"链接：{commit['web_url']}")
    files = commit.get("files") or []
    if not files:
        lines.append("（无文件明细——列表接口不携带，需单commit深读）")
    for entry in files:
        lines.append(f"- {entry['path']}（+{entry['additions']}/-{entry['deletions']}）")
        if entry.get("patch_head"):
            lines.append("```diff")
            lines.append(entry["patch_head"])
            lines.append("```")
    return "\n".join(lines)


def format_pull(pull: dict) -> str:
    """One merged/closed pull request as a ledger-style line."""
    state = "已合并" if pull.get("merged") else "未合并"
    return f"#{pull.get('number')} ｜ {pull.get('title', '')} ｜ @{pull.get('author', '')} ｜ {state} ｜ {pull.get('date', '')}"


def format_release(release: dict) -> str:
    """One release/tag as a ledger-style line."""
    parts = [release.get("tag", ""), release.get("name", ""), release.get("date", "")]
    seen = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    line = " ｜ ".join(seen)
    if release.get("notes_head"):
        line += "\n  " + release["notes_head"].replace("\n", "\n  ")
    return line


def _module_of(file_path: str) -> str:
    """A file's top-level module: its first path segment (root files together)."""
    segments = file_path.replace("\\", "/").split("/")
    return segments[0] if len(segments) > 1 else "（根目录）"


def scan_repo(provider_name: str | None, repo: str, mining_dir: str, max_commits: int | None = None) -> str:
    """Collect one repository's mining facts under the connected user's role.

    The report carries: identity and role (with its mapping basis), the
    effective commit cap, commit time spread and the user's own share,
    author distribution, module clusters and hotspot files from the deep-read
    slice, merged PRs, releases, contributors, and the role's attribution
    discipline. Every successful scan appends the repository's ledger.

    Args:
        provider_name: the repo-mining.yaml provider to use (default rules
            apply when omitted).
        repo: the repository, ``owner/repo`` (local: any name — the adapter
            binds to the configured directory).
        mining_dir: the workspace directory receiving ``repo-mining/<repo>/``.
        max_commits: requested scan size; clamped to the role's budget.

    Returns:
        The Chinese facts report, ending with the ledger path.

    Raises:
        ValueError: bad provider name, unknown repo form, missing mining dir.
        RuntimeError: the platform is unreachable or answered unexpectedly.
    """
    provider = resolve_provider(provider_name)
    if not Path(mining_dir).is_dir():
        raise ValueError(f"挖掘目录不存在：{mining_dir}（先建好目录再扫描，账本不落无根之地）")
    adapter = build_adapter(provider)
    info = adapter.repo_info(repo)
    full_name = info["full_name"] or repo
    role = info["role"]

    cap, cap_note = effective_commit_cap(role, scan_limit(load_provider_config()), max_commits)
    commits = adapter.list_commits(full_name, cap)

    identity = adapter.identity()
    own = _count_own_commits(commits, identity)

    deep = detail_cap(role)
    details = []
    deep_failures = 0
    for commit in commits[:deep]:
        try:
            details.append(adapter.get_commit(full_name, commit["sha"]))
        except (RuntimeError, ValueError):
            deep_failures += 1  # one flaky commit never kills the scan

    lines = [f"# 仓库挖掘事实：{full_name}（{provider.platform}/{provider.name}）"]
    lines.append(identity_line(identity))
    lines.append(describe_role(role, info.get("role_basis", "平台权限")))
    lines.append(f"默认分支：{info.get('default_branch', '?')}")
    lines.append(f"扫描提交数：{len(commits)}（角色上限 {cap}）")
    if cap_note:
        lines.append(f"（{cap_note}）")
    if commits:
        dates = sorted(commit.get("date", "") for commit in commits if commit.get("date"))
        lines.append(f"提交时间跨度：{dates[0][:10]} ~ {dates[-1][:10]}")
    lines.append(f"本人提交匹配：{own}/{len(commits)}（按邮箱/账号与接入身份比对）")
    if deep_failures:
        lines.append(f"（{deep_failures} 个提交深读失败，已跳过）")

    lines.append("")
    lines.append(f"## 模块聚类（最近 {len(details)} 个深读提交）")
    module_lines = _module_lines(details)
    lines.extend(module_lines or ["（无数据）"])

    lines.append("")
    lines.append("## 作者分布")
    author_counts = Counter((commit.get("author_name") or commit.get("author_email") or "?") for commit in commits)
    for name, count in author_counts.most_common(TOP_AUTHORS):
        tag = "（本人）" if _is_own_author(name, commits, identity) else ""
        lines.append(f"- {name}：{count}{tag}")
    if not author_counts:
        lines.append("（无数据）")

    lines.append("")
    lines.append(f"## 热点文件（基于最近 {len(details)} 个提交的文件明细，按改动频次×规模）")
    hotspot_lines = _hotspot_lines(details)
    lines.extend(hotspot_lines or ["（无数据）"])

    if own:
        lines.append("")
        lines.append("## 本人最近提交（接入身份的核心语料）")
        for commit in commits[:10]:
            if _commit_is_own(commit, identity):
                lines.append(f"- {commit['sha'][:12]} ｜ {commit.get('date', '')[:10]} ｜ {commit.get('message', '')}")

    lines.append("")
    lines.append(f"## 合并的 PR（最近 {TOP_PULLS} 条）")
    pulls = adapter.list_pulls(full_name, TOP_PULLS)
    if pulls:
        lines.extend(f"- {format_pull(pull)}" for pull in pulls)
    else:
        lines.append("（平台未提供 PR 数据——本地仓库无 PR 概念，或仓库没有已合并请求）")

    lines.append("")
    lines.append(f"## Releases / 标签（最近 {TOP_RELEASES} 个）")
    releases = adapter.list_releases(full_name, TOP_RELEASES)
    if releases:
        lines.extend(f"- {format_release(release)}" for release in releases)
    else:
        lines.append("（无 release/tag）")

    lines.append("")
    lines.append(f"## 贡献者排行（前 {TOP_CONTRIBUTORS}）")
    ranking = adapter.contributors(full_name, TOP_CONTRIBUTORS)
    if ranking:
        lines.extend(f"- {entry['name']}：{entry['count']}" for entry in ranking)
    else:
        lines.append("（无数据）")

    lines.append("")
    lines.extend(role_discipline_lines(role))
    lines.append("下一步：从这些事实提炼候选点子时，按 patent-mining 技能的候选文件模板落盘，证据链逐条可对账。")

    ledger = append_scan_ledger(mining_dir, full_name, f"扫描：{full_name}（角色 {role}，{len(commits)} 提交，深读 {len(details)}）")
    lines.append("")
    lines.append(f"（扫描已记录到 {ledger}）")
    return "\n".join(lines)


def identity_line(identity: dict) -> str:
    """The connected identity's one-line statement."""
    login = identity.get("login") or "（未取到账号）"
    extras = [part for part in (identity.get("name"), identity.get("email")) if part and part != login]
    return "接入身份：" + login + ("（" + "，".join(extras) + "）" if extras else "")


def _count_own_commits(commits: list[dict], identity: dict) -> int:
    return sum(1 for commit in commits if _commit_is_own(commit, identity))


def _commit_is_own(commit: dict, identity: dict) -> bool:
    email = (identity.get("email") or "").strip().lower()
    login = (identity.get("login") or "").strip().lower()
    if email and (commit.get("author_email") or "").strip().lower() == email:
        return True
    if login and (commit.get("author_login") or "").strip().lower() == login:
        return True
    return False


def _is_own_author(name: str, commits: list[dict], identity: dict) -> bool:
    return any(commit.get("author_name") == name and _commit_is_own(commit, identity) for commit in commits)


def _module_lines(details: list[dict]) -> list[str]:
    """Module clusters: commit counts per top-level module across the deep-read slice."""
    counter: Counter[str] = Counter()
    for commit in details:
        modules = {_module_of(entry["path"]) for entry in (commit.get("files") or []) if entry.get("path")}
        for module in modules:
            counter[module] += 1
    return [f"- {module}：{count} 个提交" for module, count in counter.most_common(TOP_MODULES)]


def _hotspot_lines(details: list[dict]) -> list[str]:
    """Hotspot files: change frequency first, churn (adds+dels) as the tiebreak."""
    frequency: Counter[str] = Counter()
    churn: Counter[str] = Counter()
    for commit in details:
        for entry in commit.get("files") or []:
            if not entry.get("path"):
                continue
            frequency[entry["path"]] += 1
            churn[entry["path"]] += int(entry.get("additions") or 0) + int(entry.get("deletions") or 0)
    ranked = sorted(frequency, key=lambda path: (-frequency[path], -churn[path]))
    return [f"- {path}（{frequency[path]} 次，+/-共 {churn[path]} 行）" for path in ranked[:TOP_HOTSPOTS]]
