"""Evidence reconciliation for mining candidates — the anti-fabrication gate.

A candidate file claims evidence rows (``- <sha> ｜ <作者> ｜ <改动文件路径>``);
this module re-fetches every cited commit through the same adapters the scan
used and compares sha, author, and touched paths. An unreadable sha, a
mismatched author or path, or an inventor proposal outside the evidence
authors fails the verdict loudly: mining candidates inherit the disclosure
pipeline's rule — a claim without a verifiable source is not a claim, and a
fabricated sha is worse than no candidate at all.
"""

from __future__ import annotations

import re
from pathlib import Path

from .repo_adapters import build_adapter
from .repo_config import resolve_provider

#: One evidence row: ``- <sha> ｜ <作者名或邮箱> ｜ <改动文件路径>``, full-width
#: bars matching the tool outputs' style elsewhere.
EVIDENCE_ROW = re.compile(r"^-\s*([0-9a-fA-F]{7,40})\s*｜\s*([^｜\n]+?)\s*｜\s*([^｜\n]+?)\s*$", re.MULTILINE)

#: The candidate file's identifying header fields (tolerant of ：/:).
FIELD_REPO = re.compile(r"^仓库\s*[:：]\s*(\S+)", re.MULTILINE)
FIELD_PROVIDER = re.compile(r"^平台\s*[:：]\s*(\S+)", re.MULTILINE)
FIELD_ROLE = re.compile(r"^角色\s*[:：]\s*(\S+)", re.MULTILINE)

#: The inventor-proposal section: names listed under 发明人候选 until the next heading.
INVENTOR_SECTION = re.compile(r"^#+\s*发明人候选.*$", re.MULTILINE)


def _extract_inventors(text: str) -> list[str]:
    """Names proposed in the 发明人候选 section, stripped of list markers."""
    match = INVENTOR_SECTION.search(text)
    if not match:
        return []
    rest = text[match.end():]
    names = []
    for line in rest.splitlines():
        if line.startswith("#"):
            break
        name = line.strip().lstrip("-*").strip()
        name = re.split(r"[（(]", name)[0].strip()
        if name:
            names.append(name)
    return names


def _author_matches(candidate: str, commit: dict) -> bool:
    """Whether a listed author names this commit's actual author (name, email,
    or platform login, compared loosely but not fuzzily)."""
    needle = candidate.strip().casefold()
    if not needle:
        return False
    emails = [commit.get("author_email") or ""]
    localparts = [email.split("@")[0] for email in emails if "@" in email]
    return needle in (
        (commit.get("author_name") or "").strip().casefold(),
        *[email.strip().casefold() for email in emails if email],
        *[part.strip().casefold() for part in localparts],
        (commit.get("author_login") or "").strip().casefold(),
    )


def verify_candidate(candidate_path: str, provider_name: str | None = None) -> str:
    """Re-fetch every evidence row in a candidate file and compare.

    Args:
        candidate_path: the candidate markdown file (template from the
            patent-mining skill: 仓库/平台 header fields, an evidence list,
            and optionally a 发明人候选 section).
        provider_name: overrides the file's 平台 field; falls back to the
            config's default provider.

    Returns:
        A Chinese verdict: one line per evidence row (hit or named mismatch),
        the inventor check, and the pass/fail conclusion with the fix.

    Raises:
        ValueError: the file is missing/unreadable, lacks the 仓库 field, or
            cites no evidence at all (a candidate without evidence rows does
            not reconcile — it simply does not stand).
    """
    path = Path(candidate_path)
    if not path.is_file():
        raise ValueError(f"候选文件不存在：{candidate_path}")
    text = path.read_text(encoding="utf-8")

    repo_match = FIELD_REPO.search(text)
    if not repo_match:
        raise ValueError("候选文件缺少「仓库: owner/repo」字段——按 patent-mining 模板补齐后再对账")
    repo = repo_match.group(1).strip()

    rows = EVIDENCE_ROW.findall(text)
    if not rows:
        raise ValueError(
            "候选没有任何证据行（格式：- <commit sha> ｜ <作者> ｜ <改动文件路径>）。"
            "无证据链的候选不成立；禁止编造 sha 凑数。"
        )

    provider_field = FIELD_PROVIDER.search(text)
    provider = resolve_provider(provider_field.group(1).strip() if provider_field else provider_name)
    adapter = build_adapter(provider)

    fetched: dict[str, dict] = {}
    lines = [f"证据对账：{path.name}（仓库 {repo}，平台 {provider.name}/{provider.platform}）"]
    failures = 0
    for sha, author, file_path in rows:
        full_sha = sha.lower()
        commit = None
        problem = ""
        try:
            commit = adapter.get_commit(repo, full_sha)
        except (RuntimeError, ValueError) as exc:
            problem = str(exc)[:120]
        if commit is None:
            failures += 1
            lines.append(f"✗ {sha} ｜ 取不到该提交（{problem}）")
            continue
        fetched[full_sha] = commit
        notes = []
        if not _author_matches(author, commit):
            failures += 1
            notes.append(f"作者不符（实际：{commit.get('author_name') or commit.get('author_login') or '未知'}）")
        touched = {entry["path"] for entry in (commit.get("files") or [])}
        if file_path.strip() not in touched:
            failures += 1
            preview = "、".join(sorted(touched)[:3]) or "（无文件明细）"
            notes.append(f"该提交未改动此文件（实际改动：{preview}）")
        if notes:
            lines.append(f"✗ {sha} ｜ " + "；".join(notes))
        else:
            lines.append(f"✓ {sha} ｜ 作者 {commit.get('author_name', '')} ✓ ｜ {file_path.strip()} ✓")

    inventors = _extract_inventors(text)
    if inventors:
        known = set()
        for commit in fetched.values():
            for form in (commit.get("author_name"), commit.get("author_login"), commit.get("author_email")):
                if form:
                    known.add(form.strip().casefold())
                    if "@" in form:
                        known.add(form.split("@")[0].strip().casefold())
        inventor_lines = []
        for inventor in inventors:
            if inventor.strip().casefold() not in known:
                inventor_lines.append(f"✗ 发明人候选「{inventor}」不在证据 commit 作者中——发明人只能来自真实贡献者，管理员也不例外")
        if inventor_lines:
            failures += len(inventor_lines)
            lines.extend(inventor_lines)
        else:
            lines.append(f"✓ 发明人候选 {len(inventors)} 人均在证据作者之中")

    if failures:
        lines.append("")
        lines.append(
            f"对账失败：{failures} 处失配。虚构或失配的证据必须删除或修正后再提交；"
            "无证据链的候选不成立——这是挖掘侧的反虚构红线。"
        )
    else:
        lines.append("")
        lines.append(f"对账通过：{len(rows)} 条证据全部命中。候选可进入检索评估（patent-research → 三档评估）。")
    return "\n".join(lines)
