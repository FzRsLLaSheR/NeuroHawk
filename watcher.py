#!/usr/bin/env python3

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import quote_plus

QUERIES = [
    {
        "name": "ai-pentest",
        "q": 'topic:ai-pentest OR topic:pentest-ai OR topic:ai-security OR topic:llm-security NOT archived:true fork:false',
    },
    {
        "name": "mcp-security",
        "q": 'topic:mcp-security OR topic:mcp-server "security" OR "pentest" NOT archived:true fork:false',
    },
    {
        "name": "ai-offensive",
        "q": '("AI" OR "LLM" OR "agent") "offensive security" OR "red team" in:name,description,readme NOT archived:true fork:false',
    },
    {
        "name": "autonomous-pentest",
        "q": '"autonomous" "pentest" in:name,description,readme NOT archived:true fork:false',
    },
]

DAYS_LOOKBACK = 7
DAYS_MONITOR_UPDATES = 30
UPDATE_MIN_HOURS = 1
UPDATE_MAX_AGE_DAYS = 30
PER_PAGE = 50
MAX_SEEN_IDS = 500
MAX_LAST_RESULTS = 500
MIN_STARS = 1

RESULTS_FILE = Path("previous_results.json")
LOG_FILE = Path("monitor.log")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def log(message: str, level: str = "INFO"):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] [{level}] {message}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def github_request(url: str) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "neurohawk/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 403:
            raise RuntimeError("Rate limit raggiunto.") from e
        raise RuntimeError(f"HTTP {e.code}: {e.reason}") from e
    except URLError as e:
        raise RuntimeError(f"Errore di rete: {e.reason}") from e


def parse_time(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def search_repositories(query_name: str, query_str: str, days: int) -> list:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    full_query = quote_plus(f"{query_str} created:>={since}")
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={full_query}&sort=updated&order=desc&per_page={PER_PAGE}"
    )
    data = github_request(url)
    return _parse_items(data.get("items", []), query_name)


def search_recently_updated(query_name: str, query_str: str, days: int) -> list:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    full_query = quote_plus(f"{query_str} pushed:>={since}")
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={full_query}&sort=updated&order=desc&per_page={PER_PAGE}"
    )
    data = github_request(url)
    return _parse_items(data.get("items", []), query_name)


def _parse_items(items: list, query_name: str) -> list:
    results = []
    for item in items:
        if item["stargazers_count"] < MIN_STARS:
            continue
        if not item.get("description"):
            continue
        results.append({
            "id": item["id"],
            "full_name": item["full_name"],
            "url": item["html_url"],
            "description": item.get("description") or "",
            "stars": item["stargazers_count"],
            "language": item.get("language") or "N/A",
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
            "pushed_at": item.get("pushed_at", ""),
            "topics": item.get("topics", []),
            "query": query_name,
        })
    return results


def detect_updates(current: list, previous_map: dict) -> list:
    updated = []
    now = datetime.now(timezone.utc)
    for repo in current:
        url = repo["url"]
        if url not in previous_map:
            continue
        prev = previous_map[url]
        cur_pushed = parse_time(repo.get("pushed_at"))
        prev_pushed = parse_time(prev.get("pushed_at"))
        if not cur_pushed or not prev_pushed:
            continue
        push_diff = cur_pushed - prev_pushed
        cur_topics = set(repo.get("topics", []))
        prev_topics = set(prev.get("topics", []))
        new_topics = cur_topics - prev_topics
        repo_age = now - (parse_time(repo.get("created_at")) or now)
        if push_diff >= timedelta(hours=UPDATE_MIN_HOURS):
            if repo_age.days <= UPDATE_MAX_AGE_DAYS or new_topics:
                repo["_update_reason"] = []
                if repo_age.days <= UPDATE_MAX_AGE_DAYS:
                    repo["_update_reason"].append(f"repo recente ({repo_age.days}gg)")
                if new_topics:
                    repo["_update_reason"].append(f"nuovi topic: {', '.join(new_topics)}")
                updated.append(repo)
    return updated


def load_previous_results() -> dict:
    if not RESULTS_FILE.exists():
        return {}
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            log("File previous_results.json corrotto, ripartendo da zero.", "WARN")
            return {}


def save_results(results: dict):
    if RESULTS_FILE.exists():
        RESULTS_FILE.rename(RESULTS_FILE.with_suffix(".json.bk"))
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def format_repo(repo: dict, prefix: str = "") -> str:
    desc = repo["description"][:80] + "…" if len(repo["description"]) > 80 else repo["description"]
    topics = ", ".join(repo["topics"]) if repo["topics"] else "—"
    reason = ""
    if repo.get("_update_reason"):
        reason = f"\n     Motivo: {' | '.join(repo['_update_reason'])}"
    return (
        f"  {prefix}{repo['full_name']}\n"
        f"     Stars: {repo['stars']}  Lang: {repo['language']}  Data: {repo['created_at'][:10]}\n"
        f"     URL: {repo['url']}\n"
        f"     Desc: {desc or '(nessuna descrizione)'}\n"
        f"     Topics: {topics}"
        f"{reason}"
    )


def main():
    query_names = [q["name"] for q in QUERIES]

    log("=" * 60)
    log("NeuroHawk avviato")
    log(f"Query monitorate: {', '.join(query_names)}")
    log(f"Nuovi repo: ultimi {DAYS_LOOKBACK} giorni")
    log(f"Aggiornamenti: ultimi {DAYS_MONITOR_UPDATES} giorni")
    log(f"Token GitHub: {'presente' if GITHUB_TOKEN else 'assente'}")
    log("=" * 60)

    if not GITHUB_TOKEN:
        log("ATTENZIONE: nessun GITHUB_TOKEN, rate limit molto basso.", "WARN")

    previous = load_previous_results()
    current_run = {}
    total_new = 0
    total_updated = 0
    errors = 0

    for entry in QUERIES:
        name = entry["name"]
        q_str = entry["q"]
        log(f"Query: '{name}'")
        log(f"  {q_str}")

        try:
            new_repos_all = search_repositories(name, q_str, DAYS_LOOKBACK)
            updated_repos_all = search_recently_updated(name, q_str, DAYS_MONITOR_UPDATES)

            log(f"  {len(new_repos_all)} repo nella finestra 'nuovi', {len(updated_repos_all)} nella finestra 'aggiornati'")

            prev_data = previous.get(name, {})
            prev_ids = set(prev_data.get("seen_ids", []))
            prev_map = {r["url"]: r for r in prev_data.get("last_results", [])}

            new_repos = [r for r in new_repos_all if str(r["id"]) not in prev_ids]
            updated_repos = detect_updates(updated_repos_all, prev_map)
            new_urls = {r["url"] for r in new_repos}
            updated_repos = [r for r in updated_repos if r["url"] not in new_urls]

            if new_repos:
                log(f"  {len(new_repos)} NUOVI repository:", "NEW")
                for repo in new_repos:
                    log(format_repo(repo, "[NEW] "), "NEW")
                    total_new += 1
            else:
                log("  Nessun repo nuovo")

            if updated_repos:
                log(f"  {len(updated_repos)} repository AGGIORNATI:", "UPD")
                for repo in updated_repos:
                    log(format_repo(repo, "[UPD] "), "UPD")
                    total_updated += 1
            else:
                log("  Nessun aggiornamento rilevante")

            all_seen = list(updated_repos_all) + list(new_repos_all)
            all_ids = list(prev_ids | {str(r["id"]) for r in all_seen})

            all_ids = all_ids[-MAX_SEEN_IDS:]
            all_seen = all_seen[-MAX_LAST_RESULTS:]

            current_run[name] = {
                "last_check": datetime.now(timezone.utc).isoformat(),
                "query": q_str,
                "seen_ids": all_ids,
                "last_new": [r["full_name"] for r in new_repos],
                "last_updated": [r["full_name"] for r in updated_repos],
                "last_results": all_seen,
            }

        except RuntimeError as e:
            log(f"  Errore per '{name}': {e}", "ERROR")
            current_run[name] = previous.get(name, {})
            errors += 1

    save_results(current_run)

    log("=" * 60)
    log(f"Completato: {total_new} nuovi, {total_updated} aggiornati, {errors} errori")
    log("=" * 60)

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
