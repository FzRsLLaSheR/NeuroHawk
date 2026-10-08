NeuroHawk
Automated GitHub surveillance for AI pentesting, LLM security, and MCP offensive research — running silently, every 6 hours.

What it does
NeuroHawk scans GitHub every 6 hours for new repositories matching boolean queries on AI-powered offensive security. It compares results against the previous state and logs only new signal.

Monitored queries
Name	Query
ai-pentest	topic:ai-pentest
pentest-ai	topic:pentest-ai
ai-pentesting	topic:ai-pentesting
ai-penetration-testing	topic:ai-penetration-testing
mcp-security	topic:mcp-security
llm-security	topic:llm-security
ai-red-team	"red team" AI pentest in:description
autonomous-pentest	"autonomous pentest" in:description
ai-exploit	"AI exploit" OR "LLM exploit" in:description

How it works
GitHub Actions  (every 6h / manual trigger)
      │
      ▼
  watcher.py
      ├── calls GitHub Search API for each query
      ├── filters and scores results
      ├── logs NEW repos to monitor.log  [NEW]
      └── saves state to previous_results.json

Files
File	Description
watcher.py	Main script — queries, logic, logging
.github/workflows/watcher.yml	GitHub Actions automation
previous_results.json	Seen repo state (auto-updated)
monitor.log	Full run history with all findings

Run manually
python watcher.py

Requires Python 3.10+. No external dependencies.

Runs on GitHub Actions. Zero cost on public repositories.
