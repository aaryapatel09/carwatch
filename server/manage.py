"""Administrative CLI. Invitation codes are secrets: share them privately."""

import argparse
import os

from server.database import invite

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["invite"])
    parser.add_argument(
        "--db", default=os.environ.get("CARWATCH_API_DB", "runtime/api/carwatch.sqlite3")
    )
    args = parser.parse_args()
    print(invite(args.db))
