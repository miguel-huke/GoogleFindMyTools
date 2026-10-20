#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import argparse
import os

from MapApp.server import run_map_app
from MapApp.presentation.http import HttpExposurePolicy


def _environment_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _environment_list(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def _environment_mode() -> str:
    mode = os.environ.get("GFMT_MODE", "real").strip().lower()
    if mode not in {"demo", "real"}:
        raise ValueError("GFMT_MODE must be either 'demo' or 'real'")
    return mode


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="GoogleFindMyTools local map")
    parser.add_argument("--host", default=os.environ.get("GFMT_BIND_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=int(os.environ.get("GFMT_PORT", "8765")), type=int)
    parser.add_argument(
        "--database",
        default=os.environ.get("GFMT_DATABASE_PATH"),
        help="SQLite path (defaults to the current user's local application data)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        default=_environment_mode() == "demo",
        help="use synthetic device reports without Google authentication",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="start the server without opening the default browser",
    )
    parser.add_argument(
        "--allow-non-loopback",
        action="store_true",
        default=_environment_flag("GFMT_ALLOW_NON_LOOPBACK"),
        help="allow container bind only with explicit trusted hosts and origins",
    )
    parser.add_argument(
        "--trusted-host",
        action="append",
        default=_environment_list("GFMT_TRUSTED_HOSTS"),
        help="exact trusted Host authority; may be repeated",
    )
    parser.add_argument(
        "--trusted-origin",
        action="append",
        default=_environment_list("GFMT_TRUSTED_ORIGINS"),
        help="exact trusted HTTP(S) Origin; may be repeated",
    )
    return parser.parse_args(argv)


if __name__ == '__main__':
    args = parse_args()
    exposure_policy = HttpExposurePolicy(
        allow_non_loopback_bind=args.allow_non_loopback,
        trusted_hosts=tuple(args.trusted_host),
        trusted_origins=tuple(args.trusted_origin),
    )
    run_map_app(
        host=args.host,
        port=args.port,
        demo=args.demo,
        open_browser=not args.no_browser,
        database_path=args.database,
        exposure_policy=exposure_policy,
    )
