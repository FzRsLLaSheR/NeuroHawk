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
    {"name": "ai-pentest", "q": 'topic:ai-pentest', "tier": "core"},
    {"name": "pentest-ai", "q": 'topic:pentest-ai', "tier": "core"},
    {"name": "ai-pentesting", "q": 'topic:ai-pentesting', "tier": "core"},
    {"name": "ai-penetration-testing", "q": 'topic:ai-penetration-testing', "tier": "core"},
    {"name": "mcp-security", "q": 'topic:mcp-security', "tier": "core"},
    {"name": "llm-security", "q": 'topic:llm-security', "tier": "core"},
    {"name": "ai-red-team", "q": '"red team" AI pentest in:description', "tier": "extended"},
    {"name": "autonomous-pentest", "q": '"autonomous pentest" in:description', "tier": "extended"},
    {"name": "ai-exploit", "q": '"AI exploit" OR "LLM exploit" in:description', "tier": "extended"},
    {"name": "cn-ai-pentest", "q": '"AI渗透" OR "智能渗透" OR "AI渗透测试" OR "自动化渗透" in:description,readme', "tier": "extended"},
    {"name": "cn-mixed", "q": '("CTF" OR "pentest" OR "red team") ("渗透" OR "攻防" OR "红队") in:description,readme', "tier": "extended"},
    {"name": "cn-llm-security", "q": '"大模型安全" OR "LLM安全" OR "AI安全" in:description,readme', "tier": "extended"},
]

CORE_TOPICS = {
    "ai-pentest", "pentest-ai", "ai-pentesting", "ai-penetration-testing",
    "ai-penetration", "pentest", "penetration-testing",
    "mcp-security", "llm-security", "ai-security", "agent-security",
    "ai-red-team", "red-teaming", "red-team", "red-team-tools",
    "offensive-security", "ai-hacking", "ai-exploit",
    "ctf", "ctf-tools", "hacking", "cybersecurity", "security",
}

BLOCK_DESC_KEYWORDS = [
    "portfolio", "profile readme", "my profile", "personal website",
    "awesome list", "awesome-list", "curated list", "curated list of",
    "collection of links", "book of", "study notes", "course notes",
    "my resume", "cv ", "resume ",
]

DAYS_LOOKBACK = 7
DAYS_MONITOR_UPDATES = 30
UPDATE_MIN_HOURS = 1
UPDATE_MAX_AGE_DAYS = 30
PER_PAGE = 50
MAX_SEEN_IDS = 500
MAX_LAST_RESULTS = 500

MIN_STARS_CORE = 0
MIN_STARS_EXTENDED = 3
MIN_DESC_LENGTH = 15

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


def detect_region(repo: dict) -> str:
    text = ((repo.get("description") or "") + " " + (repo.get("full_name") or "")).lower()
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff':
            return "cn"
    for kw in ["cn-", "china", "chinese", "中文", "华"]:
        if kw in text:
            return "cn"
    return "intl"


def compute_relevance_score(repo: dict, tier: str) -> int:
    score = 0
    topics = set(t.lower() for t in repo.get("topics", []))
    desc = (repo.get("description") or "").lower()
    name = (repo.get("full_name") or "").lower()

    high_value_topics = {"ai-pentest", "pentest-ai", "ai-pentesting", "ai-penetration-testing", "mcp-security", "llm-security"}
    mid_value_topics = {"ai-security", "agent-security", "ai-red-team", "red-teaming", "red-team", "offensive-security", "ai-hacking", "ai-exploit", "ctf", "ctf-tools", "hacking", "cybersecurity"}

    if topics & high_value_topics:
        score += 30
    if topics & mid_value_topics:
        score += 15

    if "pentest" in desc or "penetration" in desc:
        score += 10
    if "red team" in desc or "red-team" in desc or "redteam" in desc:
        score += 8
    if "exploit" in desc or "vulnerability" in desc or "vuln" in desc:
        score += 5
    if "agent" in desc or "llm" in desc or "ai" in desc:
        score += 5
    if "mcp" in desc:
        score += 5
    if "ctf" in desc:
        score += 5
    if "渗透" in desc or "攻防" in desc or "红队" in desc or "安全" in desc:
        score += 10

    if "pentest" in name or "ai-" in name:
        score += 5

    stars = repo.get("stars", 0)
    if stars >= 100:
        score += 20
    elif stars >= 20:
        score += 10
    elif stars >= 5:
        score += 5

    if tier == "extended":
        score -= 5

    return max(0, score)


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
    query_cfg = next((q for q in QUERIES if q["name"] == query_name), None)
    tier = query_cfg.get("tier", "core") if query_cfg else "core"
    min_stars = MIN_STARS_CORE if tier == "core" else MIN_STARS_EXTENDED

    results = []
    for item in items:
        if item["stargazers_count"] < min_stars:
            continue

        desc = (item.get("description") or "").strip()
        if len(desc) < MIN_DESC_LENGTH:
            continue

        desc_lower = desc.lower()
        if any(kw in desc_lower for kw in BLOCK_DESC_KEYWORDS):
            continue

        topics = set(t.lower() for t in item.get("topics", []))
        if not (topics & CORE_TOPICS):
            continue

        repo = {
            "id": item["id"],
            "full_name": item["full_name"],
            "url": item["html_url"],
            "description": desc,
            "stars": item["stargazers_count"],
            "language": item.get("language") or "N/A",
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
            "pushed_at": item.get("pushed_at", ""),
            "topics": item.get("topics", []),
            "query": query_name,
            "tier": tier,
        }
        repo["relevance"] = compute_relevance_score(repo, tier)
        repo["region"] = detect_region(repo)
        results.append(repo)

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
    desc = repo["description"][:80] + "..." if len(repo["description"]) > 80 else repo["description"]
    topics = ", ".join(repo["topics"]) if repo["topics"] else "-"
    score = repo.get("relevance", 0)
    region = repo.get("region", "intl")
    reason = ""
    if repo.get("_update_reason"):
        reason = f"\n     Motivo: {' | '.join(repo['_update_reason'])}"
    return (
        f"  {prefix}{repo['full_name']}  [score={score}] [{region}]\n"
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
        tier = entry.get("tier", "core")
        log(f"Query: '{name}' [{tier}]")
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
                "tier": tier,
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
