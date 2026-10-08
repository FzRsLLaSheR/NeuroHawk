# 🦅 NeuroHawk

> Automated GitHub surveillance for AI pentesting, LLM security, and MCP offensive research — running silently, every 6 hours.

---

## What it does

NeuroHawk continuously scans GitHub for newly published repositories matching advanced boolean queries focused on AI-powered offensive security. Every 6 hours, GitHub Actions wakes it up, runs the search, computes a relevance score, compares against the previous state, and logs anything new.

No noise. No duplicates. Just new signal.

---

## Monitored queries

| Name | Query |
|------|-------|
| `ai-pentest` | `topic:ai-pentest` |
| `pentest-ai` | `topic:pentest-ai` |
| `ai-pentesting` | `topic:ai-pentesting` |
| `ai-penetration-testing` | `topic:ai-penetration-testing` |
| `mcp-security` | `topic:mcp-security` |
| `llm-security` | `topic:llm-security` |
| `ai-red-team` | `"red team" AI pentest in:description` |
| `autonomous-pentest` | `"autonomous pentest" in:description` |
| `ai-exploit` | `"AI exploit" OR "LLM exploit" in:description` |

Queries are fully customizable in `watcher.py`.

---

## How it works

    GitHub Actions  (every 6h / manual trigger)
          │
          ▼
      watcher.py
          ├── calls GitHub Search API for each query
          ├── filters results and computes a relevance score
          ├── compares results with previous_results.json
          ├── logs NEW repos to monitor.log  [NEW]
          └── saves updated state to previous_results.json

---

## Files

| File | Description |
|------|-------------|
| `watcher.py` | Main script — queries, logic, logging |
| `.github/workflows/watcher.yml` | GitHub Actions automation |
| `previous_results.json` | Seen repo state (auto-updated) |
| `monitor.log` | Full run history with all findings |

---

## Reading the results

Open `monitor.log` — new repositories are marked with `[NEW]` and carry a relevance score:

    [2026-10-08 15:04:18 UTC] [INFO] ============================================================
    [2026-10-08 15:04:18 UTC] [INFO] NeuroHawk avviato
    [2026-10-08 15:04:18 UTC] [INFO] Query: 'ai-pentest' [core]
    [2026-10-08 15:04:18 UTC] [NEW]   0xSteph/pentest-ai  [score=90]
                                          ⭐ 1723  🗣 Python  📅 2026-04-04
                                          🔗 https://github.com/0xSteph/pentest-ai

---

## Customization

Edit the `QUERIES` list in `watcher.py`:

    QUERIES = [
        {
            "name": "my-query",
            "q": 'topic:my-topic',
            "tier": "core",
        },
    ]

Change the lookback window (default: last 7 days):

    DAYS_LOOKBACK = 7

Change the schedule in `watcher.yml` (default: every 6h):

    - cron: "0 */6 * * *"   # every 6 hours
    - cron: "0 8 * * *"     # daily at 08:00 UTC

---

## Run manually

    python watcher.py

    # with a GitHub token (higher rate limits)
    GITHUB_TOKEN=ghp_xxx python watcher.py

Requires Python 3.10+. No external dependencies.

---

*Runs on GitHub Actions. Zero cost on public repositories.*
