"""FastMCP server republishing read-only Reddit feeds over streamable-HTTP.

Read-only by construction. The private JSON tools return the same normalized
records the `daily-educational` cron routine already produces (the normalization
here is ported verbatim from `agentic-os-kai` `my.sources.reddit`, so the tool
surface stays faithful to the audited routine surface):

- get_frontpage      - personalized front page (subscribed subs)      [daily-educational]
- get_upvoted        - posts the user has upvoted (interest signal)    [daily-educational]

The public RSS tools need no credential and add no Reddit API app:

- get_homepage_rss   - Reddit's public homepage Atom feed
- get_subreddit_rss  - newest posts from caller-selected subreddits

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

import base64
import os
import re
import subprocess
from importlib.resources import files
from typing import Any
from xml.etree import ElementTree as StdlibElementTree

import requests
from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException
from mcp.server.fastmcp import FastMCP
from mcp.types import Icon

# Matches my.sources.reddit so the feeds see the same client Kai's routines use.
USER_AGENT = "daily-routines/1.0 (by /u/coilysiren)"
TIMEOUT = 20
REDDIT_ORIGIN = "https://www.reddit.com"
MAX_SUBREDDITS = 50
ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"
ATOM = {"atom": ATOM_NAMESPACE}
SUBREDDIT_NAME = re.compile(r"^[A-Za-z0-9_]+$")

# Each feed: (env var checked first, SSM SecureString parameter checked second).
# The SSM parameter names are taken verbatim from my.sources.reddit - do not
# re-derive them. Env wins so the deploy can inject via an ExternalSecret without
# granting the pod ssm:GetParameter, matching node-stats' env-based config.
FEEDS = {
    "frontpage": ("REDDIT_FRONTPAGE_FEED_URL", "/reddit/frontpage-feed-url"),
    "upvoted": ("REDDIT_UPVOTED_FEED_URL", "/reddit/upvoted-feed-url"),
}


def _reddit_icon() -> Icon:
    """The Reddit brand mark, embedded as a self-contained data-URI icon.

    Wired into the server's `initialize` response (`serverInfo.icons`) so clients
    that render server icons - the claude.ai / ChatGPT connector tile - show the
    Snoo mark instead of a generic placeholder. Same shape as steam-ops'
    `_steam_icon`: the asset is committed at `assets/reddit-icon.png` (official
    Snoo-on-orange mark, palette-compressed under 10KB for the ChatGPT icon cap)
    and read here at import time, base64'd into a `data:` URI rather than served
    over HTTP so the icon has no external dependency and rides inside the
    initialize payload itself.
    """
    png = files("reddit_mcp.assets").joinpath("reddit-icon.png").read_bytes()
    encoded = base64.b64encode(png).decode("ascii")
    return Icon.model_validate(
        {
            "src": f"data:image/png;base64,{encoded}",
            "mimeType": "image/png",
            "sizes": ["256x256"],
        }
    )


mcp = FastMCP(
    "reddit",
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "9111")),
    # The deploy runs multiple replicas. Pod-local MCP sessions break as soon
    # as the Service sends a later request to a different replica.
    stateless_http=True,
    icons=[_reddit_icon()],
)


class RedditFeedError(RuntimeError):
    """Safe caller-facing failure with feed credentials redacted."""


def _ssm(name: str) -> str | None:
    """Fetch a decrypted SSM parameter value. None if unavailable.

    Ported from my.sources.reddit._ssm - the feed URLs are SecureString params
    read server-side at call time. They are never logged or returned to callers.
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


def _fetch_atom(url: str) -> StdlibElementTree.Element:
    """GET and safely parse a public Reddit Atom feed."""
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    except requests.Timeout:
        raise RedditFeedError("Reddit RSS request timed out") from None
    except requests.RequestException:
        raise RedditFeedError("Reddit RSS request failed") from None

    if not response.ok:
        raise RedditFeedError(f"Reddit RSS returned HTTP {response.status_code}")

    try:
        root = SafeElementTree.fromstring(response.content)
    except (StdlibElementTree.ParseError, DefusedXmlException):
        raise RedditFeedError("Reddit RSS returned invalid XML") from None

    if root.tag != f"{{{ATOM_NAMESPACE}}}feed":
        raise RedditFeedError("Reddit RSS returned an invalid Atom feed")
    return root


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


def _atom_text(entry: StdlibElementTree.Element, path: str) -> str:
    element = entry.find(path, ATOM)
    return (element.text or "").strip() if element is not None else ""


def _atom_permalink(entry: StdlibElementTree.Element) -> str:
    for link in entry.findall("atom:link", ATOM):
        if link.get("rel", "alternate") == "alternate" and link.get("href"):
            return link.get("href", "")
    return ""


def _atom_subreddit(entry: StdlibElementTree.Element) -> str:
    category = entry.find("atom:category", ATOM)
    if category is None:
        return ""
    value = (category.get("term") or category.get("label") or "").strip()
    return value.removeprefix("/r/").removeprefix("r/")


def _normalize_atom_entry(entry: StdlibElementTree.Element) -> dict[str, str]:
    """Flatten a Reddit Atom entry without interpreting its untrusted HTML."""
    entry_id = _atom_text(entry, "atom:id")
    permalink = _atom_permalink(entry)
    return {
        "dedup_key": entry_id or permalink,
        "id": entry_id,
        "subreddit": _atom_subreddit(entry),
        "author": _atom_text(entry, "atom:author/atom:name").removeprefix("/u/"),
        "title": _atom_text(entry, "atom:title"),
        "url": permalink,
        "permalink": permalink,
        "published": _atom_text(entry, "atom:published"),
        "updated": _atom_text(entry, "atom:updated"),
        "content_html": _atom_text(entry, "atom:content"),
    }


def _rss(source: str, url: str) -> dict[str, Any]:
    root = _fetch_atom(url)
    items = [_normalize_atom_entry(entry) for entry in root.findall("atom:entry", ATOM)]
    return {"source": source, "count": len(items), "items": items}


def _subreddit_names(subreddits: list[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for raw_name in subreddits:
        name = raw_name.strip().removeprefix("/r/").removeprefix("r/").lower()
        if not name or not SUBREDDIT_NAME.fullmatch(name):
            raise ValueError("subreddits must contain only Reddit community names")
        if name not in seen:
            names.append(name)
            seen.add(name)

    if not names:
        raise ValueError("at least one subreddit is required")
    if len(names) > MAX_SUBREDDITS:
        raise ValueError(f"at most {MAX_SUBREDDITS} subreddits may be requested")
    return names


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


def get_homepage_rss() -> dict[str, Any]:
    """Reddit's public homepage Atom feed.

    This feed is public and unpersonalized. Use get_frontpage for Kai's private
    subscribed-community home feed. Read-only.
    """
    return _rss("homepage_rss", f"{REDDIT_ORIGIN}/.rss")


def get_subreddit_rss(subreddits: list[str]) -> dict[str, Any]:
    """Newest posts from one or more caller-selected subreddits.

    Names may be plain (``python``) or prefixed (``r/python``). The service
    validates them before constructing a fixed-origin reddit.com Atom URL, so a
    caller cannot turn the reader into an arbitrary URL fetcher. Read-only.
    """
    names = _subreddit_names(subreddits)
    joined = "+".join(names)
    result = _rss("subreddit_rss", f"{REDDIT_ORIGIN}/r/{joined}/new/.rss?sort=new")
    result["subreddits"] = names
    return result


# Register each tool without rebinding its name, so the plain callables stay
# directly invokable. Tests call them, and the mcp SDK's decorator return type has
# varied across versions, so we don't rely on it). Every registered tool is a
# read - keep it that way (no post, no vote, no comment).
for _tool in (
    get_frontpage,
    get_upvoted,
    get_homepage_rss,
    get_subreddit_rss,
):
    mcp.tool()(_tool)


def main() -> None:
    """Run the MCP server over streamable-HTTP (endpoint served at /mcp)."""
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
