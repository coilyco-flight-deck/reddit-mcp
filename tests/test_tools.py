"""Behavioural tests for the reddit-mcp tools.

The tools are registered with FastMCP without rebinding their names, so the
plain callables stay directly invokable here. The focus mirrors node-stats-mcp's:
the read-only + credential-custody envelope. A feed URL is resolved env-first
then SSM, an unconfigured feed fails loud, the normalization is faithful to the
routine surface, and there is no write tool.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from unittest.mock import Mock

import pytest
import requests


def _load(monkeypatch: pytest.MonkeyPatch, env: dict[str, str] | None = None) -> ModuleType:
    """Reimport the server module with a clean feed-URL env applied."""
    for _feed, (env_var, _ssm) in [
        ("frontpage", ("REDDIT_FRONTPAGE_FEED_URL", "")),
        ("upvoted", ("REDDIT_UPVOTED_FEED_URL", "")),
    ]:
        monkeypatch.delenv(env_var, raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    import reddit_mcp.server as server

    return importlib.reload(server)


_FRONTPAGE_PAYLOAD = {
    "data": {
        "children": [
            {
                "kind": "t3",
                "data": {
                    "name": "t3_abc",
                    "subreddit": "python",
                    "author": "someone",
                    "title": "  A post  ",
                    "url": "https://example.com",
                    "permalink": "/r/python/comments/abc/a_post/",
                    "score": 42,
                    "num_comments": 7,
                    "created_utc": 1_700_000_000,
                    "is_self": False,
                    "over_18": False,
                    "domain": "example.com",
                },
            },
            # A non-t3 child (e.g. an ad/listing header) must be dropped.
            {"kind": "t1", "data": {"name": "t1_nope"}},
        ]
    }
}


def test_frontpage_normalizes(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _load(monkeypatch, {"REDDIT_FRONTPAGE_FEED_URL": "https://feed/frontpage"})
    monkeypatch.setattr(server, "_fetch_json", lambda url: _FRONTPAGE_PAYLOAD)
    got = server.get_frontpage()
    assert got["source"] == "frontpage"
    assert got["count"] == 1  # the t1 child is dropped
    post = got["items"][0]
    assert post["id"] == "t3_abc"
    assert post["title"] == "A post"  # stripped
    assert post["permalink"] == "https://www.reddit.com/r/python/comments/abc/a_post/"
    assert post["score"] == 42


def test_valid_empty_listing_stays_successful(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _load(monkeypatch, {"REDDIT_FRONTPAGE_FEED_URL": "https://feed/frontpage"})
    monkeypatch.setattr(server, "_fetch_json", lambda url: {"data": {"children": []}})

    assert server.get_frontpage() == {"source": "frontpage", "count": 0, "items": []}


def test_http_failure_is_redacted(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    server = _load(monkeypatch)
    secret_url = "https://feed.invalid/listing?token=secret"
    secret_body = "upstream echoed token=secret"
    response = Mock(ok=False, status_code=403, text=secret_body)
    monkeypatch.setattr(server.requests, "get", lambda *args, **kwargs: response)

    with pytest.raises(server.RedditFeedError, match=r"^Reddit feed returned HTTP 403$") as raised:
        server._fetch_json(secret_url)

    rendered = f"{raised.value} {caplog.text}"
    assert secret_url not in rendered
    assert secret_body not in rendered
    response.json.assert_not_called()


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (requests.Timeout("https://feed.invalid/?token=secret"), "Reddit feed request timed out"),
        (
            requests.ConnectionError("https://feed.invalid/?token=secret"),
            "Reddit feed request failed",
        ),
    ],
)
def test_network_failure_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: requests.RequestException,
    message: str,
) -> None:
    server = _load(monkeypatch)
    monkeypatch.setattr(server.requests, "get", Mock(side_effect=error))

    with pytest.raises(server.RedditFeedError, match=rf"^{message}$") as raised:
        server._fetch_json("https://feed.invalid/?token=secret")

    rendered = f"{raised.value} {caplog.text}"
    assert "feed.invalid" not in rendered
    assert "token=secret" not in rendered


def test_invalid_json_is_redacted(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    server = _load(monkeypatch)
    secret_url = "https://feed.invalid/listing?token=secret"
    secret_body = "not json token=secret"
    response = Mock(ok=True, status_code=200)
    response.json.side_effect = requests.exceptions.JSONDecodeError("invalid", secret_body, 0)
    monkeypatch.setattr(server.requests, "get", lambda *args, **kwargs: response)

    with pytest.raises(
        server.RedditFeedError, match=r"^Reddit feed returned invalid JSON$"
    ) as raised:
        server._fetch_json(secret_url)

    rendered = f"{raised.value} {caplog.text}"
    assert secret_url not in rendered
    assert secret_body not in rendered


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"data": None},
        {"data": {}},
        {"data": {"children": {}}},
        {"data": {"children": [None]}},
    ],
)
def test_invalid_listing_shape_fails(payload: object, monkeypatch: pytest.MonkeyPatch) -> None:
    server = _load(monkeypatch, {"REDDIT_UPVOTED_FEED_URL": "https://feed/upvoted"})
    monkeypatch.setattr(server, "_fetch_json", lambda url: payload)

    with pytest.raises(server.RedditFeedError, match=r"^Reddit feed returned an invalid listing$"):
        server.get_upvoted()


def test_unconfigured_feed_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _load(monkeypatch)  # no env
    monkeypatch.setattr(server, "_ssm", lambda name: None)  # no SSM either
    with pytest.raises(ValueError, match="not configured"):
        server.get_upvoted()


def test_env_takes_precedence_over_ssm(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _load(monkeypatch, {"REDDIT_UPVOTED_FEED_URL": "https://env/upvoted"})
    # If SSM were consulted it would raise; env must win and be used verbatim.
    monkeypatch.setattr(server, "_ssm", lambda name: pytest.fail("SSM must not be read"))
    seen: dict[str, str] = {}

    def _capture(url: str) -> dict:
        seen["url"] = url
        return {"data": {"children": []}}

    monkeypatch.setattr(server, "_fetch_json", _capture)
    server.get_upvoted()
    assert seen["url"] == "https://env/upvoted"


def test_no_write_tools_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """The read-only invariant: every registered tool reads, none can act."""
    server = _load(monkeypatch)
    names = [t.name for t in server.mcp._tool_manager.list_tools()]
    assert set(names) == {"get_frontpage", "get_upvoted"}
    # The action verb is the leading underscore-delimited token; every tool must
    # read (`get_`), never act. A write tool would lead with post/vote/submit/...
    forbidden_verbs = {"post", "vote", "comment", "reply", "submit", "delete", "send", "mark"}
    for n in names:
        verb = n.split("_", 1)[0]
        assert verb == "get", f"non-read tool {n!r} registered"
        assert verb not in forbidden_verbs


def test_mcp_transport_avoids_pod_local_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _load(monkeypatch)

    assert server.mcp.settings.stateless_http is True
