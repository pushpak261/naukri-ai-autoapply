"""
Database backup utilities for the Naukri Agent.

Ensures data integrity by backing up the SQLite database before each run.
Retains the last 5 backups to prevent excessive disk usage.
"""

import shutil
from datetime import datetime
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


def backup_database(db_path: Path) -> None:
    """Create a backup of the SQLite database if it exists."""
    if not db_path.exists():
        return

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{db_path.stem}_backup_{timestamp}{db_path.suffix}"
        backup_path = db_path.parent / backup_name

        shutil.copy2(db_path, backup_path)
        logger.info(f"Database backed up to {backup_name}")

        # Cleanup old backups (keep last 5)
        backups = sorted(db_path.parent.glob(f"{db_path.stem}_backup_*{db_path.suffix}"))
        if len(backups) > 5:
            for old_backup in backups[:-5]:
                old_backup.unlink()
                logger.debug(f"Deleted old backup: {old_backup.name}")

    except Exception as e:
        logger.error(f"Failed to backup database: {e}")
