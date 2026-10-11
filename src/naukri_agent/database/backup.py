"""
Database backup utilities for the Naukri Agent.

Ensures data integrity by backing up the SQLite database before each run.
Retains the last 5 backups to prevent excessive disk usage.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseBackupService:
    """
    Manages SQLite database backups and retention limits.
    """

    def __init__(self, db_path: Path, max_backups: int = 5) -> None:
        self.db_path = db_path
        self.max_backups = max_backups

    def backup(self) -> Path | None:
        """Create a backup of the SQLite database if it exists and prune old backups."""
        if not self.db_path.exists():
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_name = f"{self.db_path.stem}_backup_{timestamp}{self.db_path.suffix}"
            backup_path = self.db_path.parent / backup_name

            # SQLite's online backup API includes committed WAL pages.
            with sqlite3.connect(f"{self.db_path.resolve().as_uri()}?mode=ro", uri=True) as source:
                with sqlite3.connect(backup_path) as target:
                    source.backup(target)
            logger.info(f"Database backed up to {backup_name}")

            # Cleanup old backups (keep last self.max_backups)
            backups = sorted(
                self.db_path.parent.glob(f"{self.db_path.stem}_backup_*{self.db_path.suffix}")
            )
            if len(backups) > self.max_backups:
                for old_backup in backups[: -self.max_backups]:
                    old_backup.unlink()
                    logger.debug(f"Deleted old backup: {old_backup.name}")

            return backup_path

        except Exception as e:
            logger.error(f"Failed to backup database: {e}")
            raise


def backup_database(db_path: Path) -> None:
    """Convenience wrapper that creates a DatabaseBackupService and runs a backup."""
    DatabaseBackupService(db_path).backup()
