"""reddit-mcp: read-only MCP republishing Kai's reddit reads over streamable-HTTP.

The first pure-read clone of the personal-MCP fleet. It wraps the same private
Reddit JSON feeds the `daily-social` and `daily-educational` cron routines
already read - front page, inbox-unread, and upvoted - and serves them as MCP
tools.

Read-only by construction: a private Reddit feed URL is a read token (a feed URL
cannot write), which is the whole point - it sidesteps the 2026 Responsible
Builder Policy API-app gate with no Reddit API app. There is no write tool here,
and no path that both ingests untrusted content and can act.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
