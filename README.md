# reddit-mcp

A read-only MCP that republishes Kai's existing Reddit reads and public Reddit RSS as MCP tools over streamable-HTTP. An agent (or the claude.ai hosted connector) can see the private front page, upvoted posts, the public homepage, and caller-selected subreddits without a Reddit API app.

The private tools wrap the exact Reddit JSON feeds the `daily-educational` cron routine already reads (`agentic-os-kai` `my.sources.reddit`). The public tools parse Reddit's Atom feeds with hardened XML handling and construct only fixed-origin `reddit.com` URLs. This is the first pure-read clone of the [coilyco-bridge/deploy](https://forgejo.coilysiren.me/coilyco-bridge/deploy) personal-MCP fleet, and it mirrors the shared personal-MCP rollout pattern.

## Read-only by construction

A private Reddit feed URL is a read token minted by Reddit's `/prefs/feeds/` page for the logged-in user - **a feed URL cannot post, vote, or comment.** That is the whole point: it deliberately sidesteps the 2026 Responsible Builder Policy API-app gate (no Reddit API app). There is no write tool here, and no path that both ingests untrusted content and can act. This service reads, full stop.

Unlike [node-stats-mcp](https://forgejo.coilysiren.me/coilyco-flight-deck/node-stats-mcp) (the shape this repo is patterned on), reddit-mcp is a **plain outbound-HTTP reader**: no `hostPID`, `hostNetwork`, `hostPath`, `ROOTFS`, or readable-roots. It fetches only private feed URLs supplied by the operator or public feeds constructed under `https://www.reddit.com`.

## Tools

- **get_frontpage** - Kai's private, personalized home feed.
- **get_upvoted** - posts Kai has upvoted.
- **get_homepage_rss** - Reddit's public, unpersonalized homepage Atom feed.
- **get_subreddit_rss** - newest posts from up to 50 caller-selected subreddit names. Names may be written as `python`, `r/python`, or `/r/python`.

The subreddit list is supplied by the caller instead of being embedded in this service. That keeps Kai's evolving curation at the operator layer while the source remains reusable.

## Credential custody

The private feed URLs are equivalent to passwords and **never** live in the image, the repo, or a committed config. Each is resolved at runtime, server-side:

1. an env var (`REDDIT_FRONTPAGE_FEED_URL`, `REDDIT_UPVOTED_FEED_URL`), then
2. SSM SecureString (`/reddit/frontpage-feed-url`, `/reddit/upvoted-feed-url`) via `aws ssm get-parameter --with-decryption`.

Env-first lets the deploy inject the URLs via an ExternalSecret without granting the pod `ssm:GetParameter` (node-stats' env-based config), while the SSM fallback mirrors `my.sources.reddit` and the mcporter `ssm-load` pattern. The keys never leave the box - only the fetched reddit records do.

## Port

Streamable-HTTP on `PORT` (default **9111**), `HOST` (default `0.0.0.0`), endpoint at `/mcp`. The transport is stateless so requests can move safely between deploy replicas. node-stats holds `9110`. reddit-mcp takes the next free kai-server port, `9111`.

## Run it locally

```sh
ward exec sync
# feed URLs come from env (or SSM if the box has aws creds):
REDDIT_FRONTPAGE_FEED_URL='https://www.reddit.com/.json?feed=...&user=...' \
  ward exec run     # streamable-HTTP MCP on :9111, endpoint at /mcp
```

## Commands

Dev commands are declared in [`.ward/ward.yaml`](.ward/ward.yaml). Run them as `ward exec <verb>`.

## Image publishing

Every push to canonical `main` publishes the private single-architecture image
as
`forgejo.coilysiren.me/coilyco-flight-deck/reddit-mcp:<full-source-sha>`.
The trusted deploy runner owns the write credential and verifies the remote
manifest before the workflow succeeds. The deploy repo consumes the exact
immutable reference with a separate read-only credential.

## No auth here

Auth is **not** in this source. The Authelia/Traefik public overlay is layered on in the deploy repo, not here (deploy#28 principle: the MCP source stays unchanged by the overlay). This repo just serves the reads over HTTP. Reach is gated at the network / deploy layer.

## See also

- [AGENTS.md](AGENTS.md) - agent operating context for this repo.
- [docs/FEATURES.md](docs/FEATURES.md) - inventory of what ships today.
- [.ward/ward.yaml](.ward/ward.yaml) - allowlisted commands + catalog block.
- [coilyco-flight-deck/node-stats-mcp](https://forgejo.coilysiren.me/coilyco-flight-deck/node-stats-mcp) - the source pattern this repo mirrors.
- [docs/features-release-tooling.md](docs/features-release-tooling.md) - durable cross-reference style for this repo.
