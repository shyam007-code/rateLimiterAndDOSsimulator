"""Start the simulator backend locally.

Environment variables ``HOST`` (default 127.0.0.1) and ``PORT`` (default
8100) can be used to change the bind address. Keep this service on
localhost or a private test network: it issues real HTTP traffic to
whatever ``target_url`` a caller supplies.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """Run the Uvicorn server."""
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8100")),
    )


if __name__ == "__main__":
    main()
