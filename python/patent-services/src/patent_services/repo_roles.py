"""Mining roles: platform permissions mapped to a three-level scheme.

The connected user is one person; each repository gets a role from what the
token can actually do there — admin / participant / observer. The role
decides how deep a scan runs and what a mining result may claim, never which
repositories are visible (that is the token's own reach). Limits live in one
matrix here so the scan tools cannot be talked into exceeding the role's
budget, and the attribution discipline rides along with every scan result:
an inventor proposal may only come from real evidence authors, and an
administrator's badge buys no exception.
"""

from __future__ import annotations

ADMIN = "admin"
PARTICIPANT = "participant"
OBSERVER = "observer"

#: The three mining roles, lowest privilege last.
ROLES = (ADMIN, PARTICIPANT, OBSERVER)

#: GitLab access levels (10 Guest … 50 Owner); ≥40 counts as maintainer.
GITLAB_MAINTAINER_LEVEL = 40
GITLAB_DEVELOPER_LEVEL = 30

#: Per-role scan budgets: commits pulled per scan, commits deep-read for
#: hotspots (each is one extra request), repositories per access listing.
ROLE_LIMITS = {
    ADMIN: {"max_commits": 400, "detail_commits": 30, "max_repos_listed": 100},
    PARTICIPANT: {"max_commits": 200, "detail_commits": 20, "max_repos_listed": 100},
    OBSERVER: {"max_commits": 100, "detail_commits": 10, "max_repos_listed": 50},
}

#: Floors and fallbacks.
MIN_COMMIT_CAP = 1
DEFAULT_SCAN_COMMITS = 100


def is_valid_role(role: str) -> bool:
    """Whether the string names one of the three mining roles."""
    return role in ROLES


def validate_declared_role(value: object) -> str:
    """Validate a config-declared role (the local platform's only source).

    Raises:
        ValueError: the value is not one of the three roles.
    """
    role = str(value or "").strip().lower()
    if not is_valid_role(role):
        raise ValueError(
            f"declared_role 只能是 {'/'.join(ROLES)}，收到：{value!r}"
            "（本地仓库没有平台 API，角色由配置声明、由你负责如实声明）"
        )
    return role


def role_from_permissions_dict(payload: dict) -> str:
    """Map a GitHub/Gitee repo payload's ``permissions`` object to a role.

    Missing or empty permissions fall to observer — an unknown grant is
    never read upward.
    """
    permissions = payload.get("permissions") or {}
    if not isinstance(permissions, dict):
        return OBSERVER
    if permissions.get("admin") or permissions.get("maintain"):
        return ADMIN
    if permissions.get("push"):
        return PARTICIPANT
    return OBSERVER


def gitlab_level_to_role(level: int) -> str:
    """Map a numeric GitLab access level (0-50) to a role."""
    if level >= GITLAB_MAINTAINER_LEVEL:
        return ADMIN
    if level >= GITLAB_DEVELOPER_LEVEL:
        return PARTICIPANT
    return OBSERVER


def role_from_gitlab_project(payload: dict) -> str:
    """Map a GitLab project payload's permissions block to a role.

    Project access and group access both report an access_level; the higher
    one wins. Both absent (visible but not a member) reads as observer.
    """
    permissions = payload.get("permissions") or {}
    levels = []
    if isinstance(permissions, dict):
        for part in (permissions.get("project_access"), permissions.get("group_access")):
            if isinstance(part, dict) and isinstance(part.get("access_level"), int):
                levels.append(part["access_level"])
    return gitlab_level_to_role(max(levels) if levels else 0)


def describe_role(role: str, basis: str) -> str:
    """One Chinese line naming the role and the permission it maps from."""
    names = {ADMIN: "管理员", PARTICIPANT: "参与者", OBSERVER: "观察者"}
    return f"角色：{names.get(role, role)}（映射依据：{basis}）"


def role_discipline_lines(role: str) -> list[str]:
    """The attribution discipline a scan result must carry, by role.

    These lines bind what the model may produce from the facts: the observer
    stops at leads, the participant flags other people's work, and even the
    administrator's candidates cite evidence authors — the badge does not
    make them an inventor.
    """
    if role == ADMIN:
        return [
            "产出纪律（管理员）：可对仓库内任何成员的贡献提炼候选；候选可附成员贡献矩阵。",
            "发明人候选仍只能来自证据 commit 的作者——管理员身份不是发明贡献，不能自封。",
        ]
    if role == PARTICIPANT:
        return [
            "产出纪律（参与者）：本人 commit/PR 是核心语料，本人候选可直接推进建档。",
            "他人主导的提交只能列为「他人主导」线索，须经实际作者确认后才能建档。",
            "发明人候选以证据 commit 的作者为准；你无法替他人主张发明人。",
        ]
    return [
        "产出纪律（观察者）：只有只读事实与线索级产出，不建正式候选——归属无法核实。",
        "发现可专利点时，产出「线索：谁在哪个提交里做了什么」，提示用户联系实际作者确认。",
    ]


def effective_commit_cap(role: str, config_cap: int | None = None, requested: int | None = None) -> tuple[int, str | None]:
    """Resolve the scan's commit cap: role budget, config limit, and request
    all intersect, the smallest wins.

    Returns:
        The effective cap and an explanatory note when a higher value was
        clamped down (so the report can state the clamp honestly).
    """
    role_cap = ROLE_LIMITS.get(role, ROLE_LIMITS[OBSERVER])["max_commits"]
    cap = role_cap
    for source, value in (("配置上限", config_cap), ("请求值", requested)):
        if isinstance(value, int) and value > 0 and value < cap:
            cap = value
            if value < role_cap:
                return max(cap, MIN_COMMIT_CAP), f"{source} {value} 低于角色上限 {role_cap}，按 {source} 执行"
    if requested is not None and isinstance(requested, int) and requested > role_cap:
        return cap, f"请求值 {requested} 超出角色「{role}」上限 {role_cap}，已按角色上限执行"
    return max(cap, MIN_COMMIT_CAP), None


def detail_cap(role: str) -> int:
    """How many recent commits get deep-read (per-commit file details) for hotspots."""
    return ROLE_LIMITS.get(role, ROLE_LIMITS[OBSERVER])["detail_commits"]
