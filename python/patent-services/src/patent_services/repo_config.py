"""Repository-mining providers from ``$DSH_HOME/repo-mining.yaml``.

Git-platform connections for the mining tools: one provider names one
platform (github / gitlab / gitee / local) with its base URL and token. The
file is structured YAML — a providers list, not the flat scalar keys of
``patent-services.yaml`` — because hosts and credentials differ per provider,
and the mining tools live only in the Python service, so the TS side never
reads it and the mirrored-parser rule does not apply.

Tokens resolve through the environment first: ``DSH_PATENT_REPO_TOKEN_<NAME>``
(the provider name uppercased, non-alphanumeric characters folded to ``_``)
wins over the file value, keeping tokens out of files that sync and get
committed by accident. A token is a read-only secret: adapters send it as a
header, error text carries the request path but never the headers or URL, and
:func:`remove_token_from_file` strips the file value on ``repo_forget`` —
the true revocation still happens platform-side, and the tool says so.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import config_path

#: The mining config's name inside $DSH_HOME (default ~/.dsh).
REPO_CONFIG_NAME = "repo-mining.yaml"

#: Supported platforms; ``local`` reads an existing clone with git subprocess.
PLATFORMS = ("github", "gitlab", "gitee", "local")

#: Public hosts used when a provider omits base_url (``local`` has none —
#: its base_url IS the clone path and must be given).
DEFAULT_BASE_URLS = {
    "github": "https://github.com",
    "gitlab": "https://gitlab.com",
    "gitee": "https://gitee.com",
}

#: The env-var prefix one provider's token may override: <NAME> is the
#: provider name uppercased with non-alphanumeric characters folded to ``_``.
TOKEN_ENV_PREFIX = "DSH_PATENT_REPO_TOKEN_"


@dataclass
class Provider:
    """One normalized provider row from the config file plus its env token."""

    name: str
    platform: str
    base_url: str
    token: str | None
    declared_role: str | None  # local only: admin | participant | observer


def repo_config_file() -> Path:
    """The mining config file's full path for this machine."""
    return config_path() / REPO_CONFIG_NAME


def load_provider_config() -> dict:
    """Read the mining config; a broken file fails loud, unlike flat prefs.

    The mining config gates tools that are opt-in, so a silent ``{}`` here
    would misreport a typo'd file as "no providers configured"; the error
    names the file and the YAML fault instead.

    Raises:
        RuntimeError: the file exists but is not valid YAML (or not a mapping).
    """
    path = repo_config_file()
    if not path.is_file():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RuntimeError(f"{path} 不是有效的 YAML，无法接入仓库：{exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise RuntimeError(f"{path} 的顶层必须是键值映射（providers:、default_provider: 等）")
    return loaded


def _providers_from(config: dict) -> list[Provider]:
    """Normalize the config's providers list into :class:`Provider` rows.

    Raises:
        ValueError: a row is missing name/platform, names an unknown platform,
            or duplicates a name.
    """
    rows = config.get("providers")
    if not isinstance(rows, list) or not rows:
        raise ValueError(
            f"{repo_config_file()} 没有可用的 providers 列表。请在文件里配置至少一个 provider"
            "（platform: github|gitlab|gitee|local，加 base_url 与 token）后重试。"
        )
    providers: list[Provider] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("providers 里每一项都必须是映射（name:/platform:/…）")
        name = str(row.get("name") or "").strip()
        platform = str(row.get("platform") or "").strip().lower()
        if not name or not platform:
            raise ValueError("provider 缺少 name 或 platform 字段")
        if platform not in PLATFORMS:
            raise ValueError(f"provider「{name}」的 platform 不支持：{platform}（可选 {'/'.join(PLATFORMS)}）")
        if name in seen:
            raise ValueError(f"provider 名字重复：{name}")
        seen.add(name)
        base_url = str(row.get("base_url") or "").strip() or DEFAULT_BASE_URLS.get(platform, "")
        if platform == "local" and not base_url:
            raise ValueError(f"provider「{name}」是 local 平台，base_url 必须填本地 git 仓库目录路径")
        token = row.get("token")
        providers.append(
            Provider(
                name=name,
                platform=platform,
                base_url=base_url,
                token=str(token).strip() if isinstance(token, str) and token.strip() else None,
                declared_role=row.get("declared_role"),
            )
        )
    return providers


def resolve_provider(name: str | None, config: dict | None = None) -> Provider:
    """Pick one provider by name, or the config's default / single one.

    Args:
        name: the provider's name; None means default_provider or the only row.
        config: a preloaded config (loads the file when omitted).

    Returns:
        The matching provider.

    Raises:
        ValueError: the name matches no provider, or no default is resolvable.
    """
    config = load_provider_config() if config is None else config
    providers = _providers_from(config)
    if name:
        for provider in providers:
            if provider.name == name:
                return provider
        known = "、".join(p.name for p in providers)
        raise ValueError(f"没有名为「{name}」的 provider；已配置的有：{known}")
    default = str(config.get("default_provider") or "").strip()
    if default:
        for provider in providers:
            if provider.name == default:
                return provider
        known = "、".join(p.name for p in providers)
        raise ValueError(f"default_provider「{default}」不在 providers 列表里；已配置的有：{known}")
    if len(providers) == 1:
        return providers[0]
    known = "、".join(p.name for p in providers)
    raise ValueError(f"配置里有多个 provider 且未指定 default_provider，请用 provider 参数指明（可选：{known}）")


def token_env_name(provider_name: str) -> str:
    """The env-var name that overrides one provider's file token."""
    suffix = re.sub(r"[^A-Za-z0-9]", "_", provider_name).upper()
    return TOKEN_ENV_PREFIX + suffix


def resolve_token(provider: Provider) -> str | None:
    """Resolve one provider's token: environment first, then the file value."""
    ambient = os.environ.get(token_env_name(provider.name))
    if ambient:
        return ambient
    return provider.token


def redact_token(token: str | None) -> str:
    """Mask a token for any user-facing text: only its last 4 characters show."""
    if not token:
        return "（未配置）"
    if len(token) <= 8:
        return "****"
    return "****" + token[-4:]


def remove_token_from_file(provider_name: str) -> tuple[bool, Path]:
    """Strip one provider's ``token:`` line from the config file in place.

    Line surgery, not a YAML round-trip: the file is for people and its
    comments must survive. Only the line whose key is ``token`` inside the
    provider's own block (from its ``- name:`` until the next ``- name:`` or
    a top-level key) is removed.

    Returns:
        Whether a token line was removed, and the file's path (present even
        when nothing was removed, for the caller's report).

    Raises:
        RuntimeError: the config file is broken YAML (a repair beats an edit).
    """
    path = repo_config_file()
    if not path.is_file():
        return False, path
    load_provider_config()  # broken YAML must not be "repaired" by deletion
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    block_start = -1
    block_end = len(lines)
    token_line = -1
    for index, line in enumerate(lines):
        match = re.match(r"^\s*-?\s*name:\s*(.+?)\s*$", line)
        if match and match.group(1).strip("'\"") == provider_name:
            block_start = index
            continue
        if block_start >= 0:
            if re.match(r"^\s*-?\s*name:", line) or re.match(r"^[A-Za-z_]", line):
                block_end = index
                break
            if re.match(r"^\s*token:", line):
                token_line = index
    removed = False
    if block_start >= 0 and token_line >= 0:
        del lines[token_line]
        removed = True
        path.write_text("".join(lines), encoding="utf-8")
    return removed, path


def scan_limit(config: dict | None = None) -> int | None:
    """The config's global scan cap (``limits.max_commits_per_scan``), if any.

    The role matrix always applies on top: the effective cap is whichever is
    smaller, so a permissive file cannot widen a role's budget.
    """
    config = load_provider_config() if config is None else config
    limits = config.get("limits")
    if isinstance(limits, dict):
        value = limits.get("max_commits_per_scan")
        if isinstance(value, int) and value > 0:
            return value
    return None
