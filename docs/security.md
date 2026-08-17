# Security envelope

**Read-only by construction.** A Reddit feed URL is a read token that cannot
post, vote, or comment (deploy#30). No write tool exists, and no tool both
ingests untrusted content and can act.

**Credentials never in the image.** Feed URLs resolve at runtime server-side,
env var first then SSM SecureString via `aws ssm get-parameter
--with-decryption`. They are never baked into the image, repo, or committed
config, and never logged or returned to callers. An unconfigured feed fails
loud with a `ValueError` rather than silently returning empty.

**Fixed-origin public reads.** Callers provide subreddit names, never URLs. The
names are validated before the service constructs an HTTPS URL under
`www.reddit.com`, which prevents arbitrary outbound fetches.

**Hardened XML parsing.** Public Atom feeds are parsed with `defusedxml`, and
untrusted HTML stays an uninterpreted string in `content_html`.

**Network-gated reach.** The endpoint sits behind the deploy's auth and network
overlay rather than anything in this source.

## Configuration

- `PORT` (default 9111), `HOST` (default 0.0.0.0)
- `REDDIT_FRONTPAGE_FEED_URL` or SSM `/reddit/frontpage-feed-url`
- `REDDIT_UPVOTED_FEED_URL` or SSM `/reddit/upvoted-feed-url`

Env is checked first and SSM is the fallback. The keys never leave the box.

## See also

- [FEATURES.md](FEATURES.md) - the capability inventory.
