# Incremental Project Indexing and Context Caching System

This document outlines the design and implementation plan for a production-ready, incremental project indexing system tailored for AI context generation during "vibe coding".

## Architecture Analysis
I analyzed the current codebase (`Naukri.com AI Agent`) and found that **there is currently no built-in project scanning mechanism** for AI coding context. The existing AI integrations (Gemini) are strictly used for business logic (resume parsing, job matching) rather than self-referential codebase indexing. 

Therefore, this will be a **new, standalone module** added to your workspace that you can use to rapidly generate and update project context for Gemini 3.1 Pro (or any other model) without rescanning the entire repository every time.

## Proposed Design

To meet the requirements (thread-safe, persistent, incremental, and memory-efficient), I propose an **SQLite-backed caching system**. SQLite natively provides thread safety, ACID compliance, and persistence across IDE restarts.

### Core Components
1. **File System Scanner & Hasher**: 
   - Uses `os.walk` to traverse the repository, ignoring files based on `.gitignore` and common cache directories.
   - Computes SHA-256 hashes and modification timestamps (mtime) for change detection.
2. **Context Extractor**: 
   - Extracts project structure (tree).
   - Extracts symbols (classes, functions) using Python's built-in `ast` module.
   - Parses dependencies from `requirements.txt` and `pyproject.toml`.
3. **SQLite Cache Manager (`ProjectCache`)**: 
   - Stores file paths, hashes, extracted symbols, and full text context.
   - Automatically identifies added, modified, renamed, or deleted files.
4. **Context Generator**:
   - Assembles the cached components into an optimized markdown prompt for Gemini.

### Open Questions
> [!WARNING]
> Please review these questions before I proceed with the implementation:
> 1. **Embeddings:** Do you want to actually call the Gemini API to compute vector embeddings for semantic search, or is generating a smart, compressed Markdown context file (with symbols and modified file contents) sufficient for your vibe coding workflow? (I will implement the structural caching first, with a placeholder/extensible method for vector embeddings).
> 2. **Location:** I plan to put the core logic in `src/naukri_agent/utils/project_indexer.py` and a CLI script in `scripts/vibe_context.py`. Does this sound good?

## Proposed Changes

### [NEW] `src/naukri_agent/utils/project_indexer.py`
This will contain the core engine:
- `ProjectCache`: SQLite database wrapper managing the `files`, `symbols`, and `dependencies` tables.
- `FileScanner`: Logic to walk directories, respect ignore patterns, and compute SHA-256 hashes.
- `SymbolExtractor`: AST-based parser to extract class and function definitions.
- `ContextBuilder`: Assembles the final AI context from the SQLite cache.

### [NEW] `scripts/vibe_context.py`
A CLI tool that you can run before or during your vibe coding sessions:
- Flags: `--update` (to run the incremental sync), `--export <file>` (to dump the context), `--watch` (to run a continuous background watcher using `watchdog`).
- Initializes the SQLite DB (e.g., in `data/project_index.db` to survive restarts).

## Verification Plan
### Automated Verification
- I will create a basic test script to index the project, modify a dummy file, and re-run the indexer to assert that *only* the modified file is processed.
- Verify that SQLite cache sizes remain small and lookups are fast.

### Manual Verification
- You can run `python scripts/vibe_context.py --update` and check the console output to see how many files were skipped vs. scanned.
