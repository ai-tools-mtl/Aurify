"""repo_adapters: normalized payloads over stubbed REST endpoints and a real local clone.

The stub HTTP server answers route-table JSON on an ephemeral port, so all
three REST platforms run their URL schemes, auth headers, pagination walks,
and fail-loud remedies offline; the local adapter runs against the demo_repo
clone from conftest — real git output, no network at all.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import pytest

from patent_services.repo_adapters import (
    GitHubAdapter,
    GiteeAdapter,
    GitLabAdapter,
    LocalGitAdapter,
    build_adapter,
    flush_response_cache,
)
from patent_services.repo_config import Provider
from patent_services.repo_roles import ADMIN, OBSERVER, PARTICIPANT

TOKEN = "tok-secret-1234"


@pytest.fixture(autouse=True)
def clean_cache():
    flush_response_cache()
    yield
    flush_response_cache()


class StubAPI:
    """A route-table HTTP server: path → (status, payload) or callable(raw_path)."""

    def __init__(self, routes: dict):
        outer = self
        self.routes = routes

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?")[0]
                entry = outer.routes.get(path)
                if entry is None:
                    body = b'{"message": "Not Found"}'
                    status = 404
                elif callable(entry):
                    status, payload = entry(self.path)
                    body = json.dumps(payload).encode("utf-8")
                else:
                    status, payload = entry
                    body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


def rest_provider(platform: str, base_url: str) -> Provider:
    return Provider(name="stub", platform=platform, base_url=base_url, token=TOKEN, declared_role=None)


def commit_item(index: int, sha: str = None, author_login: str = None) -> dict:
    return {
        "sha": sha or f"{index:040x}",
        "commit": {
            "author": {"name": f"作者{index}", "email": f"a{index}@example.com", "date": "2025-01-01T00:00:00Z"},
            "message": f"commit {index}\n\nbody",
        },
        "author": {"login": author_login} if author_login else None,
        "html_url": "https://example.com/commit",
    }


class TestGitHub:
    def test_identity_repos_and_roles(self):
        api = StubAPI(
            {
                "/api/v3/user": (200, {"login": "miner", "name": "张三", "email": "zhang@example.com", "id": 1}),
                "/api/v3/user/repos": (
                    200,
                    [
                        {
                            "full_name": "o/admin-repo",
                            "permissions": {"admin": True, "push": True, "pull": True},
                            "default_branch": "main",
                            "html_url": "https://github.com/o/admin-repo",
                            "description": "",
                        },
                        {
                            "full_name": "o/read-repo",
                            "permissions": {"admin": False, "push": False, "pull": True},
                            "default_branch": "main",
                            "html_url": "https://github.com/o/read-repo",
                            "description": "",
                        },
                    ],
                ),
                "/api/v3/repos/o/r": (200, {"full_name": "o/r", "permissions": {"push": True, "pull": True}, "default_branch": "main", "html_url": "", "description": ""}),
            }
        )
        try:
            adapter = GitHubAdapter(rest_provider("github", api.base_url))
            assert adapter.identity()["login"] == "miner"
            repos = adapter.list_repos(10)
            assert repos[0]["role"] == ADMIN
            assert repos[1]["role"] == OBSERVER
            assert adapter.repo_info("o/r")["role"] == PARTICIPANT
        finally:
            api.stop()

    def test_commit_detail_normalizes_files_and_patch_head(self):
        detail = dict(commit_item(1, sha="b" * 40))
        detail["files"] = [
            {"filename": "src/engine.py", "additions": 10, "deletions": 2, "patch": "\n".join(f"@ line{i}" for i in range(20))},
            {"filename": "docs/x.md", "additions": 1, "deletions": 0},
        ]
        api = StubAPI({"/api/v3/repos/o/r/commits/" + "b" * 40: (200, detail)})
        try:
            adapter = GitHubAdapter(rest_provider("github", api.base_url))
            commit = adapter.get_commit("o/r", "b" * 40)
            assert commit["author_login"] is None
            assert commit["files"][0]["path"] == "src/engine.py"
            assert len(commit["files"][0]["patch_head"].splitlines()) == 12
            assert commit["files"][1]["patch_head"] == ""
        finally:
            api.stop()

    def test_pagination_walks_pages_until_a_short_one(self):
        def commits(raw_path):
            params = parse_qs(raw_path.split("?")[1])
            page = int(params.get("page", ["1"])[0])
            if page == 1:
                return 200, [commit_item(i) for i in range(50)]
            return 200, [commit_item(i) for i in range(10)]

        api = StubAPI({"/api/v3/repos/o/r/commits": commits})
        try:
            adapter = GitHubAdapter(rest_provider("github", api.base_url))
            assert len(adapter.list_commits("o/r", 200)) == 60
            assert len(adapter.list_commits("o/r", 55)) == 55
        finally:
            api.stop()


class TestGitLab:
    def test_access_levels_drive_the_role(self):
        def project(level):
            return {
                "path_with_namespace": "g/p",
                "permissions": {"project_access": {"access_level": level} if level is not None else None, "group_access": None},
                "default_branch": "main",
                "web_url": "",
                "description": "",
            }

        api = StubAPI(
            {
                "/api/v4/projects/g%2Fp": (200, project(40)),
                "/api/v4/projects/g%2Fq": (200, project(30)),
                "/api/v4/projects/g%2Fz": (200, {"path_with_namespace": "g/z", "permissions": {}, "default_branch": "main", "web_url": "", "description": ""}),
            }
        )
        try:
            adapter = GitLabAdapter(rest_provider("gitlab", api.base_url))
            assert adapter.repo_info("g/p")["role"] == ADMIN
            assert adapter.repo_info("g/q")["role"] == PARTICIPANT
            assert adapter.repo_info("g/z")["role"] == OBSERVER
        finally:
            api.stop()

    def test_commit_diff_counts_lines(self):
        meta = {"id": "c" * 40, "author_name": "李四", "author_email": "li@example.com", "title": "add cache", "committed_date": "2025-01-02T00:00:00Z"}
        diffs = [{"new_path": "src/cache.py", "diff": "--- a/src/cache.py\n+++ b/src/cache.py\n@@ -0,0 +1,2 @@\n+cache = {}\n+keep = True\n-fall = 1\n"}]
        api = StubAPI(
            {
                "/api/v4/projects/g%2Fp/repository/commits/" + "c" * 40: (200, meta),
                "/api/v4/projects/g%2Fp/repository/commits/" + "c" * 40 + "/diff": (200, diffs),
            }
        )
        try:
            adapter = GitLabAdapter(rest_provider("gitlab", api.base_url))
            commit = adapter.get_commit("g/p", "c" * 40)
            assert commit["author_name"] == "李四"
            assert commit["files"][0]["additions"] == 2
            assert commit["files"][0]["deletions"] == 1
        finally:
            api.stop()


class TestGitee:
    def test_pull_only_permissions_read_observer(self):
        api = StubAPI(
            {
                "/api/v5/user": (200, {"login": "miner", "name": "张三", "email": "", "id": 1}),
                "/api/v5/repos/o/r": (
                    200,
                    {"full_name": "o/r", "permissions": {"admin": False, "push": False, "pull": True}, "default_branch": "master", "html_url": "", "description": ""},
                ),
            }
        )
        try:
            adapter = GiteeAdapter(rest_provider("gitee", api.base_url))
            assert adapter.identity()["login"] == "miner"
            assert adapter.repo_info("o/r")["role"] == OBSERVER
        finally:
            api.stop()


class TestFailLoud:
    def test_http_error_names_the_status_and_never_the_token(self):
        api = StubAPI({"/api/v3/repos/o/r": (403, {"message": "forbidden"})})
        try:
            adapter = GitHubAdapter(rest_provider("github", api.base_url))
            with pytest.raises(RuntimeError, match="HTTP 403") as excinfo:
                adapter.repo_info("o/r")
            assert TOKEN not in str(excinfo.value)
        finally:
            api.stop()

    def test_unreachable_host_carries_the_remedy(self):
        adapter = GitHubAdapter(rest_provider("github", "http://127.0.0.1:1"))
        with pytest.raises(RuntimeError, match="VPN"):
            adapter.repo_info("o/r")

    def test_bad_sha_and_repo_shapes_are_value_errors(self):
        adapter = GitHubAdapter(rest_provider("github", "http://127.0.0.1:1"))
        with pytest.raises(ValueError, match="sha"):
            adapter.get_commit("o/r", "rm -rf /")
        with pytest.raises(ValueError, match="owner/repo"):
            adapter.repo_info("just-a-name")
        with pytest.raises(ValueError, match="非法字符"):
            adapter.repo_info("o/r?query")

    def test_non_mapping_payload_fails_instead_of_attribute_error(self):
        api = StubAPI({"/api/v3/repos/o/r": (200, ["unexpected", "list"])})
        try:
            adapter = GitHubAdapter(rest_provider("github", api.base_url))
            with pytest.raises(RuntimeError, match="非映射结构"):
                adapter.repo_info("o/r")
        finally:
            api.stop()


class TestLocalAdapter:
    def test_repo_info_declares_the_role_basis(self, local_provider):
        adapter = build_adapter(local_provider)
        info = adapter.repo_info("demo-repo")
        assert info["role"] == ADMIN
        assert "声明" in info["role_basis"]
        assert info["default_branch"] == "main"

    def test_history_carries_files_and_counts(self, local_provider):
        adapter = build_adapter(local_provider)
        commits = adapter.list_commits("demo-repo", 10)
        assert [commit["author_name"] for commit in commits] == ["李四", "张三"]
        newest = commits[0]
        paths = {entry["path"]: entry for entry in newest["files"]}
        assert paths["src/cache.py"]["additions"] == 1
        assert paths["src/engine.py"]["deletions"] == 1
        short = adapter.get_commit("demo-repo", newest["sha"][:8])
        assert short["sha"].startswith(newest["sha"][:8])

    def test_identity_reads_repo_config(self, local_provider):
        assert build_adapter(local_provider).identity()["email"] == "zhang@example.com"

    def test_read_file_with_ref_and_truncation(self, local_provider):
        adapter = build_adapter(local_provider)
        assert "value = 2" in adapter.read_file("demo-repo", "src/engine.py", None)["content"]
        assert "value = 1" in adapter.read_file("demo-repo", "src/engine.py", "v0.1.0")["content"]

    def test_contributors_tags_and_no_pulls(self, local_provider):
        adapter = build_adapter(local_provider)
        names = {entry["name"] for entry in adapter.contributors("demo-repo", 10)}
        assert names == {"张三", "李四"}
        assert adapter.list_releases("demo-repo", 5)[0]["tag"] == "v0.1.0"
        assert adapter.list_pulls("demo-repo", 5) == []

    def test_option_style_refs_are_rejected(self, local_provider):
        adapter = build_adapter(local_provider)
        with pytest.raises(ValueError, match="非法"):
            adapter.get_commit("demo-repo", "--exec=evil")
        with pytest.raises(ValueError, match="非法"):
            adapter.read_file("demo-repo", "-rf", None)

    def test_declared_role_is_required_and_validated(self, demo_repo):
        from patent_services.repo_config import Provider

        with pytest.raises(ValueError, match="declared_role"):
            build_adapter(Provider(name="x", platform="local", base_url=str(demo_repo), token=None, declared_role="owner"))

    def test_non_repository_path_fails_loud(self, tmp_path):
        from patent_services.repo_config import Provider

        adapter = build_adapter(Provider(name="x", platform="local", base_url=str(tmp_path / "not-a-repo"), token=None, declared_role="observer"))
        with pytest.raises(RuntimeError, match="git 仓库目录"):
            adapter.repo_info("whatever")
