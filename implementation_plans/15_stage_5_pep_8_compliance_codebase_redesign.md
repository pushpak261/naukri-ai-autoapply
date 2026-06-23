# Implementation Plan - Stage 5: PEP 8 Compliance & Codebase Redesign

## Goal
We will refactor the codebase to align with PEP 8 coding standards and modernize the project layout according to production-grade Python packaging best practices:
1. **Source Layout Standardization:** Rename the generic `src` package to a dedicated namespace (`naukri_agent`) and place it inside `src/naukri_agent/` (or update absolute paths) to ensure PEP 517 build system compatibility.
2. **Import Ordering & Continuous Blocks:** Align imports in all files to standard PEP 8 groups (standard library, third-party, local), resolving the interleaved execution statements and dataclasses ordering.
3. **Project Root Cleanup:** Move operational utility scripts (`sync_session.py` and `update_resume.py`) from the root directory into a dedicated `scripts/` package.
4. **Namespace Updates:** Systematically update all module imports across all project components and test files.

---

## Proposed Changes

We will restructure directories and update codebase imports:

```
refactored/
├── scripts/
│   ├── sync_session.py
│   └── update_resume.py
└── src/
    └── naukri_agent/
        ├── main.py
        ├── config/
        ├── core/
        ├── database/
        ├── browser/
        ├── ai/
        └── utils/
```

### Infrastructure Layer

#### [MODIFY] All Python Files
* Clean up import groupings at the top of each file, ensuring Standard Library, Third Party, and Local imports are divided into distinct blocks separated by a single empty line.
* Move the console stream reconfiguration script in [logger.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/utils/logger.py) to occur after the imports block.

#### [NEW] [__init__.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/scripts/__init__.py)
* Initialize the `scripts/` directory as a package namespace.

#### [MOVE] [sync_session.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/sync_session.py) -> [sync_session.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/scripts/sync_session.py)
* Move the cookie synchronization script to `scripts/`.

#### [MOVE] [update_resume.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/update_resume.py) -> [update_resume.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/scripts/update_resume.py)
* Move the resume encryption script to `scripts/`.

#### [MOVE] `src/*` -> [src/naukri_agent/*](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/)
* Move all package subfolders (`core`, `config`, `database`, `browser`, `ai`, `orchestrator`, `utils`, `main.py`) inside `src/naukri_agent/`.
* Update absolute import references in all Python files (including `tests/` files) from `from src.xyz` to `from naukri_agent.xyz` or `from src.naukri_agent.xyz` (depending on pythonpath/installation configuration, but standardizing on package-relative or absolute namespace imports).

---

## Verification Plan

### Automated Tests
* We will verify the changes by running `python -m pytest` with the PYTHONPATH updated to include the new package structure.
* We will verify static checks by executing `python -m ruff check src` and `python -m mypy src` if available.

### Manual Verification
* Run a dry run using `python -m src.naukri_agent.main run --dry-run` to ensure the entrypoint loads successfully and dependencies wire up cleanly.
