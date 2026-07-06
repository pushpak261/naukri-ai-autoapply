import os
from pathlib import Path


def clear_data_and_cache():
    targets = [
        Path("data/naukri_agent.db"),
        Path("data/project_index.db"),
        Path("data/qa_cache.json"),
        Path("data/sessions/naukri_session.json"),
    ]

    for path in targets:
        if path.exists():
            try:
                os.remove(path)
                print(f"Successfully deleted {path}")
            except Exception as e:
                print(f"Error deleting {path}: {e}")
        else:
            print(f"{path} does not exist, nothing to clear.")


if __name__ == "__main__":
    clear_data_and_cache()
