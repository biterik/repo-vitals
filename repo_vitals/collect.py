# Author: Erik Bitzek <e.bitzek@mpi-susmat.de>
# Department of Materials Science, WW8-Materials Simulation,
# Friedrich-Alexander-Universität Erlangen-Nürnberg,
# Dr.-Mack-Straße 77, 90762 Fürth, Germany
"""Collect stage: query GitHub REST/GraphQL APIs and produce today's snapshot.

Robustness rules (ARCHITECTURE.md §7):
- Partial failures never abort the run: each section is collected
  independently; a failure lands in snapshot["errors"] and the section
  value becomes None.
- Traffic endpoints reject GITHUB_TOKEN and need a PAT. If no traffic
  token is provided the traffic section is skipped gracefully.
- Rate limits: Retry-After is respected; 403/429/5xx get exponential
  backoff (capped — an Actions job must fail fast, not sleep an hour).
- All dates are UTC.
"""

from __future__ import annotations

import datetime as dt
import os
import re

import requests

from repo_vitals.schemas import SCHEMA_VERSION

API_ROOT = "https://api.github.com"
USER_AGENT = "repo-vitals (+https://github.com/biterik/repo-vitals)"
MAX_RETRY_AFTER_SECONDS = 120
ACTIVITY_WINDOW_DAYS = 30


class GitHubError(Exception):
    """A GitHub API call failed after retries."""


class GitHubClient:
    """Thin requests wrapper: auth headers, retries, backoff, GraphQL."""

    def __init__(self, token=None, session=None, max_retries=3, sleep=None):
        self.token = token
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.sleep = sleep if sleep is not None else __import__("time").sleep

    def _headers(self, token=None):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        tok = token or self.token
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        return headers

    def request(self, method, path, token=None, params=None, json_body=None):
        url = path if path.startswith("http") else API_ROOT + path
        resp = None
        for attempt in range(self.max_retries + 1):
            resp = self.session.request(
                method,
                url,
                headers=self._headers(token),
                params=params,
                json=json_body,
                timeout=30,
            )
            retryable = resp.status_code in (403, 429) or resp.status_code >= 500
            if not retryable or attempt == self.max_retries:
                return resp
            retry_after = resp.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = min(int(retry_after), MAX_RETRY_AFTER_SECONDS)
            else:
                delay = 2**attempt
            self.sleep(delay)
        return resp

    def get_json(self, path, token=None, params=None):
        resp = self.request("GET", path, token=token, params=params)
        if resp.status_code >= 400:
            raise GitHubError(f"GET {path} -> HTTP {resp.status_code}: {resp.text[:200]}")
        if resp.status_code == 204:
            return None
        return resp.json()

    def graphql(self, query, variables, token=None):
        resp = self.request("POST", "/graphql", token=token, json_body={
            "query": query,
            "variables": variables,
        })
        if resp.status_code >= 400:
            raise GitHubError(f"GraphQL -> HTTP {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        if payload.get("errors"):
            raise GitHubError(f"GraphQL errors: {str(payload['errors'])[:300]}")
        return payload["data"]


ACTIVITY_QUERY = """
query($owner: String!, $name: String!, $since: GitTimestamp!,
      $qPrsOpened: String!, $qPrsMerged: String!,
      $qIssuesOpened: String!, $qIssuesClosed: String!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target { ... on Commit { history(since: $since) { totalCount } } }
    }
  }
  prsOpened: search(query: $qPrsOpened, type: ISSUE) { issueCount }
  prsMerged: search(query: $qPrsMerged, type: ISSUE) { issueCount }
  issuesOpened: search(query: $qIssuesOpened, type: ISSUE) { issueCount }
  issuesClosed: search(query: $qIssuesClosed, type: ISSUE) { issueCount }
}
"""


def collect_snapshot(repo, token=None, traffic_token=None, client=None, now=None):
    """Collect all metric sections for `repo` ("owner/name") into a snapshot dict."""
    client = client or GitHubClient(token=token)
    now = now or dt.datetime.now(dt.UTC)
    errors: list[dict] = []

    def section(name, fn, *args):
        try:
            return fn(*args)
        except Exception as exc:  # noqa: BLE001 - a snapshot with holes beats no snapshot
            errors.append({"section": name, "error": f"{type(exc).__name__}: {exc}"})
            return None

    repo_data = section("repo", client.get_json, f"/repos/{repo}")

    if traffic_token:
        traffic = section("traffic", _collect_traffic, client, repo, traffic_token)
    else:
        traffic = None
        errors.append({
            "section": "traffic",
            "error": "no traffic token provided; views/clones/referrers/paths skipped "
                     "(traffic endpoints reject GITHUB_TOKEN and need a PAT)",
        })

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "date": now.strftime("%Y-%m-%d"),
        "collected_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": repo,
        "popularity": _popularity(repo_data) if repo_data else None,
        "traffic": traffic,
        "releases": section("releases", _collect_releases, client, repo),
        "activity": section("activity", _collect_activity, client, repo, now),
        "meta": _meta(repo_data) if repo_data else None,
        "errors": errors,
    }
    return snapshot


def all_sections_failed(snapshot) -> bool:
    """True when nothing at all was collected (the only case worth a non-zero exit)."""
    sections = ("popularity", "traffic", "releases", "activity", "meta")
    return all(snapshot.get(s) is None for s in sections)


def _popularity(repo_data):
    return {
        "stars": repo_data.get("stargazers_count"),
        "forks": repo_data.get("forks_count"),
        "watchers": repo_data.get("watchers_count"),
        "subscribers": repo_data.get("subscribers_count"),
    }


def _meta(repo_data):
    return {
        "size_kb": repo_data.get("size"),
        "open_issues": repo_data.get("open_issues_count"),
        "default_branch": repo_data.get("default_branch"),
        "created_at": repo_data.get("created_at"),
        "pushed_at": repo_data.get("pushed_at"),
        "fork": repo_data.get("fork", False),
        "archived": repo_data.get("archived", False),
    }


def _per_day(entries):
    """[{timestamp, count, uniques}, ...] -> {"YYYY-MM-DD": {count, uniques}}."""
    return {
        e["timestamp"][:10]: {"count": e["count"], "uniques": e["uniques"]}
        for e in (entries or [])
    }


def _collect_traffic(client, repo, traffic_token):
    views = client.get_json(f"/repos/{repo}/traffic/views", token=traffic_token)
    clones = client.get_json(f"/repos/{repo}/traffic/clones", token=traffic_token)
    referrers = client.get_json(f"/repos/{repo}/traffic/popular/referrers", token=traffic_token)
    paths = client.get_json(f"/repos/{repo}/traffic/popular/paths", token=traffic_token)
    return {
        "views": _per_day(views.get("views")),
        "clones": _per_day(clones.get("clones")),
        "referrers": [
            {"referrer": r["referrer"], "count": r["count"], "uniques": r["uniques"]}
            for r in (referrers or [])
        ],
        "paths": [
            {"path": p["path"], "count": p["count"], "uniques": p["uniques"]}
            for p in (paths or [])
        ],
    }


def _collect_releases(client, repo):
    releases = []
    page = 1
    while page <= 10:
        batch = client.get_json(f"/repos/{repo}/releases", params={"per_page": 100, "page": page})
        if not batch:
            break
        for r in batch:
            releases.append({
                "tag": r.get("tag_name"),
                "name": r.get("name"),
                "published_at": r.get("published_at"),
                "prerelease": r.get("prerelease", False),
                "assets": [
                    {"name": a.get("name"), "downloads": a.get("download_count", 0)}
                    for a in r.get("assets", [])
                ],
            })
        if len(batch) < 100:
            break
        page += 1
    return releases


def _collect_activity(client, repo, now):
    owner, name = repo.split("/", 1)
    since = now - dt.timedelta(days=ACTIVITY_WINDOW_DAYS)
    since_date = since.strftime("%Y-%m-%d")
    data = client.graphql(ACTIVITY_QUERY, {
        "owner": owner,
        "name": name,
        "since": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "qPrsOpened": f"repo:{repo} is:pr created:>={since_date}",
        "qPrsMerged": f"repo:{repo} is:pr merged:>={since_date}",
        "qIssuesOpened": f"repo:{repo} is:issue created:>={since_date}",
        "qIssuesClosed": f"repo:{repo} is:issue closed:>={since_date}",
    })
    branch_ref = (data.get("repository") or {}).get("defaultBranchRef")
    commits = 0
    if branch_ref and branch_ref.get("target"):
        commits = branch_ref["target"]["history"]["totalCount"]
    return {
        "commits_30d": commits,
        "prs_opened_30d": data["prsOpened"]["issueCount"],
        "prs_merged_30d": data["prsMerged"]["issueCount"],
        "issues_opened_30d": data["issuesOpened"]["issueCount"],
        "issues_closed_30d": data["issuesClosed"]["issueCount"],
        "contributors_total": _contributors_total(client, repo),
    }


STARGAZER_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    stargazers(first: 100, after: $cursor,
               orderBy: {field: STARRED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      edges { starredAt }
    }
  }
}
"""


def collect_star_history(client, repo, max_pages=400):
    """First-run backfill (§7.8): every starredAt date since repo birth, ascending."""
    owner, name = repo.split("/", 1)
    dates = []
    cursor = None
    for _ in range(max_pages):
        data = client.graphql(STARGAZER_QUERY, {"owner": owner, "name": name,
                                                "cursor": cursor})
        stargazers = data["repository"]["stargazers"]
        dates.extend(e["starredAt"][:10] for e in stargazers["edges"])
        if not stargazers["pageInfo"]["hasNextPage"]:
            break
        cursor = stargazers["pageInfo"]["endCursor"]
    return dates


def re_enable_workflow(client, repo, workflow_ref=None):
    """§7.1: GitHub disables cron workflows after 60 days without repo activity;
    re-enable ours on every run. Best-effort — needs `actions: write`."""
    ref = workflow_ref if workflow_ref is not None else os.environ.get("GITHUB_WORKFLOW_REF", "")
    match = re.search(r"/([^/@]+\.ya?ml)@", ref)
    if not match:
        return False
    resp = client.request(
        "PUT", f"/repos/{repo}/actions/workflows/{match.group(1)}/enable"
    )
    return resp.status_code == 204


def _contributors_total(client, repo):
    resp = client.request(
        "GET", f"/repos/{repo}/contributors", params={"per_page": 1, "anon": "1"}
    )
    if resp.status_code == 204:  # empty repository
        return 0
    if resp.status_code >= 400:
        raise GitHubError(f"GET /repos/{repo}/contributors -> HTTP {resp.status_code}")
    match = re.search(r'[?&]page=(\d+)>;\s*rel="last"', resp.headers.get("Link", ""))
    if match:
        return int(match.group(1))
    return len(resp.json())
