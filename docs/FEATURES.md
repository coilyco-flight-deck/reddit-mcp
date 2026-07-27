# reddit-mcp features

Living inventory of what ships from this repo. One image, one process: a FastMCP server on port 9111, streamable-HTTP endpoint at `/mcp`.

## Tools (all read-only)

- **get_frontpage** - Kai's personalized reddit front page (subscribed subs), from the `/reddit/frontpage-feed-url` feed. Mirrors daily-educational.
- **get_upvoted** - posts Kai has upvoted (interest signal), from the `/reddit/upvoted-feed-url` feed. Mirrors daily-educational.
- **get_homepage_rss** - Reddit's public, unpersonalized homepage Atom feed. No credential or Reddit API app.
- **get_subreddit_rss** - newest posts from up to 50 caller-selected subreddit names. Names are validated before the service constructs a fixed-origin `reddit.com` Atom URL.

Each returns `{source, count, items}`. The private JSON items are the same normalized t3 post records `my.sources.reddit` produces. Public RSS items expose stable Atom fields plus the upstream `content_html` without interpreting it. The subreddit tool also returns its normalized, deduplicated `subreddits` list.

## Security envelope

- **Read-only by construction** - a Reddit feed URL is a read token that cannot post, vote, or comment (deploy#30). No write tool exists, and no tool both ingests untrusted content and can act.
- **Credentials never in the image** - feed URLs resolve at runtime, server-side: env var first, then SSM SecureString via `aws ssm get-parameter --with-decryption`. Never baked into the image, repo, or committed config. Never logged or returned to callers. An unconfigured feed fails loud (`ValueError`) rather than silently returning empty.
- **Fixed-origin public reads** - callers provide subreddit names, never URLs. Names are validated before the service constructs an HTTPS URL under `www.reddit.com`, preventing arbitrary outbound fetches.
- **Hardened XML parsing** - public Atom feeds are parsed with `defusedxml`. Untrusted HTML remains an uninterpreted string in `content_html`.
- **Network-gated reach** - the endpoint sits behind the deploy's auth/network overlay (Authelia/Traefik, added in the deploy repo), not in this source.

## Configuration (env)

- `PORT` (default 9111), `HOST` (default 0.0.0.0).
- `REDDIT_FRONTPAGE_FEED_URL` / SSM `/reddit/frontpage-feed-url`.
- `REDDIT_UPVOTED_FEED_URL` / SSM `/reddit/upvoted-feed-url`.

Env is checked first. SSM is the fallback. The keys never leave the box.

## Deploy

Plain outbound-HTTP reader (no host namespaces, no hostPath). Every push to
canonical `main` publishes and verifies the private single-architecture image
as
`forgejo.coilysiren.me/coilyco-flight-deck/reddit-mcp:<full-source-sha>`.
[The source workflow](../.forgejo/workflows/build-publish.yml) owns publishing.
Rollout lives in
[coilyco-bridge/deploy](https://forgejo.coilysiren.me/coilyco-bridge/deploy),
which consumes the exact immutable reference with a read-only package
credential.

## See also

- [../README.md](../README.md) - human-facing intro.
- [../AGENTS.md](../AGENTS.md) - agent operating context.
- [../.ward/ward.yaml](../.ward/ward.yaml) - allowlisted commands + catalog block.
- [features-release-tooling.md](features-release-tooling.md) - durable cross-reference style for this repo.
