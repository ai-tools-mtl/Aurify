# deepseek-harness-patent-services

English | [中文](README.zh.md)

Aurify's Python MCP stdio server. When enabled through the Bundle, fifteen tools appear with the `mcp__patent__` prefix. See the [installation guide](../../docs/install/INSTALL-NEW-PROFILE.md#services-and-runtime-dependencies) for setup.

## Tool interfaces

`?` denotes an optional parameter; exact defaults live in `src/patent_services/server.py`.

| Tool and parameters | Behavior |
|---|---|
| `import_patent_document(project_dir, document_path, name?, overwrite?)` | Map docx section headings to eight chapters, seed the brief and create a missing manifest. Extra top-level sections become extra chapters; claims and abstracts are not imported verbatim. Existing content is protected by default |
| `parse_disclosure_docx(path, output_path?)` | Parse styles and numbering into three-level Markdown, optionally writing it; skip tables and embedded images |
| `export_disclosure(project_dir, fmt?)` | Generate a disclosure from the shipped agency template, embed final figures and return the path, figure count and review/heading warnings |
| `export_application_docs(project_dir, fmt?)` | Export `application/{claims,description,abstract}.md` into one file with sections; add abstract and description figures when available |
| `render_drawio_figure(source, fmt?)` | drawio → png/pdf/svg/jpg; geometry errors block rendering and warnings accompany results |
| `lint_drawio_figure(source)` | Check missing anchors, waypoints inside boxes, shared bends and parallel corridors |
| `render_html_figure(source, fmt?)` | Edge/Chrome headless screenshots to png/jpg; text uses grayscale antialiasing (`--disable-lcd-text`) for pure black-and-white output |
| `search_patent_archive(query, archive_dir, limit?)` | jieba + SQLite FTS5 BM25 over local Markdown, excluding export/tool directories; return sources and snippets |
| `search_cn_patents(query, limit?, since_year?, project_dir?)` | Google Patents CN search; append successful results to `reference/search-history.md` when a project directory is supplied |
| `run_experiment(project_dir, experiment, command?, timeout_seconds?)` | Run in Docker, append `results/run-log.md`, return output tail and log path |
| `repo_check_access(provider?, repo?)` | Probe the platform connection: identity, masked token and accessible repositories; with `repo`, return that repository's role and attribution discipline |
| `repo_scan(repo, mining_dir, provider?, max_commits?)` | Collect role-gated mining facts (module clusters, hotspot files, release spans, contributors), appending `<mining_dir>/repo-mining/<owner>__<repo>/ledger.md` |
| `repo_read_object(repo, kind, ref?, path?, provider?)` | Deep-read one object: commit (with patch excerpts) / pull / release / file (capped with an explicit note) |
| `repo_verify_evidence(candidate_path, provider?)` | Re-fetch each commit a candidate cites, reconciling sha/author/touched paths and inventor proposals into a pass or mismatch list |
| `repo_forget(provider)` | Remove the provider's token line from the config, clear cached responses and name the platform-side revocation step |

## Repository mining contracts

- Connection settings live in `$DSH_HOME/repo-mining.yaml` (structured YAML, separate from patent-services.yaml): a `providers` list (`platform: github|gitlab|gitee|local`, `base_url` — required for self-hosted hosts; for `local` it is the clone directory — plus `token`), `default_provider` and `limits.max_commits_per_scan`. The `DSH_PATENT_REPO_TOKEN_<NAME>` environment variable overrides the file value; tool output always masks tokens.
- Roles map from the token's real permissions: GitHub `permissions.admin/maintain/push`, GitLab `access_level` (≥40/≥30/≥10), Gitee `permissions` — admin / participant / observer. For `local`, the role is the declared `declared_role`; the adapter only verifies the directory reads as a git repository. The role bounds the scan budget (commit and deep-read caps intersect with the config limit) and the attribution discipline (admins mine everything, participants center on their own commits, observers stop at leads).
- Scanning, deep reads and evidence reconciliation are read-only; repository content is treated as untrusted data and no code from it is executed. Inventor proposals may only come from evidence authors; a candidate failing `repo_verify_evidence` must not proceed to prior-art search.

## File and execution contracts

- Import extracts paragraphs only. Tables and images are counted but omitted; convert `.doc`, `.wps` or PDF to docx first. Top-level heading checks precede section-keyword matching. Reports list omitted sections and empty chapters.
- Export follows source files; `brief.md` is excluded from the disclosure body. The template header, information table and page setup remain; its footer is cleared. Headings, lists and emphasis are normalized, with malformed heading warnings returned. Exports stamp source fingerprints for the pipeline gate.
- `fmt` defaults to `docx`. PDF first tries Windows Word COM, then weasyprint, which needs separate installation and system libraries. The HTML fallback may differ from Word layout. Both paths retain the docx.
- Sources in `figures/source/` render to the `figures/` root; other sources render beside themselves. drawio tries an explicit CLI, PATH, the Windows user installation, then Docker. An invalid explicit CLI path fails immediately. HTML uses a fixed 1600×2400 viewport and may crop tall content.
- Patent search requires connectivity. Network/HTTP errors and unknown responses fail explicitly, rather than becoming empty hits. Read details separately with `web_fetch`. `search-history.md` records raw searches; `prior-art.md` records selected comparison documents.
- Experiments default to `python run.py`, with a 30–7200 second timeout. Only a single Python invocation with plain arguments is allowed; shell operators and `python -c` are rejected. Dependencies default to wheels only; installation failure stops the command and records a nonzero exit code. Logs retain code fingerprints, exit codes and output for success, failure and timeout. When `plot.py` exists, a successful run also executes it and reports PNGs under `results/`; final figures must then be copied, numbered and visually checked.

A log alone is not completion: quantified effects need at least one experiment whose latest run succeeded, or an explicit no-experiment declaration. A successful run does not establish evidence for every metric; verify each citation.

## Configuration and running

Settings live in `$DSH_HOME/patent-services.yaml` (default `~/.dsh/`). The host reads `mcp_enabled` and `mcp_project_dir` / `mcp_wheel` at process start; restart after changes. Wheel mode uses an unpinned PyPI name and does not guarantee use of a locally installed wheel.

Python preferences such as `experiment_image`, `experiment_allow_any_command`, `experiment_pip_allow_source`, `drawio_bin`, `drawio_docker_image` and `html_browser` apply on the next call; corresponding environment variables win. Default images are `q771103517/dsh-patent:latest` and `q771103517/dsh-patent-experiment:latest`; Dockerfiles live in `src/patent_services/assets/`.

Run from the repository root:

```sh
uv run --locked --project python/patent-services python -m patent_services
uv run --locked --project python/patent-services --group test pytest python/patent-services/tests -q
uv build --out-dir dist python/patent-services
```

The wheel includes templates, Dockerfiles and a `patent-services` entry point. The MCP server can access host paths passed to it and does not implement the dsh filesystem sandbox. The experiment container mounts the whole project read-write. See the [development guide](../../docs/DEVELOPMENT.md) for build and validation scope.
