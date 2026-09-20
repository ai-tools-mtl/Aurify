"""Server wiring: the MCP app exposes exactly the domain tools."""

from __future__ import annotations

import asyncio

from patent_services.server import mcp


def test_server_registers_the_nine_domain_tools():
    tools = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert tools == {"parse_disclosure_docx", "export_disclosure", "export_application_docs", "render_drawio_figure", "render_html_figure", "lint_drawio_figure", "search_patent_archive", "run_experiment", "search_cn_patents"}

def test_fail_loud_keeps_the_domain_message_on_the_wire():
    """The SDK swallows non-ToolError exceptions into a bare 'Error executing
    tool' with no cause; fail_loud must convert the domain failure first so
    the remedy text (e.g. the proxy guidance on a dead search channel)
    reaches the model."""
    from mcp.server.mcpserver.exceptions import ToolError

    from patent_services.server import fail_loud

    @fail_loud
    def broken(query: str) -> str:
        raise RuntimeError("网络不可达：请开启代理后重试（connection refused）")

    try:
        broken(query="x")
        raise AssertionError("expected ToolError")
    except ToolError as exc:
        message = str(exc)
        assert "RuntimeError" in message
        assert "请开启代理" in message
        assert "Error executing tool" not in message


def test_fail_loud_passes_successes_and_tool_errors_through():
    from mcp.server.mcpserver.exceptions import ToolError

    from patent_services.server import fail_loud

    @fail_loud
    def fine(query: str) -> str:
        return f"ok:{query}"

    assert fine(query="x") == "ok:x"

    @fail_loud
    def anticipated(query: str) -> str:
        raise ToolError("检索词不能为空")

    try:
        anticipated(query="x")
        raise AssertionError("expected ToolError")
    except ToolError as exc:
        assert str(exc) == "检索词不能为空"

def _stub_search_payload():
    return {
        "results": {
            "total_num_results": 1,
            "cluster": [
                {
                    "result": [
                        {
                            "patent": {
                                "publication_number": "CN0000000A",
                                "title": "测试对比文件",
                                "assignee": "测试申请人",
                                "priority_date": "2020-01-01",
                            }
                        }
                    ]
                }
            ],
        }
    }


def test_search_cn_patents_through_the_mcp_call_path(monkeypatch):
    """Call the tool the way a client does. A tool function that shadows its
    implementation import recurses instead of searching — this catches that
    shape on the real call path, not just registration."""
    import patent_services.prior_art as prior_art

    monkeypatch.setattr(prior_art, "_fetch_json", lambda url: _stub_search_payload())
    result = asyncio.run(mcp.call_tool("search_cn_patents", {"query": "测试检索词", "limit": 3}))
    text = result.content[0].text
    assert "CN0000000A" in text
    assert "共 1 条命中" in text


def test_render_html_figure_tool_resolves_the_implementation(monkeypatch):
    """The same shadowing shape as search: the tool body must reach the
    render module's function, not itself."""
    import patent_services.server as server

    calls = []
    # The server bound the implementation at import time (the alias that fixed
    # the shadowing), so patch the server's name, not the render module's.
    monkeypatch.setattr(server, "_render_html_figure_impl", lambda source, fmt: calls.append((source, fmt)) or "/tmp/out.png")
    result = asyncio.run(mcp.call_tool("render_html_figure", {"source": "figures/source/fig.html"}))
    assert calls == [("figures/source/fig.html", "png")]
    text = result.content[0].text
    assert "/tmp/out.png" in text
