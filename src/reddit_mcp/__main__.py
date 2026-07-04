"""Entrypoint so `python -m reddit_mcp` and the console script both run the server."""

from reddit_mcp.server import main

if __name__ == "__main__":
    main()
