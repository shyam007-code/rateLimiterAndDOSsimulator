"""Start the rate limiter backend locally.

Environment variables ``HOST`` (default 127.0.0.1) and ``PORT`` (default 8000)
can be used to change the bind address.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """Run the Uvicorn server."""
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
