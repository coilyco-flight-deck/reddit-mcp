"""Behavioural tests for the reddit-mcp tools.

The tools are registered with FastMCP without rebinding their names, so the
plain callables stay directly invokable here. The focus mirrors node-stats-mcp's
read-only + credential-custody envelope. Private feed URLs resolve env-first
then SSM, public RSS URLs stay pinned to reddit.com, normalization is faithful
to each upstream format, and there is no write tool.
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

_RSS_PAYLOAD = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>reddit.com</title>
  <entry>
    <author><name>/u/someone</name></author>
    <category term="python" label="r/python"/>
    <content type="html">&lt;p&gt;A summary&lt;/p&gt;</content>
    <id>t3_rss</id>
    <link href="https://www.reddit.com/r/python/comments/rss/a_post/"/>
    <published>2026-07-24T10:00:00+00:00</published>
    <updated>2026-07-24T10:05:00+00:00</updated>
    <title>A post from RSS</title>
  </entry>
</feed>
"""


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


def test_homepage_rss_normalizes(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _load(monkeypatch)
    response = Mock(ok=True, status_code=200, content=_RSS_PAYLOAD)
    get = Mock(return_value=response)
    monkeypatch.setattr(server.requests, "get", get)

    got = server.get_homepage_rss()

    assert got["source"] == "homepage_rss"
    assert got["count"] == 1
    assert got["items"][0] == {
        "dedup_key": "t3_rss",
        "id": "t3_rss",
        "subreddit": "python",
        "author": "someone",
        "title": "A post from RSS",
        "url": "https://www.reddit.com/r/python/comments/rss/a_post/",
        "permalink": "https://www.reddit.com/r/python/comments/rss/a_post/",
        "published": "2026-07-24T10:00:00+00:00",
        "updated": "2026-07-24T10:05:00+00:00",
        "content_html": "<p>A summary</p>",
    }
    assert get.call_args.args[0] == f"{server.REDDIT_ORIGIN}/.rss"


def test_subreddit_rss_builds_fixed_origin_new_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _load(monkeypatch)
    seen: dict[str, str] = {}

    def _capture(url: str) -> object:
        seen["url"] = url
        return server.SafeElementTree.fromstring(_RSS_PAYLOAD)

    monkeypatch.setattr(server, "_fetch_atom", _capture)

    got = server.get_subreddit_rss(["r/Python", "/r/golang", "python"])

    assert got["subreddits"] == ["python", "golang"]
    assert got["count"] == 1
    assert seen["url"] == f"{server.REDDIT_ORIGIN}/r/python+golang/new/.rss?sort=new"


@pytest.mark.parametrize("subreddits", [[], ["python/../../elsewhere"], ["https://example.com"]])
def test_subreddit_rss_rejects_unsafe_names(
    subreddits: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    server = _load(monkeypatch)
    monkeypatch.setattr(server, "_fetch_atom", Mock())

    with pytest.raises(ValueError):
        server.get_subreddit_rss(subreddits)

    server._fetch_atom.assert_not_called()


def test_subreddit_rss_caps_request_size(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _load(monkeypatch)
    monkeypatch.setattr(server, "_fetch_atom", Mock())
    subreddits = [f"subreddit_{index}" for index in range(server.MAX_SUBREDDITS + 1)]

    with pytest.raises(ValueError, match="may be requested"):
        server.get_subreddit_rss(subreddits)

    server._fetch_atom.assert_not_called()


def test_invalid_rss_is_redacted(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    server = _load(monkeypatch)
    secret_url = "https://feed.invalid/listing?token=secret"
    response = Mock(ok=True, status_code=200, content=b"<not-closed>")
    monkeypatch.setattr(server.requests, "get", Mock(return_value=response))

    with pytest.raises(
        server.RedditFeedError, match=r"^Reddit RSS returned invalid XML$"
    ) as raised:
        server._fetch_atom(secret_url)

    rendered = f"{raised.value} {caplog.text}"
    assert secret_url not in rendered
    assert "token=secret" not in rendered


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
    # If SSM were consulted it would raise. Env must win and be used verbatim.
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
    assert set(names) == {
        "get_frontpage",
        "get_upvoted",
        "get_homepage_rss",
        "get_subreddit_rss",
    }
    # The action verb is the leading underscore-delimited token. Every tool must
    # read (`get_`), never act. A write tool would lead with post/vote/submit/...
    forbidden_verbs = {"post", "vote", "comment", "reply", "submit", "delete", "send", "mark"}
    for n in names:
        verb = n.split("_", 1)[0]
        assert verb == "get", f"non-read tool {n!r} registered"
        assert verb not in forbidden_verbs


def test_mcp_transport_avoids_pod_local_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _load(monkeypatch)

    assert server.mcp.settings.stateless_http is True
