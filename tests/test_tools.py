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

import pytest


def _load(monkeypatch: pytest.MonkeyPatch, env: dict[str, str] | None = None) -> ModuleType:
    """Reimport the server module with a clean feed-URL env applied."""
    for _feed, (env_var, _ssm) in [
        ("frontpage", ("REDDIT_FRONTPAGE_FEED_URL", "")),
        ("inbox_unread", ("REDDIT_INBOX_UNREAD_FEED_URL", "")),
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

_INBOX_PAYLOAD = {
    "data": {
        "children": [
            {
                "kind": "t1",
                "data": {
                    "name": "t1_reply",
                    "author": "a",
                    "body": " hi ",
                    "context": "/r/x/comments/1/_/2/",
                    "new": True,
                },
            },
            {"kind": "t4", "data": {"name": "t4_msg", "author": "b", "subject": "hello"}},
            # A t3 must not leak into the inbox surface.
            {"kind": "t3", "data": {"name": "t3_nope"}},
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


def test_inbox_filters_to_t1_and_t4(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _load(monkeypatch, {"REDDIT_INBOX_UNREAD_FEED_URL": "https://feed/inbox"})
    monkeypatch.setattr(server, "_fetch_json", lambda url: _INBOX_PAYLOAD)
    got = server.get_inbox_unread()
    assert got["count"] == 2  # the t3 child is dropped
    kinds = {item["kind"] for item in got["items"]}
    assert kinds == {"comment_reply", "message"}


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
    assert names, "expected tools to be registered"
    # The action verb is the leading underscore-delimited token; every tool must
    # read (`get_`), never act. A write tool would lead with post/vote/submit/...
    forbidden_verbs = {"post", "vote", "comment", "reply", "submit", "delete", "send", "mark"}
    for n in names:
        verb = n.split("_", 1)[0]
        assert verb == "get", f"non-read tool {n!r} registered"
        assert verb not in forbidden_verbs
