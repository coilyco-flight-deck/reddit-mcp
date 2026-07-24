"""FastMCP server republishing Kai's private Reddit feeds over streamable-HTTP.

Read-only by construction. Each tool fetches one private Reddit JSON feed URL and
returns the same normalized records the `daily-educational` cron routine already
produces (the normalization here is ported verbatim from
`agentic-os-kai` `my.sources.reddit`, so the tool surface stays faithful to the
audited routine surface):

- get_frontpage      - personalized front page (subscribed subs)      [daily-educational]
- get_upvoted        - posts the user has upvoted (interest signal)    [daily-educational]

A feed URL is a read token minted by Reddit's `/prefs/feeds/` page for the
logged-in user - it cannot post, vote, or comment (deploy#30). There is
deliberately **no write tool** and no path that both ingests untrusted content
and can act: this service reads, full stop.

Credential custody: the feed URLs are private and never live in the image, the
repo, or a committed config. Each is resolved at runtime, server-side, from an
env var first and then from SSM (`aws ssm get-parameter --with-decryption`),
mirroring `my.sources.reddit._ssm` and the mcporter `ssm-load` pattern. The keys
never leave the box - only the fetched (already public-to-Kai) reddit records do.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

# Matches my.sources.reddit so the feeds see the same client Kai's routines use.
USER_AGENT = "daily-routines/1.0 (by /u/coilysiren)"
TIMEOUT = 20

# Each feed: (env var checked first, SSM SecureString parameter checked second).
# The SSM parameter names are taken verbatim from my.sources.reddit - do not
# re-derive them. Env wins so the deploy can inject via an ExternalSecret without
# granting the pod ssm:GetParameter, matching node-stats' env-based config.
FEEDS = {
    "frontpage": ("REDDIT_FRONTPAGE_FEED_URL", "/reddit/frontpage-feed-url"),
    "upvoted": ("REDDIT_UPVOTED_FEED_URL", "/reddit/upvoted-feed-url"),
}

mcp = FastMCP(
    "reddit",
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "9111")),
    # The deploy runs multiple replicas. Pod-local MCP sessions break as soon
    # as the Service sends a later request to a different replica.
    stateless_http=True,
)


class RedditFeedError(RuntimeError):
    """Safe caller-facing failure with feed credentials redacted."""


def _ssm(name: str) -> str | None:
    """Fetch a decrypted SSM parameter value. None if unavailable.

    Ported from my.sources.reddit._ssm - the feed URLs are SecureString params
    read server-side at call time; they are never logged or returned to callers.
    """
    try:
        proc = subprocess.run(
            [
                "aws",
                "ssm",
                "get-parameter",
                "--name",
                name,
                "--with-decryption",
                "--query",
                "Parameter.Value",
                "--output",
                "text",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.stdout.strip() if proc.returncode == 0 else None
    except Exception:
        return None


def _feed_url(feed: str) -> str:
    """Resolve a feed's private URL: env var first, then SSM.

    Raises ValueError (surfaced to the caller as a tool error) when neither
    source has the URL, so an unconfigured deploy fails loud instead of silently
    returning an empty feed.
    """
    env_var, ssm_name = FEEDS[feed]
    url = os.environ.get(env_var) or _ssm(ssm_name)
    if not url:
        raise ValueError(f"feed {feed!r} is not configured (set {env_var} or SSM {ssm_name})")
    return url


def _fetch_json(url: str) -> object:
    """GET a reddit JSON feed. Read-only: this is the only network call, a plain
    outbound GET a feed URL cannot turn into a write."""
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    except requests.Timeout:
        raise RedditFeedError("Reddit feed request timed out") from None
    except requests.RequestException:
        raise RedditFeedError("Reddit feed request failed") from None

    if not response.ok:
        raise RedditFeedError(f"Reddit feed returned HTTP {response.status_code}")

    try:
        return response.json()
    except requests.exceptions.JSONDecodeError:
        raise RedditFeedError("Reddit feed returned invalid JSON") from None


def _children(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        raise RedditFeedError("Reddit feed returned an invalid listing")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RedditFeedError("Reddit feed returned an invalid listing")
    children = data.get("children")
    if not isinstance(children, list) or not all(isinstance(child, dict) for child in children):
        raise RedditFeedError("Reddit feed returned an invalid listing")
    return children


def _normalize_post(child: dict) -> dict[str, Any]:
    """Flatten a t3 link/post into a stable record (ported from my.sources.reddit)."""
    d = child.get("data") or {}
    name = d.get("name") or ""
    permalink = d.get("permalink") or ""
    return {
        "dedup_key": name,
        "id": name,
        "subreddit": d.get("subreddit") or "",
        "author": d.get("author") or "",
        "title": (d.get("title") or "").strip(),
        "url": d.get("url") or "",
        "permalink": f"https://www.reddit.com{permalink}" if permalink else "",
        "score": d.get("score") or 0,
        "num_comments": d.get("num_comments") or 0,
        "created_utc": d.get("created_utc") or 0,
        "is_self": bool(d.get("is_self")),
        "selftext": (d.get("selftext") or "").strip(),
        "over_18": bool(d.get("over_18")),
        "domain": d.get("domain") or "",
    }


def _posts(feed: str) -> dict[str, Any]:
    """Fetch a link-listing feed and return its normalized t3 posts."""
    payload = _fetch_json(_feed_url(feed))
    items = [_normalize_post(c) for c in _children(payload) if (c.get("kind") or "") == "t3"]
    return {"source": feed, "count": len(items), "items": items}


def get_frontpage() -> dict[str, Any]:
    """Kai's personalized reddit front page (subscribed subs), newest first.

    Reads the private `/reddit/frontpage-feed-url` feed. Mirrors what
    daily-educational pulls. Read-only.
    """
    return _posts("frontpage")


def get_upvoted() -> dict[str, Any]:
    """Posts Kai has upvoted - an interest signal, not a feed of new content.

    Reads the private `/reddit/upvoted-feed-url` feed. Mirrors what
    daily-educational pulls. Read-only.
    """
    return _posts("upvoted")


# Register each tool without rebinding its name, so the plain callables stay
# directly invokable (tests call them; the mcp SDK's decorator return type has
# varied across versions, so we don't rely on it). Every registered tool is a
# read - keep it that way (no post, no vote, no comment).
for _tool in (
    get_frontpage,
    get_upvoted,
):
    mcp.tool()(_tool)


def main() -> None:
    """Run the MCP server over streamable-HTTP (endpoint served at /mcp)."""
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
