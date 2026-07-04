import os
import sqlite3
import hashlib
import ast
from pathlib import Path
import logging

# Set up a basic logger for the module if not integrating fully into external logger
logger = logging.getLogger(__name__)

# Default directories to ignore
DEFAULT_IGNORE_DIRS = {
    ".git",
    ".vscode",
    ".idea",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "venv",
    ".venv",
    "env",
    "data",
    "node_modules",
    "debug_artifacts",
    "implementation_plans",
}

# Default file extensions to include
DEFAULT_INCLUDE_EXTS = {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt"}


class SymbolVisitor(ast.NodeVisitor):
    """Extracts classes and function names using AST."""

    def __init__(self):
        self.symbols = []

    def visit_ClassDef(self, node):
        self.symbols.append(f"class {node.name}")
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.symbols.append(f"def {node.name}")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.symbols.append(f"async def {node.name}")
        self.generic_visit(node)


class ProjectIndexer:
    """Incremental Project Indexing and Context Caching System."""

    def __init__(self, project_root: str, db_path: str = "data/project_index.db"):
        self.project_root = Path(project_root).resolve()

        # Resolve db_path relative to project_root if it is not absolute
        db_path_obj = Path(db_path)
        if not db_path_obj.is_absolute():
            self.db_path = self.project_root / db_path_obj
        else:
            self.db_path = db_path_obj

        # Ensure DB directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """Initializes the SQLite cache schema."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS file_cache (
                filepath TEXT PRIMARY KEY,
                mtime REAL,
                sha256 TEXT,
                symbols TEXT,
                content TEXT
            )
        """
        )
        self.conn.commit()

    def _get_sha256(self, filepath: Path) -> str:
        """Computes the SHA-256 hash of a file."""
        sha256_hash = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"Error hashing {filepath}: {e}")
            return ""

    def _extract_symbols(self, filepath: Path, content: str) -> str:
        """Extracts symbols if it's a Python file."""
        if filepath.suffix != ".py":
            return ""
        try:
            tree = ast.parse(content, filename=str(filepath))
            visitor = SymbolVisitor()
            visitor.visit(tree)
            return "\n".join(visitor.symbols)
        except SyntaxError:
            logger.debug(f"Syntax error while parsing {filepath}")
            return ""
        except Exception as e:
            logger.debug(f"Failed to extract symbols from {filepath}: {e}")
            return ""

    def index_project(self) -> dict:
        """
        Scans the project incrementally and updates the cache.
        Returns a dictionary with statistics.
        """
        stats = {"added": 0, "updated": 0, "unchanged": 0, "deleted": 0}
        cursor = self.conn.cursor()

        # Fetch existing files in DB to detect deletions
        cursor.execute("SELECT filepath, mtime, sha256 FROM file_cache")
        existing_files = {row["filepath"]: dict(row) for row in cursor.fetchall()}
        current_files = set()

        logger.info(f"Starting incremental index of {self.project_root}...")

        for root, dirs, files in os.walk(self.project_root):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS and not d.startswith(".")]

            for file in files:
                filepath = Path(root) / file

                # Check extensions
                if filepath.suffix not in DEFAULT_INCLUDE_EXTS:
                    continue

                # Ignore the DB itself
                if file in {self.db_path.name, self.db_path.name + "-journal"}:
                    continue

                rel_path = filepath.relative_to(self.project_root).as_posix()
                current_files.add(rel_path)

                try:
                    mtime = filepath.stat().st_mtime
                except FileNotFoundError:
                    continue

                cached = existing_files.get(rel_path)

                # Fast path: check mtime first
                if cached and cached["mtime"] == mtime:
                    stats["unchanged"] += 1
                    continue

                # Slower path: check SHA-256 if mtime differs (or new file)
                current_sha = self._get_sha256(filepath)
                if cached and cached["sha256"] == current_sha:
                    # Update mtime so we don't hash next time
                    cursor.execute(
                        "UPDATE file_cache SET mtime = ? WHERE filepath = ?", (mtime, rel_path)
                    )
                    stats["unchanged"] += 1
                    continue

                # File has actually changed or is new
                try:
                    with open(filepath, encoding="utf-8") as f:
                        content = f.read()
                except UnicodeDecodeError:
                    logger.debug(f"Skipping binary/non-UTF8 file: {rel_path}")
                    continue

                symbols = self._extract_symbols(filepath, content)

                cursor.execute(
                    """
                    INSERT INTO file_cache (filepath, mtime, sha256, symbols, content)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(filepath) DO UPDATE SET
                        mtime=excluded.mtime,
                        sha256=excluded.sha256,
                        symbols=excluded.symbols,
                        content=excluded.content
                    """,
                    (rel_path, mtime, current_sha, symbols, content),
                )

                if cached:
                    stats["updated"] += 1
                else:
                    stats["added"] += 1

        # Handle deletions
        deleted_files = set(existing_files.keys()) - current_files
        for df in deleted_files:
            cursor.execute("DELETE FROM file_cache WHERE filepath = ?", (df,))
            stats["deleted"] += 1

        self.conn.commit()
        logger.info(f"Indexing complete: {stats}")
        return stats

    def generate_context(self) -> str:
        """
        Generates a consolidated Markdown string from the cache,
        suitable for feeding into an AI's context window.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT filepath, symbols, content FROM file_cache ORDER BY filepath")
        rows = cursor.fetchall()

        context_parts = []
        context_parts.append("# Project Context")
        context_parts.append("This is an automatically generated index of the codebase.\n")

        # 1. Project Structure
        context_parts.append("## Project Structure")
        context_parts.append("```")
        for row in rows:
            context_parts.append(f"- {row['filepath']}")
        context_parts.append("```\n")

        # 2. File Contents & Symbols
        context_parts.append("## File Details")
        for row in rows:
            filepath = row["filepath"]
            symbols = row["symbols"]
            content = row["content"]

            context_parts.append(f"### File: `{filepath}`")
            if symbols:
                context_parts.append(f"**Key Symbols:**\n```python\n{symbols}\n```")

            context_parts.append(f"**Content:**\n```{self._get_lang(filepath)}\n{content}\n```\n")

        return "\n".join(context_parts)

    def _get_lang(self, filepath: str) -> str:
        """Helper to get markdown language identifier from extension."""
        ext = filepath.split(".")[-1] if "." in filepath else ""
        lang_map = {
            "py": "python",
            "md": "markdown",
            "json": "json",
            "yaml": "yaml",
            "yml": "yaml",
            "toml": "toml",
            "txt": "text",
        }
        return lang_map.get(ext, "")

    def close(self):
        self.conn.close()
