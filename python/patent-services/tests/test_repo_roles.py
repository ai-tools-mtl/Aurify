"""repo_roles: permission mapping, role budgets, and the attribution discipline."""

from __future__ import annotations

import pytest

from patent_services.repo_roles import (
    ADMIN,
    OBSERVER,
    PARTICIPANT,
    detail_cap,
    effective_commit_cap,
    gitlab_level_to_role,
    role_discipline_lines,
    role_from_gitlab_project,
    role_from_permissions_dict,
    validate_declared_role,
)


@pytest.mark.parametrize(
    "permissions,expected",
    [
        ({"admin": True, "maintain": True, "push": True, "pull": True}, ADMIN),
        ({"maintain": True, "push": False, "pull": True}, ADMIN),
        ({"admin": False, "push": True, "pull": True}, PARTICIPANT),
        ({"pull": True}, OBSERVER),
        ({}, OBSERVER),
    ],
)
def test_github_gitee_permissions_map_to_roles(permissions, expected):
    assert role_from_permissions_dict({"permissions": permissions}) == expected


def test_missing_permissions_object_reads_observer():
    assert role_from_permissions_dict({}) == OBSERVER


@pytest.mark.parametrize(
    "level,expected",
    [
        (50, ADMIN),
        (40, ADMIN),
        (30, PARTICIPANT),
        (20, OBSERVER),
        (10, OBSERVER),
        (0, OBSERVER),
    ],
)
def test_gitlab_levels_map_to_roles(level, expected):
    assert gitlab_level_to_role(level) == expected


def test_gitlab_project_takes_the_higher_of_project_and_group_access():
    project = {"permissions": {"project_access": {"access_level": 30}, "group_access": {"access_level": 40}}}
    assert role_from_gitlab_project(project) == ADMIN
    project = {"permissions": {"project_access": None, "group_access": {"access_level": 30}}}
    assert role_from_gitlab_project(project) == PARTICIPANT
    assert role_from_gitlab_project({"permissions": {}}) == OBSERVER
    assert role_from_gitlab_project({}) == OBSERVER


def test_declared_role_is_validated_strictly():
    assert validate_declared_role("Admin") == ADMIN
    with pytest.raises(ValueError, match="declared_role"):
        validate_declared_role("owner")


def test_effective_cap_intersects_role_config_and_request():
    cap, note = effective_commit_cap(OBSERVER, requested=500)
    assert cap == 100
    assert note and "超出" in note
    cap, note = effective_commit_cap(ADMIN, config_cap=150)
    assert cap == 150
    assert note and "150" in note
    cap, note = effective_commit_cap(PARTICIPANT, config_cap=500, requested=80)
    assert cap == 80
    cap, note = effective_commit_cap(ADMIN)
    assert cap == 400
    assert note is None


def test_detail_cap_descends_with_privilege():
    assert detail_cap(ADMIN) > detail_cap(PARTICIPANT) > detail_cap(OBSERVER)


def test_discipline_lines_carry_the_attribution_rules():
    assert any("发明人" in line and "不能自封" in line for line in role_discipline_lines(ADMIN))
    assert any("他人主导" in line for line in role_discipline_lines(PARTICIPANT))
    assert any("线索" in line for line in role_discipline_lines(OBSERVER))
