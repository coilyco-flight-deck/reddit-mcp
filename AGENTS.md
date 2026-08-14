---
ward:
  workflow: merge-remote-main
---
# Agent instructions

Workspace conventions load globally via `~/.claude/CLAUDE.md`. This file covers only what is specific to this repo.

## Scope

A single tiny Python service: a FastMCP server (`src/reddit_mcp/server.py`) that republishes Kai's two private Reddit JSON feeds plus public homepage and caller-selected subreddit Atom feeds as read-only MCP tools over streamable-HTTP.

## Project shape

No frontend, no database. `src/reddit_mcp/` holds the server and its entrypoint. `tests/` covers the tool logic, credential-resolution order, fixed-origin public URL construction, hardened Atom parsing, and the read-only envelope. One image, one process.

## Repo boundaries

The deploy surface (namespace, Ingress, Authelia client, values.env) lives in [coilyco-bridge/deploy](https://forgejo.coilysiren.me/coilyco-bridge/deploy), not here (source -> deploy layer invariant). This repo builds and publishes the image. The deploy repo rolls it. The private JSON normalization logic is ported from `agentic-os-kai` `my.sources.reddit` - that routine remains the source of truth for private feed shapes and SSM parameter names. Keep this port faithful to it. Public RSS is a separate Atom surface and must never weaken the fixed-origin read-only boundary.

## Commands

Route every command through Ward, never bare `uv` / `pytest`. Verbs are declared in [`.ward/ward.yaml`](.ward/ward.yaml). Run them as `ward exec <verb>`.

## Validation

`ward exec lint` (ruff + ruff-format + mypy) and `ward exec test` (pytest). `ward exec precommit` runs the full pre-commit suite, including the agentic-os catalog hooks. Validate before pushing.

## Safety

- **Every tool is read-only.** Never add a tool that posts, votes, comments, marks-read, or otherwise mutates Reddit. A feed URL cannot write. Keep it that way at the tool layer too. Mutation is out of scope for this MCP by design (deploy#30).
- **No ingest-and-act path.** A tool must never both fetch untrusted feed content and take an action on it. This service only reads and returns.
- **Feed URLs are secrets.** They resolve from env then SSM at runtime, server-side, and must never be baked into the image, the repo, or a committed config. Never log a feed URL or return it to a caller. `trufflehog` runs at commit time as the backstop, but the discipline is upstream of the hook.

## Cross-repo contracts

The private single-architecture image is published as
`forgejo.coilysiren.me/coilyco-flight-deck/reddit-mcp:<full-source-sha>` by
[`.forgejo/workflows/build-publish.yml`](.forgejo/workflows/build-publish.yml)
on every push to main. The trusted `deploy` runner receives the registry write
token, and the publisher verifies the immutable remote manifest before it
succeeds. The deploy repo receives that exact reference and rolls it with a
read-only package credential. Keep the dependency surface tiny. `defusedxml`
exists only because public Atom is untrusted XML. Any other new dependency
needs a reason.

## Release

Push to main. CI tests, publishes one source-SHA image to Forgejo OCI, and
verifies the remote manifest. There is no version bump or tag ceremony.
Deferred cleanup gets a Forgejo issue, never a silent skip.

## Agent rules

Name the actor in action sentences.

## Checkout residency

This repo is not in Agent Compose's `repository-plan.yaml`, so it has no
resident checkout under `~/projects/<owner>/`. That is intentional. Work it
from a task-scoped temporary clone, and remove that clone once the work lands.

A temporary root can be purged at any time, so commit and push before pausing,
switching tasks, or ending a session. The remote is the only durable artifact.

## See also

- [README.md](README.md) - human-facing intro.
- [docs/FEATURES.md](docs/FEATURES.md) - inventory of what ships today.
- [.ward/ward.yaml](.ward/ward.yaml) - allowlisted commands + catalog block.
- [docs/features-release-tooling.md](docs/features-release-tooling.md) - durable cross-reference style for this repo.
