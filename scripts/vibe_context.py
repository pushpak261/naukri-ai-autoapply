#!/usr/bin/env python3
"""
Vibe Context Generator

This script runs the incremental project indexer and generates a markdown
context file that can be fed into Gemini (or other AI models) during
"vibe coding" sessions.

Usage:
  python scripts/vibe_context.py --update
  python scripts/vibe_context.py --export context.md
"""

import argparse
import sys
import logging
import time
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False


# Add project root to path so we can import src
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.naukri_agent.utils.project_indexer import ProjectIndexer  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


if HAS_WATCHDOG:

    class IndexerEventHandler(FileSystemEventHandler):
        def __init__(self, indexer):
            self.indexer = indexer
            self.last_update = 0
            self.debounce_seconds = 1.0

        def on_any_event(self, event):
            if event.is_directory:
                return

            # Simple debounce to prevent rapid sequential updates
            current_time = time.time()
            if current_time - self.last_update > self.debounce_seconds:
                logger.info(
                    f"File change detected ({event.src_path}), running incremental update..."
                )
                stats = self.indexer.index_project()
                print(f"Update Summary: {stats}")
                self.last_update = time.time()


def main():
    parser = argparse.ArgumentParser(description="Incremental Project Indexer for AI Context")
    parser.add_argument(
        "--update", action="store_true", help="Run the incremental indexer to update the cache"
    )
    parser.add_argument(
        "--export", type=str, metavar="FILE", help="Export the cached context to a markdown file"
    )
    parser.add_argument(
        "--db-path", type=str, default="data/project_index.db", help="Path to the SQLite cache DB"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run in background and watch for file changes to automatically update",
    )

    args = parser.parse_args()

    if not args.update and not args.export and not args.watch:
        parser.print_help()
        sys.exit(1)

    indexer = ProjectIndexer(project_root=str(project_root), db_path=args.db_path)

    try:
        if args.update:
            logger.info("Running incremental update...")
            stats = indexer.index_project()
            print(f"\nUpdate Summary: {stats}")

        if args.export:
            logger.info(f"Generating context and exporting to {args.export}...")
            context = indexer.generate_context()

            export_path = Path(args.export)
            if not export_path.is_absolute():
                export_path = project_root / export_path

            with open(export_path, "w", encoding="utf-8") as f:
                f.write(context)
            print(f"\nContext successfully written to: {export_path}")

        if args.watch:
            if not HAS_WATCHDOG:
                logger.error(
                    "The 'watchdog' library is not installed. Please run: pip install watchdog"
                )
                sys.exit(1)

            logger.info("Starting initial index before watching...")
            stats = indexer.index_project()
            print(f"Initial Update Summary: {stats}")

            event_handler = IndexerEventHandler(indexer)
            observer = Observer()
            observer.schedule(event_handler, str(project_root), recursive=True)
            observer.start()
            logger.info(f"Watching for file changes in {project_root}...")

            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Stopping watcher...")
                observer.stop()
            observer.join()

    finally:
        indexer.close()


if __name__ == "__main__":
    main()
