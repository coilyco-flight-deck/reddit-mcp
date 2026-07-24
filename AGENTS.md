# Agent instructions

Workspace conventions load globally via `~/.claude/CLAUDE.md`. This file covers only what is specific to this repo.

## Scope

A single tiny Python service: a FastMCP server (`src/reddit_mcp/server.py`) that republishes Kai's two private Reddit JSON feeds - front page and upvoted - as read-only MCP tools over streamable-HTTP.

## Project shape

No frontend, no database. `src/reddit_mcp/` holds the server and its entrypoint; `tests/` covers the tool logic, the credential-resolution order, and the read-only envelope. One image, one process.

## Repo boundaries

The deploy surface (namespace, Ingress, Authelia client, values.env) lives in [coilyco-bridge/deploy](https://forgejo.coilysiren.me/coilyco-bridge/deploy), not here (source -> deploy layer invariant). This repo builds and publishes the image; the deploy repo rolls it. The normalization logic is ported from `agentic-os-kai` `my.sources.reddit` - that routine remains the source of truth for feed shapes and SSM parameter names; keep this port faithful to it.

## Commands

Route every command through ward, never bare `make` / `uv` / `pytest`. Verbs are declared in [`.ward/ward.yaml`](.ward/ward.yaml); run them as `ward <verb>`.

## Validation

`ward lint` (ruff + ruff-format + mypy) and `ward test` (pytest). `ward precommit` runs the full pre-commit suite, including the agentic-os catalog hooks. Validate before pushing.

## Safety

- **Every tool is read-only.** Never add a tool that posts, votes, comments, marks-read, or otherwise mutates Reddit. A feed URL cannot write; keep it that way at the tool layer too. Mutation is out of scope for this MCP by design (deploy#30).
- **No ingest-and-act path.** A tool must never both fetch untrusted feed content and take an action on it. This service only reads and returns.
- **Feed URLs are secrets.** They resolve from env then SSM at runtime, server-side, and must never be baked into the image, the repo, or a committed config. Never log a feed URL or return it to a caller. `trufflehog` runs at commit time as the backstop, but the discipline is upstream of the hook.

## Cross-repo contracts

The image is published to the in-cluster registry (`192.168.0.194:30500/reddit-mcp:<sha>`) by [`.forgejo/workflows/build-publish.yml`](.forgejo/workflows/build-publish.yml) on every push to main. The deploy repo's rollout resolves that image by sha. Keep the dependency surface tiny (mcp + requests); a new dependency needs a reason.

## Release

Push to main; CI builds and publishes the image. There is no version bump or tag ceremony. Deferred cleanup gets a Forgejo issue, never a silent skip.

## Agent rules

Name the actor in action sentences.

## See also

- [README.md](README.md) - human-facing intro.
- [docs/FEATURES.md](docs/FEATURES.md) - inventory of what ships today.
- [.ward/ward.yaml](.ward/ward.yaml) - allowlisted commands + catalog block.
- [docs/features-release-tooling.md](docs/features-release-tooling.md) - durable cross-reference style for this repo.
