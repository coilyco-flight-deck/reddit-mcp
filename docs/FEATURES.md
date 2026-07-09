# reddit-mcp features

Living inventory of what ships from this repo. One image, one process: a FastMCP server on port 9111, streamable-HTTP endpoint at `/mcp`.

## Tools (all read-only)

- **get_frontpage** - Kai's personalized reddit front page (subscribed subs), from the `/reddit/frontpage-feed-url` feed. Mirrors daily-educational.
- **get_upvoted** - posts Kai has upvoted (interest signal), from the `/reddit/upvoted-feed-url` feed. Mirrors daily-educational.
- **get_inbox_unread** - unread comment replies (t1) and private messages (t4), from the `/reddit/inbox-unread-feed-url` feed. Mirrors daily-social. Fetching does not mark anything read.

Each returns `{source, count, items}`; `items` are the same normalized records `my.sources.reddit` produces (t3 posts flattened for the listing feeds, t1/t4 items for the inbox).

## Security envelope

- **Read-only by construction** - a Reddit feed URL is a read token that cannot post, vote, or comment (deploy#30). No write tool exists, and no tool both ingests untrusted content and can act.
- **Credentials never in the image** - feed URLs resolve at runtime, server-side: env var first, then SSM SecureString via `aws ssm get-parameter --with-decryption`. Never baked into the image, repo, or committed config; never logged or returned to callers. An unconfigured feed fails loud (`ValueError`) rather than silently returning empty.
- **Network-gated reach** - the endpoint sits behind the deploy's auth/network overlay (Authelia/Traefik, added in the deploy repo), not in this source.

## Configuration (env)

- `PORT` (default 9111), `HOST` (default 0.0.0.0).
- `REDDIT_FRONTPAGE_FEED_URL` / SSM `/reddit/frontpage-feed-url`.
- `REDDIT_INBOX_UNREAD_FEED_URL` / SSM `/reddit/inbox-unread-feed-url`.
- `REDDIT_UPVOTED_FEED_URL` / SSM `/reddit/upvoted-feed-url`.

Env is checked first; SSM is the fallback. The keys never leave the box.

## Deploy

Plain outbound-HTTP reader (no host namespaces, no hostPath). Image published to the in-cluster registry (`192.168.0.194:30500/reddit-mcp:<sha>`) by [`.forgejo/workflows/build-publish.yml`](../.forgejo/workflows/build-publish.yml). Rollout lives in [coilyco-bridge/deploy](https://forgejo.coilysiren.me/coilyco-bridge/deploy) and is out of scope for this repo.

## See also

- [../README.md](../README.md) - human-facing intro.
- [../AGENTS.md](../AGENTS.md) - agent operating context.
- [../.ward/ward.yaml](../.ward/ward.yaml) - allowlisted commands + catalog block.
- [features-release-tooling.md](features-release-tooling.md) - durable cross-reference style for this repo.
