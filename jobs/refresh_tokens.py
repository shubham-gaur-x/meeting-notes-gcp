#!/usr/bin/env python3
"""Cloud Run Job entrypoint — verify the OAuth refresh token still works.

Scheduled every 6 hours. Exits non-zero on a dead token so the failure shows
up as a failed job rather than a quiet log line nobody reads.

Thin by design (CLAUDE.md): all logic lives in meeting_notes/token_health.py.
"""

import asyncio

from meeting_notes import token_health


def main() -> int:
    health = asyncio.run(token_health.check())
    print(token_health.render(health))
    return 0 if health.healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
