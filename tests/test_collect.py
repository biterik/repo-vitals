"""Collect stage against recorded API fixtures (no network)."""

import datetime as dt
import json

from conftest import FIXTURES

from repo_vitals.collect import API_ROOT, GitHubClient, collect_snapshot
from repo_vitals.schemas import validate_snapshot

REPO = "biterik/relevantr"
NOW = dt.datetime(2026, 7, 6, 3, 21, 14, tzinfo=dt.UTC)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {}
        self.text = text or (json.dumps(json_data) if json_data is not None else "")

    def json(self):
        return self._json


class FakeSession:
    """Routes (method, url) -> FakeResponse, list of them (consumed in order),
    or callable(params, json_body) -> FakeResponse. Records every call."""

    def __init__(self, routes):
        self.routes = dict(routes)
        self.calls = []

    def request(self, method, url, headers=None, params=None, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": headers,
                           "params": params, "json": json})
        route = self.routes.get((method, url))
        if route is None:
            return FakeResponse(404, {"message": "Not Found"})
        if isinstance(route, list):
            return route.pop(0) if len(route) > 1 else route[0]
        if callable(route):
            return route(params, json)
        return route


def fixture_response(name, **kwargs):
    return FakeResponse(200, json.loads((FIXTURES / name).read_text()), **kwargs)


def default_routes():
    def releases(params, _json_body):
        if params and params.get("page", 1) > 1:
            return FakeResponse(200, [])
        return fixture_response("releases.json")

    return {
        ("GET", f"{API_ROOT}/repos/{REPO}"): fixture_response("repo.json"),
        ("GET", f"{API_ROOT}/repos/{REPO}/traffic/views"): fixture_response("traffic_views.json"),
        ("GET", f"{API_ROOT}/repos/{REPO}/traffic/clones"): fixture_response("traffic_clones.json"),
        ("GET", f"{API_ROOT}/repos/{REPO}/traffic/popular/referrers"):
            fixture_response("traffic_referrers.json"),
        ("GET", f"{API_ROOT}/repos/{REPO}/traffic/popular/paths"):
            fixture_response("traffic_paths.json"),
        ("GET", f"{API_ROOT}/repos/{REPO}/releases"): releases,
        ("POST", f"{API_ROOT}/graphql"): fixture_response("graphql_activity.json"),
        ("GET", f"{API_ROOT}/repos/{REPO}/contributors"): FakeResponse(
            200,
            [{"login": "biterik"}],
            headers={"Link": f'<{API_ROOT}/repos/{REPO}/contributors'
                             '?per_page=1&anon=1&page=7>; rel="last"'},
        ),
    }


def make_client(routes, **kwargs):
    session = FakeSession(routes)
    return GitHubClient(token="gh-token", session=session, sleep=lambda s: None,
                        **kwargs), session


def test_full_collect_matches_fixtures():
    client, session = make_client(default_routes())
    snap = collect_snapshot(REPO, traffic_token="traffic-pat", client=client, now=NOW)

    assert validate_snapshot(snap) == []
    assert snap["date"] == "2026-07-06"
    assert snap["collected_at"] == "2026-07-06T03:21:14Z"
    assert snap["repo"] == REPO
    assert snap["errors"] == []

    assert snap["popularity"] == {"stars": 53, "forks": 12, "watchers": 53, "subscribers": 9}
    assert snap["traffic"]["views"]["2026-06-23"] == {"count": 91, "uniques": 40}
    # GitHub omits zero-traffic days; the collector must not invent them
    assert "2026-06-25" not in snap["traffic"]["views"]
    assert snap["traffic"]["clones"]["2026-06-30"] == {"count": 11, "uniques": 7}
    assert snap["traffic"]["referrers"][0]["referrer"] == "reddit.com"
    assert snap["traffic"]["paths"][0]["path"] == "/biterik/relevantr"

    assert [r["tag"] for r in snap["releases"]] == ["v1.3", "v1.2"]
    assert snap["releases"][0]["assets"][0]["downloads"] == 182

    assert snap["activity"] == {
        "commits_30d": 14,
        "prs_opened_30d": 3,
        "prs_merged_30d": 2,
        "issues_opened_30d": 5,
        "issues_closed_30d": 4,
        "contributors_total": 7,
    }
    assert snap["meta"]["fork"] is False
    assert snap["meta"]["open_issues"] == 4


def test_traffic_uses_traffic_token_and_rest_uses_default_token():
    client, session = make_client(default_routes())
    collect_snapshot(REPO, traffic_token="traffic-pat", client=client, now=NOW)

    for call in session.calls:
        auth = call["headers"]["Authorization"]
        if "/traffic/" in call["url"]:
            assert auth == "Bearer traffic-pat"
        else:
            assert auth == "Bearer gh-token"


def test_missing_traffic_token_skips_gracefully():
    client, _ = make_client(default_routes())
    snap = collect_snapshot(REPO, client=client, now=NOW)

    assert snap["traffic"] is None
    assert any(e["section"] == "traffic" and "token" in e["error"] for e in snap["errors"])
    # everything else still collected
    assert snap["popularity"]["stars"] == 53
    assert snap["activity"]["commits_30d"] == 14
    assert validate_snapshot(snap) == []


def test_partial_api_failure_never_aborts_the_run():
    routes = default_routes()
    routes[("GET", f"{API_ROOT}/repos/{REPO}/releases")] = FakeResponse(
        500, {"message": "boom"}
    )
    client, _ = make_client(routes, max_retries=0)
    snap = collect_snapshot(REPO, traffic_token="traffic-pat", client=client, now=NOW)

    assert snap["releases"] is None
    assert any(e["section"] == "releases" for e in snap["errors"])
    assert snap["popularity"]["stars"] == 53
    assert snap["traffic"]["views"]
    assert validate_snapshot(snap) == []


def test_rate_limit_retry_respects_retry_after():
    routes = default_routes()
    routes[("GET", f"{API_ROOT}/repos/{REPO}")] = [
        FakeResponse(403, {"message": "rate limited"}, headers={"Retry-After": "3"}),
        fixture_response("repo.json"),
    ]
    sleeps = []
    session = FakeSession(routes)
    client = GitHubClient(token="t", session=session, sleep=sleeps.append)
    snap = collect_snapshot(REPO, traffic_token="tt", client=client, now=NOW)

    assert 3 in sleeps
    assert snap["popularity"]["stars"] == 53


def test_empty_repo_contributors_204_means_zero():
    routes = default_routes()
    routes[("GET", f"{API_ROOT}/repos/{REPO}/contributors")] = FakeResponse(204)
    client, _ = make_client(routes)
    snap = collect_snapshot(REPO, traffic_token="tt", client=client, now=NOW)
    assert snap["activity"]["contributors_total"] == 0
