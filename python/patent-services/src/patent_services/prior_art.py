"""Chinese patent discovery through the Google Patents search API.

Prior-art discovery for the disclosure's background chapters: the model
describes the technical idea in Chinese, this module queries Google Patents
(patents.google.com) restricted to CN publications and returns the closest
hits — publication number, title, assignee, priority date — one line each.
Google Patents carries the full CNIPA corpus with Chinese-language matching;
its detail pages (``patents.google.com/patent/<number>/zh``) are statically
rendered, so reading one hit's abstract and claim 1 goes through the
harness's ordinary ``web_fetch`` tool, keeping this module discovery-only.

The search endpoint is Google's unauthenticated ``/xhr/query`` JSON API; the
host machine must reach it through a proxy (urllib picks the system proxy up
on Windows), and every dead end — no route, HTTP error, an unrecognized
payload — fails loud with a remedy instead of an empty result, because an
invented hit is worse than a failed search.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

#: Seconds one search request may run before failing loud.
SEARCH_TIMEOUT_SECONDS = 30

#: How long one identical query's result stays cached in this server process:
#: the interview's rolling re-searches repeat queries within minutes, and a
#: repeated call should not re-hit (or re-trip) the endpoint for the same words.
SEARCH_CACHE_TTL_SECONDS = 1800

#: Upper bound on cached queries, so a long-lived server cannot grow forever.
SEARCH_CACHE_MAX_ENTRIES = 50

#: The in-process cache: (query, limit, since_year) -> (monotonic time, result
#: text). Server-process lifetime only — a restart forgets it, by design.
_SEARCH_CACHE: dict[tuple[str, int, int | None], tuple[float, str]] = {}

#: Browser User-Agent: the endpoint tolerates anonymous calls but rejects
#: requests identifying as a bare library client.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

#: How many hits the API returns per request (its own page default); larger
#: limits are met by slicing, not by a second request.
PAGE_SIZE = 10

PROXY_GUIDANCE = (
    "检索中国专利需要访问 Google Patents（patents.google.com）。当前网络不可达："
    "请开启本机代理（如 Clash 的系统代理）后重试；检索结果仅来自该接口，"
    "不要在无检索依据的情况下编造对比文件。"
)


def build_search_url(query: str, since_year: int | None = None) -> str:
    """Build the Google Patents XHR search URL for one CN-restricted query.

    Args:
        query: free-text query in Chinese (or mixed), matched against title,
            abstract, and claims.
        since_year: when given, only results filed in or after this year
            (``after=priority:YYYY0101``).

    Returns:
        The complete request URL, with the query string encoded exactly once
        (the endpoint consumes a whole inner query string as one parameter).
    """
    inner = f"q={query}&country=CN"
    if since_year is not None:
        inner += f"&after=priority:{since_year}0101"
    return "https://patents.google.com/xhr/query?" + urllib.parse.urlencode({"url": inner, "exp": ""}, quote_via=urllib.parse.quote)


def search_cn_patents(query: str, limit: int = 10, since_year: int | None = None) -> str:
    """Search Chinese patents on Google Patents and format the closest hits.

    Args:
        query: free-text query in Chinese (core feature words work best).
        limit: maximum hits to return, 1-10 (default 10; one API page).
        since_year: when given, only results filed in or after this year.

    Returns:
        One line per hit — publication number, title, assignee, priority
        date — headed by the total count and followed by the detail-page
        reading hint (``web_fetch`` on ``patents.google.com/patent/<号>/zh``).

    Raises:
        ValueError: an empty query or an out-of-range limit.
        RuntimeError: the network is unreachable (proxy guidance), the
            endpoint returned an HTTP error, or the payload shape was
            unrecognized (its head is carried for diagnosis).
    """
    query = query.strip()
    if not query:
        raise ValueError("检索词不能为空")
    if not 1 <= limit <= PAGE_SIZE:
        raise ValueError(f"limit 必须在 1-{PAGE_SIZE} 之间：{limit}")
    cache_key = (query, limit, since_year)
    cached = _SEARCH_CACHE.get(cache_key)
    if cached is not None and time.monotonic() - cached[0] < SEARCH_CACHE_TTL_SECONDS:
        return cached[1] + f"\n（缓存命中：{SEARCH_CACHE_TTL_SECONDS // 60} 分钟内同一检索词直接复用结果）"
    payload = _fetch_json(build_search_url(query, since_year))
    results = payload.get("results") if isinstance(payload, dict) else None
    clusters = results.get("cluster") if isinstance(results, dict) else None
    if not isinstance(results, dict) or not isinstance(clusters, list):
        raise RuntimeError(
            "Google Patents 返回了无法识别的结构（可能是接口变更或限流）。响应开头："
            + json.dumps(payload, ensure_ascii=False)[:400]
        )
    total = results.get("total_num_results")
    entries = [item.get("patent", {}) for item in (clusters[0].get("result", []) if clusters else [])][:limit]
    lines = []
    for patent in entries:
        lines.append(
            " ｜ ".join(
                str(part)
                for part in (
                    patent.get("publication_number", "?"),
                    re.sub(r"\s+", " ", str(patent.get("title", ""))).strip(),
                    patent.get("assignee", ""),
                    patent.get("priority_date", ""),
                )
                if part != ""
            )
        )
    header = f"共 {total} 条命中，返回前 {len(lines)} 条：" if isinstance(total, int) else f"返回 {len(lines)} 条命中："
    if not lines:
        return header + "（无命中，换检索词再试）"
    detail_hint = "读某篇的摘要与权利要求：用 web_fetch 抓 https://patents.google.com/patent/<公开号>/zh"
    result = header + "\n" + "\n".join(lines) + "\n" + detail_hint
    if len(_SEARCH_CACHE) >= SEARCH_CACHE_MAX_ENTRIES:
        oldest = min(_SEARCH_CACHE, key=lambda key: _SEARCH_CACHE[key][0])
        del _SEARCH_CACHE[oldest]
    _SEARCH_CACHE[cache_key] = (time.monotonic(), result)
    return result


#: Where the search-history ledger lives inside a patent project: every
#: successful discovery search appends its query and hits here, so a network
#: outage still leaves the model the numbers it already found (the in-process
#: cache dies with the process; the ledger is the durable half).
SEARCH_LEDGER_NAME = "search-history.md"


def append_search_ledger(project_dir: str, query: str, result: str) -> Path:
    """Append one successful search to the project's search-history ledger.

    Args:
        project_dir: the patent project directory (must exist); the ledger
            lands under its ``reference/`` folder, created when missing.
        query: the query text the caller issued.
        result: the formatted result text (header, hits, hint) verbatim.

    Returns:
        The ledger file's path.

    Raises:
        ValueError: the project directory does not exist.
    """
    root = Path(project_dir)
    if not root.is_dir():
        raise ValueError(f"项目目录不存在：{project_dir}（不落账本，本次检索未记录）")
    reference = root / "reference"
    reference.mkdir(exist_ok=True)
    ledger = reference / SEARCH_LEDGER_NAME
    stamp = datetime.now().isoformat(timespec="seconds")
    entry = f"## {stamp} ｜ 检索词：{query}\n\n{result}\n\n"
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    return ledger


def _fetch_json(url: str) -> object:
    """Fetch one JSON payload from Google Patents.

    Args:
        url: the complete request URL.

    Returns:
        The decoded payload.

    Raises:
        RuntimeError: the request could not reach the endpoint (its cause is
            carried, with proxy guidance for the common blocked-network case)
            or the endpoint answered non-200.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=SEARCH_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise RuntimeError(f"Google Patents 返回 HTTP {response.status}。稍后重试，或直接在 patents.google.com 手动检索。")
            return json.loads(response.read().decode("utf-8"))
    except RuntimeError:
        raise
    except Exception as cause:
        raise RuntimeError(PROXY_GUIDANCE + f"（{cause}）") from cause
