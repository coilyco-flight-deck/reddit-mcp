# Single-stage: this is a tiny requests + FastMCP service, no frontend, no build
# step. uv installs the pinned deps into the system env, then the console script
# runs the streamable-HTTP server. Mirrors node-stats-mcp's registry flow (in-
# cluster registry, plain build), minus the psutil/host machinery.
#
# The image ships zero credentials: the private feed URLs are resolved at runtime
# from env/SSM (see src/reddit_mcp/server.py), never baked in here.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# The aws CLI is the SSM fallback path when the deploy injects no feed-URL env.
RUN pip install --no-cache-dir awscli

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src /app/src

# Install the project (and its deps) into the system environment. No lockfile:
# the dependency surface is two libraries, so a resolved install is enough.
RUN uv pip install --system --no-cache .

ENV PORT=9111
EXPOSE 9111

CMD ["reddit-mcp"]
