"""
Unit tests for the Database Backup Service.
"""

from pathlib import Path
from src.naukri_agent.database.backup import DatabaseBackupService, backup_database


def test_database_backup_service(tmp_path):
    db_file = tmp_path / "test.db"
    db_file.write_text("dummy database content")

    backup_service = DatabaseBackupService(db_file, max_backups=2)
    backup_service.backup()

    backups = list(tmp_path.glob("test_backup_*.db"))
    assert len(backups) == 1

    # Create more backups to test pruning limit (max_backups = 2)
    import time

    time.sleep(1.1)
    backup_service.backup()
    time.sleep(1.1)
    backup_service.backup()
    backups = sorted(tmp_path.glob("test_backup_*.db"))
    assert len(backups) == 2


def test_backup_database_wrapper(tmp_path):
    db_file = tmp_path / "test_wrap.db"
    db_file.write_text("wrap dummy database")

    backup_database(db_file)
    backups = list(tmp_path.glob("test_wrap_backup_*.db"))
    assert len(backups) == 1
