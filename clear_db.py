import os
import shutil
from pathlib import Path


def clear_data_and_cache():
    project_root = Path(__file__).resolve().parent

    # 1. Databases and associated files
    db_dirs = [project_root / "data", project_root / "src" / "data"]
    for db_dir in db_dirs:
        if db_dir.exists():
            for p in db_dir.glob("*.db*"):
                try:
                    os.remove(p)
                    print(f"Deleted database/backup file: {p.relative_to(project_root)}")
                except Exception as e:
                    print(f"Error deleting {p}: {e}")

    # 2. JSON/cache files under data/ and src/data/
    cache_files = [
        project_root / "data" / "qa_cache.json",
        project_root / "data" / "match_cache.json",
        project_root / "data" / "logs" / ".alert_cooldowns.json",
        project_root / "data" / "logs" / "metrics.json",
        project_root / ".coverage",
        project_root / "coverage.xml",
    ]
    for cache_file in cache_files:
        if cache_file.exists():
            try:
                os.remove(cache_file)
                print(f"Deleted cache file: {cache_file.relative_to(project_root)}")
            except Exception as e:
                print(f"Error deleting {cache_file}: {e}")

    # 3. Sessions directories
    session_dirs = [
        project_root / "data" / "sessions",
        project_root / "src" / "data" / "sessions",
    ]
    for s_dir in session_dirs:
        if s_dir.exists():
            for p in s_dir.glob("*.json*"):
                try:
                    os.remove(p)
                    print(f"Deleted session file: {p.relative_to(project_root)}")
                except Exception as e:
                    print(f"Error deleting {p}: {e}")

    # 4. Cache directories (.pytest_cache, .ruff_cache, .mypy_cache, __pycache__)
    cache_dirs = [".pytest_cache", ".ruff_cache", ".mypy_cache"]
    for c_dir_name in cache_dirs:
        c_dir = project_root / c_dir_name
        if c_dir.exists():
            try:
                shutil.rmtree(c_dir)
                print(f"Deleted cache directory: {c_dir_name}")
            except Exception as e:
                print(f"Error deleting cache directory {c_dir_name}: {e}")

    # 5. Remove __pycache__ directories recursively
    for root, dirs, files in os.walk(project_root):
        if "__pycache__" in dirs:
            pycache_path = Path(root) / "__pycache__"
            try:
                shutil.rmtree(pycache_path)
                print(f"Deleted: {pycache_path.relative_to(project_root)}")
            except Exception as e:
                print(f"Error deleting pycache {pycache_path}: {e}")


if __name__ == "__main__":
    clear_data_and_cache()

