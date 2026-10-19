#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import argparse

from MapApp.server import run_map_app


def parse_args():
    parser = argparse.ArgumentParser(description="GoogleFindMyTools local map")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument(
        "--database",
        default=None,
        help="SQLite path (defaults to the current user's local application data)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use synthetic device reports without Google authentication",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="start the server without opening the default browser",
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    run_map_app(
        host=args.host,
        port=args.port,
        demo=args.demo,
        open_browser=not args.no_browser,
        database_path=args.database,
    )
