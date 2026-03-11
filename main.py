from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parent
load_dotenv(REPO_ROOT / ".env")

SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from game.cli.app import run_cli  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Game Master AI entrypoint")
    parser.add_argument("--cli", action="store_true", help="Run the deterministic CLI engine")
    parser.add_argument("--live-llm", action="store_true", help="Run CLI with live LLM parser + narrator loop")
    parser.add_argument("--session-id", default=None, help="Resume or name the CLI session")
    parser.add_argument("--seed", type=int, default=5, help="Seed used for deterministic runtime setup")
    parser.add_argument("--data-dir", default="data", help="Path to game data directory")
    parser.add_argument("--schema-dir", default=None, help="Optional path to JSON schema directory")
    parser.add_argument("--debug", action="store_true", help="Print extra CLI debug output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cli:
        parser.print_help()
        return 1
    return run_cli(
        data_dir=args.data_dir,
        schema_dir=args.schema_dir,
        session_id=args.session_id,
        seed=args.seed,
        debug=args.debug,
        live_llm=args.live_llm,
    )


if __name__ == "__main__":
    raise SystemExit(main())