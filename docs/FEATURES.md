# reddit-mcp features

Living inventory of what ships here. One image, one process: a FastMCP server
on port 9111, streamable-HTTP at `/mcp`.

## Tools (all read-only)

- **get_frontpage** - the personalized front page of subscribed subs, from the
  `/reddit/frontpage-feed-url` feed.
- **get_upvoted** - upvoted posts as an interest signal, from the
  `/reddit/upvoted-feed-url` feed.
- **get_homepage_rss** - Reddit's public unpersonalized homepage Atom feed, with
  no credential or API app.
- **get_subreddit_rss** - newest posts from up to 50 caller-named subreddits,
  validated before the service builds a fixed-origin URL.

Each returns `{source, count, items}`. Private JSON items are the same
normalized t3 records `my.sources.reddit` produces. Public RSS items expose
stable Atom fields plus the upstream `content_html`, uninterpreted. The
subreddit tool also returns its normalized, deduplicated `subreddits` list.

## Security envelope

Read-only by construction, credentials never in the image, fixed-origin public
reads, hardened XML parsing, network-gated reach. See [security](security.md).

## Deploy

A plain outbound-HTTP reader with no host namespaces and no hostPath. Every
push to canonical `main` publishes and verifies the private image at a full
source SHA. Rollout lives in
[deploy](https://forgejo.coilysiren.me/coilyco-bridge/deploy), which consumes
the exact immutable reference with a read-only package credential.

## See also

- [../README.md](../README.md) - human-facing intro.
- [../AGENTS.md](../AGENTS.md) - agent operating context.
- [../.ward/ward.yaml](../.ward/ward.yaml) - allowlisted commands + catalog block.
- [features-release-tooling.md](features-release-tooling.md) - cross-reference style.
