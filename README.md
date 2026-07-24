# reddit-mcp

A read-only MCP that republishes Kai's existing reddit reads as MCP tools over streamable-HTTP, so an agent (or the claude.ai hosted connector) can see the reddit front page, unread inbox, and upvoted posts without a Reddit API app.

It wraps the exact private Reddit JSON feeds the `daily-social` and `daily-educational` cron routines already read (`agentic-os-kai` `my.sources.reddit`). This is the first pure-read clone of the [coilyco-bridge/deploy](https://forgejo.coilysiren.me/coilyco-bridge/deploy) personal-MCP fleet, and it mirrors the inbox-backed rollout plan.

## Read-only by construction

A private Reddit feed URL is a read token minted by Reddit's `/prefs/feeds/` page for the logged-in user - **a feed URL cannot post, vote, or comment.** That is the whole point: it deliberately sidesteps the 2026 Responsible Builder Policy API-app gate (no Reddit API app). There is no write tool here, and no path that both ingests untrusted content and can act. This service reads, full stop.

Unlike [node-stats-mcp](https://forgejo.coilysiren.me/coilyco-flight-deck/node-stats-mcp) (the shape this repo is patterned on), reddit-mcp is a **plain outbound-HTTP reader**: no `hostPID`, `hostNetwork`, `hostPath`, `ROOTFS`, or readable-roots. It is a dumb backend that fetches three URLs.

## Credential custody

The feed URLs are private (equivalent to passwords) and **never** live in the image, the repo, or a committed config. Each is resolved at runtime, server-side:

1. an env var (`REDDIT_FRONTPAGE_FEED_URL`, `REDDIT_INBOX_UNREAD_FEED_URL`, `REDDIT_UPVOTED_FEED_URL`), then
2. SSM SecureString (`/reddit/frontpage-feed-url`, `/reddit/inbox-unread-feed-url`, `/reddit/upvoted-feed-url`) via `aws ssm get-parameter --with-decryption`.

Env-first lets the deploy inject the URLs via an ExternalSecret without granting the pod `ssm:GetParameter` (node-stats' env-based config), while the SSM fallback mirrors `my.sources.reddit` and the mcporter `ssm-load` pattern. The keys never leave the box - only the fetched reddit records do.

## Port

Streamable-HTTP on `PORT` (default **9111**), `HOST` (default `0.0.0.0`), endpoint at `/mcp`. The transport is stateless so requests can move safely between deploy replicas. node-stats holds `9110`; reddit-mcp takes the next free kai-server port, `9111`.

## Run it locally

```sh
ward sync
# feed URLs come from env (or SSM if the box has aws creds):
REDDIT_FRONTPAGE_FEED_URL='https://www.reddit.com/.rss?feed=...&user=...' \
  ward run     # streamable-HTTP MCP on :9111, endpoint at /mcp
```

## Commands

Dev commands are declared in [`.ward/ward.yaml`](.ward/ward.yaml). Run them as `ward <verb>`.

## No auth here

Auth is **not** in this source. The Authelia/Traefik public overlay is layered on in the deploy repo, not here (deploy#28 principle: the MCP source stays unchanged by the overlay). This repo just serves the reads over HTTP; reach is gated at the network / deploy layer.

## See also

- [AGENTS.md](AGENTS.md) - agent operating context for this repo.
- [docs/FEATURES.md](docs/FEATURES.md) - inventory of what ships today.
- [.ward/ward.yaml](.ward/ward.yaml) - allowlisted commands + catalog block.
- [coilyco-flight-deck/node-stats-mcp](https://forgejo.coilysiren.me/coilyco-flight-deck/node-stats-mcp) - the source pattern this repo mirrors.
- [docs/features-release-tooling.md](docs/features-release-tooling.md) - durable cross-reference style for this repo.
