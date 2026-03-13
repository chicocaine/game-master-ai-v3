#!/usr/bin/env python3
"""
Launcher script for the Gradio UI version of Game Master AI.

Usage:
    python run_gradio.py [--live-llm] [--debug] [--port 7860] [--seed 5]

Examples:
    python run_gradio.py                    # Run with default settings
    python run_gradio.py --live-llm         # Enable LLM narrator and converse
    python run_gradio.py --debug --port 8000  # Debug mode on port 8000
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add src to path for imports
REPO_ROOT = Path(__file__).resolve().parent
load_dotenv(REPO_ROOT / ".env")

sys.path.insert(0, str(REPO_ROOT / "src"))

from ui.gradio_app import launch_gradio_ui


def main():
    parser = argparse.ArgumentParser(
        description="Launch the Gradio UI for Game Master AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Path to data directory (default: data)",
    )
    parser.add_argument(
        "--persistence-dir",
        type=str,
        default="logs/checkpoints",
        help="Path to persistence directory (default: logs/checkpoints)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Session ID to load (optional; generates new ID if not provided)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=5,
        help="Random seed for reproducibility (default: 5)",
    )
    parser.add_argument(
        "--live-llm",
        action="store_true",
        help="Enable live LLM features (narrator, converse responder)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (verbose logging)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Server port (default: 7860)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Server host/bind address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Create a public sharing link (useful for remote access)",
    )

    args = parser.parse_args()

    print(f"""
╔════════════════════════════════════════════════════════════════╗
║           Game Master AI - Gradio UI Launcher                  ║
╚════════════════════════════════════════════════════════════════╝

Configuration:
  Data Directory:     {args.data_dir}
  Persistence Dir:    {args.persistence_dir}
  Session ID:         {args.session_id or '(auto-generated)'}
  Random Seed:        {args.seed}
  Live LLM:           {'✓ Enabled' if args.live_llm else '✗ Disabled'}
  Debug Mode:         {'✓ Enabled' if args.debug else '✗ Disabled'}
  Server:             {args.host}:{args.port}
  Public Share:       {'✓ Yes' if args.share else '✗ No'}

Launching...
""")

    try:
        launch_gradio_ui(
            data_dir=args.data_dir,
            persistence_dir=args.persistence_dir,
            session_id=args.session_id,
            seed=args.seed,
            live_llm=args.live_llm,
            debug=args.debug,
            server_name=args.host,
            server_port=args.port,
            share=args.share,
        )
    except KeyboardInterrupt:
        print("\n\n✓ Gradio UI terminated.")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error launching Gradio UI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
