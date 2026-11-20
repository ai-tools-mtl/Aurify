"""Transport adapters for the four mining platforms behind one interface.

GitHub REST v3, GitLab REST v4, Gitee REST v5, and a local git adapter share
one normalized surface — identity, repo list with roles, commits, pull
requests, releases, file content, contributors — so the scan and evidence
modules never branch on platform. HTTP follows prior_art.py's discipline:
stdlib urllib, explicit timeout, in-process TTL cache, fail-loud Chinese
remedies (an unreachable private host names the VPN/base_url fix instead of
returning an empty result). Tokens ride headers only and never enter error
text, which quotes the request path, not the URL. The local adapter shells
out fixed-argument subprocess git against an existing clone — no shell, and
refs/shas are rejected when they could parse as git options. Repository
content is untrusted data: fetched as text, returned, never executed.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from .repo_config import Provider
from .repo_roles import gitlab_level_to_role, role_from_permissions_dict, validate_declared_role

#: Seconds one HTTP request may run before failing loud.
REQUEST_TIMEOUT_SECONDS = 30

#: Seconds one identical request's payload stays cached in this process.
CACHE_TTL_SECONDS = 1800

#: Upper bound on cached responses so a long-lived server cannot grow forever.
CACHE_MAX_ENTRIES = 100

#: Page size for every paged listing (all three REST platforms accept it).
PER_PAGE = 50

#: Hard bound on pagination walks: at most this many full pages per list.
MAX_PAGES = 8

#: A single file read returns at most this many bytes before an explicit
#: truncation note — hotspot reading is for evidence, not bulk export.
MAX_FILE_BYTES = 200_000

#: Patch excerpt kept per file in a commit detail.
PATCH_HEAD_LINES = 12

#: Browser User-Agent: some corporate proxies reject bare library clients.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

#: The in-process cache: (platform, base, path, params) -> (monotonic time,
#: payload). Server-process lifetime only — a restart forgets it, by design.
_REST_CACHE: dict[tuple[str, str, str, tuple[tuple[str, str], ...]], tuple[float, object]] = {}

NETWORK_REMEDY = (
    "无法访问 {base}：请确认 VPN/内网已连通、平台地址拼写正确；"
    "自建平台需在 ~/.dsh/repo-mining.yaml 里为该 provider 配置 base_url（根地址，不带 /api）后重试。"
)

_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{4,40}$")


def _safe_sha(sha: str) -> str:
    """Validate a commit ref before it enters a URL path or git argv.

    Raises:
        ValueError: empty, or not a plain hex prefix (a crafted value could
            otherwise change the request path).
    """
    cleaned = str(sha).strip()
    if not _SHA_PATTERN.match(cleaned):
        raise ValueError(f"commit ref 必须是 4-40 位十六进制 sha：{sha!r}")
    return cleaned


def _safe_plain(value: str) -> str:
    """Validate a git ref or file path for the local adapter's argv.

    No shell is involved, so the only risk is git option parsing; a leading
    dash or control character is rejected outright.
    """
    cleaned = str(value).strip()
    if not cleaned or cleaned.startswith("-") or any(ch in cleaned for ch in "\x00\n\r"):
        raise ValueError(f"非法参数（不允许空值、前导 - 或控制字符）：{value!r}")
    return cleaned


def _safe_repo_path(full_name: str) -> str:
    """Validate an ``owner/repo`` (GitLab: ``group/sub/…/repo``) path slug."""
    cleaned = str(full_name).strip().strip("/")
    segments = cleaned.split("/")
    if len(segments) < 2 or any(not seg or seg.startswith("-") for seg in segments):
        raise ValueError(f"仓库要写 owner/repo 形式（GitLab 可带子组）：{full_name!r}")
    for seg in segments:
        if any(ch in seg for ch in "?#& \t\x00"):
            raise ValueError(f"仓库路径含非法字符：{full_name!r}")
    return cleaned


def _diff_counts(patch_text: str) -> tuple[int, int]:
    """Count added/deleted lines inside one unified-diff body."""
    additions = deletions = 0
    for line in patch_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def _patch_head(patch_text: str) -> str:
    """First lines of one unified-diff body, for evidence excerpts."""
    lines = (patch_text or "").splitlines()
    return "\n".join(lines[:PATCH_HEAD_LINES])


def flush_response_cache() -> None:
    """Drop every cached response (used by repo_forget after credential removal)."""
    _REST_CACHE.clear()


def _cache_get(key) -> object | None:
    cached = _REST_CACHE.get(key)
    if cached is not None and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    return None


def _cache_put(key, payload: object) -> None:
    if len(_REST_CACHE) >= CACHE_MAX_ENTRIES:
        oldest = min(_REST_CACHE, key=lambda item: _REST_CACHE[item][0])
        del _REST_CACHE[oldest]
    _REST_CACHE[key] = (time.monotonic(), payload)


class RestAdapter:
    """Shared HTTP machinery; subclasses supply endpoints and auth style."""

    platform = "rest"

    def __init__(self, provider: Provider):
        self.provider_name = provider.name
        self.base_url = provider.base_url.rstrip("/")
        self.token = provider.token or ""

    # -- platform hooks -------------------------------------------------
    def api_root(self) -> str:
        raise NotImplementedError

    def auth_headers(self) -> dict:
        raise NotImplementedError

    def repo_role(self, payload: dict) -> str:
        raise NotImplementedError

    def role_basis(self, payload: dict) -> str:
        raise NotImplementedError

    # -- HTTP -----------------------------------------------------------
    def _get(self, path: str, params: dict | None = None) -> object:
        key = (self.platform, self.base_url, path, tuple(sorted((k, str(v)) for k, v in (params or {}).items())))
        cached = _cache_get(key)
        if cached is not None:
            return cached
        url = self.api_root() + path
        if params:
            url += "?" + urllib.parse.urlencode({k: str(v) for k, v in params.items()})
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **self.auth_headers()})
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            head = ""
            try:
                head = err.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            detail = head or str(err.reason)
            raise RuntimeError(
                f"{self.platform} API 返回 HTTP {err.code}（{path}）：{detail}。"
                "请检查 token 是否有效、是否给了仓库只读权限，以及仓库路径是否写对（owner/repo）。"
            ) from err
        except RuntimeError:
            raise
        except Exception as cause:
            raise RuntimeError(NETWORK_REMEDY.format(base=self.base_url) + f"（{cause}）") from cause
        _cache_put(key, payload)
        return payload

    def _paged(self, path: str, params: dict | None, max_items: int) -> list:
        """Walk ``page``/``per_page`` until the cap or a short page — the one
        pagination scheme all three REST platforms share. A page-shaped
        non-list fails loud: an unrecognized payload is an endpoint change,
        not an empty result."""
        items: list = []
        for page in range(1, MAX_PAGES + 1):
            query = dict(params or {}, page=page, per_page=PER_PAGE)
            payload = self._get(path, query)
            if not isinstance(payload, list):
                raise RuntimeError(f"{self.platform} API（{path}）返回了非列表结构，可能接口变更或权限不足，已停止解析。")
            items.extend(item for item in payload if isinstance(item, dict))
            if len(items) >= max_items or len(payload) < PER_PAGE:
                break
        return items[:max_items]

    def _ensure_dict(self, payload: object, where: str) -> dict:
        """A single-object endpoint answered with something else — fail loud
        (fail_loud converts RuntimeError, but a bare AttributeError would be
        swallowed by the SDK with no cause text)."""
        if not isinstance(payload, dict):
            raise RuntimeError(f"{self.platform} API（{where}）返回了非映射结构，可能接口变更，已停止解析。")
        return payload

    # -- normalized operations ------------------------------------------
    def identity(self) -> dict:
        payload = self._ensure_dict(self._get("/user"), "/user")
        login = payload.get("login") or payload.get("username") or ""
        return {
            "platform": self.platform,
            "login": str(login),
            "name": payload.get("name") or "",
            "email": payload.get("email") or "",
            "id": payload.get("id"),
        }

    def list_repos(self, max_items: int) -> list[dict]:
        raise NotImplementedError

    def repo_info(self, full_name: str) -> dict:
        raise NotImplementedError

    def list_commits(self, full_name: str, max_items: int) -> list[dict]:
        raise NotImplementedError

    def get_commit(self, full_name: str, sha: str) -> dict:
        raise NotImplementedError

    def list_pulls(self, full_name: str, max_items: int) -> list[dict]:
        raise NotImplementedError

    def list_releases(self, full_name: str, max_items: int) -> list[dict]:
        raise NotImplementedError

    def read_file(self, full_name: str, path: str, ref: str | None) -> dict:
        raise NotImplementedError

    def contributors(self, full_name: str, max_items: int) -> list[dict]:
        raise NotImplementedError

    # -- shared payload shaping ------------------------------------------
    def _commit_files(self, file_entries: list) -> list[dict]:
        """Normalize one commit's file entries, keeping a small patch excerpt.

        The excerpt rides along because evidence reading needs to see what a
        commit actually did; the scan report prints only paths and counts.
        """
        files = []
        for entry in file_entries or []:
            if not isinstance(entry, dict):
                continue
            patch = entry.get("patch") or entry.get("diff") or ""
            additions = entry.get("additions")
            deletions = entry.get("deletions")
            if additions is None or deletions is None:
                # GitLab's diff entries carry no counts — derive them from the
                # unified-diff body instead of reporting zeros.
                derived_additions, derived_deletions = _diff_counts(patch)
                additions = derived_additions if additions is None else additions
                deletions = derived_deletions if deletions is None else deletions
            files.append(
                {
                    "path": entry.get("filename") or entry.get("new_path") or entry.get("old_path") or "",
                    "additions": int(additions or 0),
                    "deletions": int(deletions or 0),
                    "patch_head": _patch_head(patch),
                }
            )
        return files

    @staticmethod
    def _one_line(message: str) -> str:
        return (message or "").strip().splitlines()[0] if (message or "").strip() else ""


class GitHubAdapter(RestAdapter):
    """GitHub REST v3; the same protocol covers GitHub Enterprise Server."""

    platform = "github"

    def api_root(self) -> str:
        if self.base_url in ("https://github.com", "https://www.github.com"):
            return "https://api.github.com"
        return self.base_url + "/api/v3"  # GitHub Enterprise Server

    def auth_headers(self) -> dict:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def repo_role(self, payload: dict) -> str:
        return role_from_permissions_dict(payload)

    def role_basis(self, payload: dict) -> str:
        permissions = payload.get("permissions") or {}
        if permissions.get("admin"):
            return "permissions.admin=true"
        if permissions.get("maintain"):
            return "permissions.maintain=true"
        if permissions.get("push"):
            return "permissions.push=true"
        return "仅 permissions.pull（只读）"

    def _repo_summary(self, payload: dict) -> dict:
        return {
            "platform": self.platform,
            "full_name": payload.get("full_name") or "",
            "description": payload.get("description") or "",
            "default_branch": payload.get("default_branch") or "main",
            "web_url": payload.get("html_url") or "",
            "role": self.repo_role(payload),
            "role_basis": self.role_basis(payload),
        }

    def list_repos(self, max_items: int) -> list[dict]:
        payloads = self._paged(
            "/user/repos",
            {"affiliation": "owner,collaborator,organization_member", "sort": "pushed"},
            max_items,
        )
        return [self._repo_summary(payload) for payload in payloads]

    def repo_info(self, full_name: str) -> dict:
        return self._repo_summary(self._ensure_dict(self._get(f"/repos/{_safe_repo_path(full_name)}"), f"/repos/{full_name}"))

    def list_commits(self, full_name: str, max_items: int) -> list[dict]:
        payloads = self._paged(f"/repos/{_safe_repo_path(full_name)}/commits", {}, max_items)
        return [self._commit_summary(payload) for payload in payloads]

    @staticmethod
    def _commit_summary(payload: dict) -> dict:
        commit = payload.get("commit") or {}
        author = commit.get("author") or {}
        return {
            "sha": payload.get("sha") or "",
            "author_name": author.get("name") or "",
            "author_email": author.get("email") or "",
            "author_login": (payload.get("author") or {}).get("login"),
            "date": author.get("date") or "",
            "message": RestAdapter._one_line(commit.get("message")),
            "web_url": payload.get("html_url") or "",
            "files": None,
        }

    def get_commit(self, full_name: str, sha: str) -> dict:
        payload = self._ensure_dict(self._get(f"/repos/{_safe_repo_path(full_name)}/commits/{_safe_sha(sha)}"), f"commit {sha}")
        summary = self._commit_summary(payload)
        summary["files"] = self._commit_files(payload.get("files"))
        return summary

    def list_pulls(self, full_name: str, max_items: int) -> list[dict]:
        payloads = self._paged(
            f"/repos/{_safe_repo_path(full_name)}/pulls",
            {"state": "closed", "sort": "updated", "direction": "desc"},
            max_items,
        )
        return [
            {
                "number": payload.get("number"),
                "title": payload.get("title") or "",
                "author": (payload.get("user") or {}).get("login") or "",
                "merged": payload.get("merged_at") is not None,
                "date": payload.get("merged_at") or payload.get("closed_at") or "",
                "web_url": payload.get("html_url") or "",
            }
            for payload in payloads
        ]

    def list_releases(self, full_name: str, max_items: int) -> list[dict]:
        payloads = self._paged(f"/repos/{_safe_repo_path(full_name)}/releases", {}, max_items)
        return [
            {
                "tag": payload.get("tag_name") or "",
                "name": payload.get("name") or payload.get("tag_name") or "",
                "date": payload.get("published_at") or "",
                "notes_head": _patch_head(payload.get("body") or ""),
            }
            for payload in payloads
        ]

    def read_file(self, full_name: str, path: str, ref: str | None) -> dict:
        quoted = urllib.parse.quote(str(path).strip().lstrip("/"), safe="/")
        params = {"ref": ref} if ref else None
        payload = self._ensure_dict(self._get(f"/repos/{_safe_repo_path(full_name)}/contents/{quoted}", params), f"contents {path}")
        size = int(payload.get("size") or 0)
        if size > MAX_FILE_BYTES:
            raise RuntimeError(
                f"文件过大（{size} 字节，上限 {MAX_FILE_BYTES}）：{path}。改读局部文件，或用 local 平台接入本地仓库。"
            )
        content = base64.b64decode(payload.get("content") or b"").decode("utf-8", "replace")
        return {"path": payload.get("path") or path, "size": size, "content": content}

    def contributors(self, full_name: str, max_items: int) -> list[dict]:
        payloads = self._paged(f"/repos/{_safe_repo_path(full_name)}/contributors", {}, max_items)
        return [
            {"name": payload.get("login") or "?", "count": int(payload.get("contributions") or 0)}
            for payload in payloads
        ]


class GitLabAdapter(RestAdapter):
    """GitLab REST v4; one protocol for gitlab.com and self-hosted instances."""

    platform = "gitlab"

    def api_root(self) -> str:
        return self.base_url + "/api/v4"

    def auth_headers(self) -> dict:
        headers = {}
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token
        return headers

    def repo_role(self, payload: dict) -> str:
        permissions = payload.get("permissions") or {}
        levels = []
        if isinstance(permissions, dict):
            for part in (permissions.get("project_access"), permissions.get("group_access")):
                if isinstance(part, dict) and isinstance(part.get("access_level"), int):
                    levels.append(part["access_level"])
        return gitlab_level_to_role(max(levels) if levels else 0)

    def role_basis(self, payload: dict) -> str:
        permissions = payload.get("permissions") or {}
        levels = []
        if isinstance(permissions, dict):
            for part in (permissions.get("project_access"), permissions.get("group_access")):
                if isinstance(part, dict) and isinstance(part.get("access_level"), int):
                    levels.append(part["access_level"])
        if levels:
            return f"access_level={max(levels)}"
        return "非成员可见（按 10/Guest 计）"

    def _repo_summary(self, payload: dict) -> dict:
        return {
            "platform": self.platform,
            "full_name": payload.get("path_with_namespace") or "",
            "description": payload.get("description") or "",
            "default_branch": payload.get("default_branch") or "main",
            "web_url": payload.get("web_url") or "",
            "role": self.repo_role(payload),
            "role_basis": self.role_basis(payload),
        }

    @staticmethod
    def _project_id(full_name: str) -> str:
        return urllib.parse.quote(_safe_repo_path(full_name), safe="")

    def list_repos(self, max_items: int) -> list[dict]:
        payloads = self._paged(
            "/projects",
            {"membership": "true", "order_by": "last_activity_at"},
            max_items,
        )
        return [self._repo_summary(payload) for payload in payloads]

    def repo_info(self, full_name: str) -> dict:
        return self._repo_summary(self._ensure_dict(self._get(f"/projects/{self._project_id(full_name)}"), f"/projects/{full_name}"))

    def list_commits(self, full_name: str, max_items: int) -> list[dict]:
        payloads = self._paged(f"/projects/{self._project_id(full_name)}/repository/commits", {}, max_items)
        summaries = []
        for payload in payloads:
            summaries.append(
                {
                    "sha": payload.get("id") or "",
                    "author_name": payload.get("author_name") or "",
                    "author_email": payload.get("author_email") or "",
                    "author_login": None,
                    "date": payload.get("committed_date") or payload.get("created_at") or "",
                    "message": RestAdapter._one_line(payload.get("title")),
                    "web_url": payload.get("web_url") or "",
                    "files": None,
                }
            )
        return summaries

    def get_commit(self, full_name: str, sha: str) -> dict:
        project = self._project_id(full_name)
        meta = self._ensure_dict(self._get(f"/projects/{project}/repository/commits/{_safe_sha(sha)}"), f"commit {sha}")
        diffs = self._get(f"/projects/{project}/repository/commits/{_safe_sha(sha)}/diff")
        if not isinstance(diffs, list):
            raise RuntimeError(f"GitLab diff 接口返回了非列表结构（{full_name}@{sha}），已停止解析。")
        files = self._commit_files(diffs)
        return {
            "sha": meta.get("id") or sha,
            "author_name": meta.get("author_name") or "",
            "author_email": meta.get("author_email") or "",
            "author_login": None,
            "date": meta.get("committed_date") or meta.get("created_at") or "",
            "message": RestAdapter._one_line(meta.get("title")),
            "web_url": meta.get("web_url") or "",
            "files": files,
        }

    def list_pulls(self, full_name: str, max_items: int) -> list[dict]:
        payloads = self._paged(
            f"/projects/{self._project_id(full_name)}/merge_requests",
            {"state": "merged"},
            max_items,
        )
        return [
            {
                "number": payload.get("iid"),
                "title": payload.get("title") or "",
                "author": (payload.get("author") or {}).get("username") or "",
                "merged": payload.get("state") == "merged",
                "date": payload.get("merged_at") or payload.get("updated_at") or "",
                "web_url": payload.get("web_url") or "",
            }
            for payload in payloads
        ]

    def list_releases(self, full_name: str, max_items: int) -> list[dict]:
        payloads = self._paged(f"/projects/{self._project_id(full_name)}/releases", {}, max_items)
        return [
            {
                "tag": payload.get("tag_name") or "",
                "name": payload.get("name") or payload.get("tag_name") or "",
                "date": payload.get("released_at") or payload.get("created_at") or "",
                "notes_head": _patch_head(payload.get("description") or ""),
            }
            for payload in payloads
        ]

    def read_file(self, full_name: str, path: str, ref: str | None) -> dict:
        quoted_path = urllib.parse.quote(str(path).strip().lstrip("/"), safe="")
        params = {"ref": ref} if ref else None
        payload = self._ensure_dict(self._get(f"/projects/{self._project_id(full_name)}/repository/files/{quoted_path}", params), f"files {path}")
        size = int(payload.get("size") or 0)
        if size > MAX_FILE_BYTES:
            raise RuntimeError(
                f"文件过大（{size} 字节，上限 {MAX_FILE_BYTES}）：{path}。改读局部文件，或用 local 平台接入本地仓库。"
            )
        content = base64.b64decode(payload.get("content") or b"").decode("utf-8", "replace")
        return {"path": payload.get("file_path") or path, "size": size, "content": content}

    def contributors(self, full_name: str, max_items: int) -> list[dict]:
        payloads = self._paged(f"/projects/{self._project_id(full_name)}/repository/contributors", {}, max_items)
        return [
            {"name": payload.get("name") or payload.get("email") or "?", "count": int(payload.get("commits") or 0)}
            for payload in payloads
        ]


class GiteeAdapter(RestAdapter):
    """Gitee API v5, GitHub-flavored; token rides the Bearer header (never a
    URL query, so it cannot leak through error text)."""

    platform = "gitee"

    def api_root(self) -> str:
        return self.base_url + "/api/v5"

    def auth_headers(self) -> dict:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def repo_role(self, payload: dict) -> str:
        return role_from_permissions_dict(payload)

    def role_basis(self, payload: dict) -> str:
        permissions = payload.get("permissions") or {}
        if permissions.get("admin"):
            return "permissions.admin=true"
        if permissions.get("push"):
            return "permissions.push=true"
        return "仅 permissions.pull（只读）"

    def _repo_summary(self, payload: dict) -> dict:
        return {
            "platform": self.platform,
            "full_name": payload.get("full_name") or payload.get("path") or "",
            "description": payload.get("description") or "",
            "default_branch": payload.get("default_branch") or "master",
            "web_url": payload.get("html_url") or "",
            "role": self.repo_role(payload),
            "role_basis": self.role_basis(payload),
        }

    def list_repos(self, max_items: int) -> list[dict]:
        payloads = self._paged("/user/repos", {"sort": "pushed"}, max_items)
        return [self._repo_summary(payload) for payload in payloads]

    def repo_info(self, full_name: str) -> dict:
        return self._repo_summary(self._ensure_dict(self._get(f"/repos/{_safe_repo_path(full_name)}"), f"/repos/{full_name}"))

    def list_commits(self, full_name: str, max_items: int) -> list[dict]:
        payloads = self._paged(f"/repos/{_safe_repo_path(full_name)}/commits", {}, max_items)
        return [self._commit_summary(payload) for payload in payloads]

    @staticmethod
    def _commit_summary(payload: dict) -> dict:
        commit = payload.get("commit") or {}
        author = commit.get("author") or {}
        return {
            "sha": payload.get("sha") or "",
            "author_name": author.get("name") or "",
            "author_email": author.get("email") or "",
            "author_login": (payload.get("author") or {}).get("login"),
            "date": author.get("date") or "",
            "message": RestAdapter._one_line(commit.get("message")),
            "web_url": payload.get("html_url") or "",
            "files": None,
        }

    def get_commit(self, full_name: str, sha: str) -> dict:
        payload = self._ensure_dict(self._get(f"/repos/{_safe_repo_path(full_name)}/commits/{_safe_sha(sha)}"), f"commit {sha}")
        summary = self._commit_summary(payload)
        summary["files"] = self._commit_files(payload.get("files"))
        return summary

    def list_pulls(self, full_name: str, max_items: int) -> list[dict]:
        payloads = self._paged(
            f"/repos/{_safe_repo_path(full_name)}/pulls",
            {"state": "all", "sort": "updated", "direction": "desc"},
            max_items,
        )
        return [
            {
                "number": payload.get("number"),
                "title": payload.get("title") or "",
                "author": (payload.get("user") or {}).get("login") or "",
                "merged": payload.get("state") == "merged",
                "date": payload.get("merged_at") or payload.get("updated_at") or "",
                "web_url": payload.get("html_url") or "",
            }
            for payload in payloads
        ]

    def list_releases(self, full_name: str, max_items: int) -> list[dict]:
        payloads = self._paged(
            f"/repos/{_safe_repo_path(full_name)}/releases",
            {"direction": "desc"},
            max_items,
        )
        return [
            {
                "tag": payload.get("tag_name") or "",
                "name": payload.get("name") or payload.get("tag_name") or "",
                "date": payload.get("created_at") or "",
                "notes_head": _patch_head(payload.get("body") or ""),
            }
            for payload in payloads
        ]

    def read_file(self, full_name: str, path: str, ref: str | None) -> dict:
        quoted = urllib.parse.quote(str(path).strip().lstrip("/"), safe="/")
        params = {"ref": ref} if ref else None
        payload = self._ensure_dict(self._get(f"/repos/{_safe_repo_path(full_name)}/contents/{quoted}", params), f"contents {path}")
        size = int(payload.get("size") or 0)
        if size > MAX_FILE_BYTES:
            raise RuntimeError(
                f"文件过大（{size} 字节，上限 {MAX_FILE_BYTES}）：{path}。改读局部文件，或用 local 平台接入本地仓库。"
            )
        content = base64.b64decode(payload.get("content") or b"").decode("utf-8", "replace")
        return {"path": payload.get("path") or path, "size": size, "content": content}

    def contributors(self, full_name: str, max_items: int) -> list[dict]:
        payloads = self._paged(f"/repos/{_safe_repo_path(full_name)}/contributors", {}, max_items)
        return [
            {
                "name": payload.get("name") or payload.get("login") or payload.get("email") or "?",
                "count": int(payload.get("contributions") or payload.get("count") or 0),
            }
            for payload in payloads
        ]


class LocalGitAdapter:
    """A plain local clone, for private hosts without any HTTP API.

    The role cannot come from a platform — it is declared in the config and
    the declaration is the user's responsibility (the adapter only verifies
    the directory is a readable git repository). History reads through one
    fixed-argument ``git log --numstat`` per scan: every commit arrives with
    its touched files in a single subprocess, no shell, no option-style refs.
    Pull requests and release notes do not exist in bare git — the adapter
    says so instead of pretending.
    """

    platform = "local"

    def __init__(self, provider: Provider):
        self.provider_name = provider.name
        self.path = provider.base_url
        self.role = validate_declared_role(provider.declared_role)

    def _git(self, *args: str, timeout_seconds: int = 60) -> str:
        argv = ["git", "-C", self.path, *args]
        try:
            completed = subprocess.run(
                argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_seconds
            )
        except subprocess.TimeoutExpired as cause:
            raise RuntimeError(f"本地 git 命令超时（{args[0]}）：请确认目录在可用磁盘上，或减小扫描上限。") from cause
        except OSError as cause:
            raise RuntimeError(f"无法运行 git（请确认已安装并加入 PATH）：{cause}") from cause
        if completed.returncode != 0:
            head = (completed.stderr or "").strip().splitlines()
            detail = head[0] if head else f"退出码 {completed.returncode}"
            raise RuntimeError(f"本地 git 命令失败（{args[0]}）：{detail}。请确认 base_url 指向可读的 git 仓库目录。")
        return completed.stdout or ""

    def _check(self) -> None:
        self._git("rev-parse", "--git-dir")

    def identity(self) -> dict:
        name = ""
        email = ""
        if self._check_ok():
            # Either config may be unset — a missing identity is not an error,
            # it only weakens the participant's own-commit matching.
            for key, store in (("user.name", "name"), ("user.email", "email")):
                try:
                    value = self._git("config", key).strip()
                except RuntimeError:
                    value = ""
                if store == "name":
                    name = value
                else:
                    email = value
        return {"platform": self.platform, "login": email or name, "name": name, "email": email, "id": None}

    def _check_ok(self) -> bool:
        try:
            self._check()
            return True
        except RuntimeError:
            return False

    def list_repos(self, max_items: int) -> list[dict]:
        return [self.repo_info(Path(self.path).name or self.path)]

    def repo_info(self, full_name: str) -> dict:
        self._check()
        branch = self._git("symbolic-ref", "--short", "HEAD").strip()
        return {
            "platform": self.platform,
            "full_name": Path(self.path).name or self.path,
            "description": "本地仓库（角色为 repo-mining.yaml 声明，工具仅校验可读性）",
            "default_branch": branch or "HEAD",
            "web_url": self.path,
            "role": self.role,
            "role_basis": f"repo-mining.yaml 声明 declared_role={self.role}",
        }

    _LOG_FORMAT = "%x1e%H%x1f%an%x1f%ae%x1f%ad%x1f%s"

    def _parse_log(self, text: str) -> list[dict]:
        """Parse the ``git log --numstat`` output framed with a record-start
        separator: each chunk is its commit's header line followed by the
        commit's own ``adds<TAB>dels<TAB>path`` numstat lines."""
        commits = []
        for record in text.split("\x1e"):
            if not record.strip():
                continue
            lines = [line for line in record.splitlines() if line.strip()]
            if not lines:
                continue
            fields = lines[0].split("\x1f")
            while len(fields) < 5:
                fields.append("")
            files = []
            for line in lines[1:]:
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                adds, dels, file_path = parts[0], parts[1], "\t".join(parts[2:])
                files.append(
                    {
                        "path": file_path,
                        "additions": 0 if adds == "-" else int(adds),
                        "deletions": 0 if dels == "-" else int(dels),
                        "patch_head": "",
                    }
                )
            commits.append(
                {
                    "sha": fields[0],
                    "author_name": fields[1],
                    "author_email": fields[2],
                    "author_login": None,
                    "date": fields[3],
                    "message": fields[4],
                    "web_url": "",
                    "files": files,
                }
            )
        return commits

    def list_commits(self, full_name: str, max_items: int) -> list[dict]:
        self._check()
        text = self._git("log", f"--max-count={max_items}", "--date=iso-strict", f"--format={self._LOG_FORMAT}", "--numstat")
        return self._parse_log(text)

    def get_commit(self, full_name: str, sha: str) -> dict:
        self._check()
        text = self._git(
            "show", "--no-renames", "--date=iso-strict", f"--format={self._LOG_FORMAT}", "--numstat", _safe_plain(sha)
        )
        commits = self._parse_log(text)
        if not commits:
            raise RuntimeError(f"本地仓库中找不到提交：{sha}")
        return commits[0]

    def list_pulls(self, full_name: str, max_items: int) -> list[dict]:
        return []  # bare git has no pull requests; callers render the absence

    def list_releases(self, full_name: str, max_items: int) -> list[dict]:
        self._check()
        # for-each-ref does not process %x escapes: one ref per line, split on
        # the last space — tag names hold no spaces and iso-strict dates hold
        # none either.
        text = self._git(
            "for-each-ref", "refs/tags", f"--count={max_items}", "--sort=-creatordate",
            "--format=%(refname:short) %(creatordate:iso-strict)",
        )
        releases = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            tag, _, date = line.rpartition(" ")
            releases.append({"tag": tag, "name": tag, "date": date, "notes_head": ""})
        return releases

    def read_file(self, full_name: str, path: str, ref: str | None) -> dict:
        self._check()
        content = self._git("show", f"{_safe_plain(ref or 'HEAD')}:{_safe_plain(path)}")
        if len(content) > MAX_FILE_BYTES:
            content = content[:MAX_FILE_BYTES]
            return {"path": path, "size": MAX_FILE_BYTES, "content": content + "\n…（已截断到 200000 字节）"}
        return {"path": path, "size": len(content), "content": content}

    def contributors(self, full_name: str, max_items: int) -> list[dict]:
        self._check()
        names = Counter(line.strip() for line in self._git("log", "--format=%an").splitlines() if line.strip())
        return [{"name": name, "count": count} for name, count in names.most_common(max_items)]


#: The four adapters by platform name.
ADAPTER_CLASSES = {
    "github": GitHubAdapter,
    "gitlab": GitLabAdapter,
    "gitee": GiteeAdapter,
    "local": LocalGitAdapter,
}


def build_adapter(provider: Provider):
    """Instantiate the right adapter for one provider.

    Raises:
        ValueError: the provider's platform has no adapter.
    """
    adapter_class = ADAPTER_CLASSES.get(provider.platform)
    if adapter_class is None:
        raise ValueError(f"platform「{provider.platform}」没有适配器（可选：{'/'.join(ADAPTER_CLASSES)}）")
    return adapter_class(provider)
