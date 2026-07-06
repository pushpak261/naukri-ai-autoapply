import time
import os
import sys
import subprocess
from src.naukri_agent.config.settings import get_settings


def test_watcher():
    settings = get_settings()
    print(f"Config 'enable_project_indexer' is: {settings.application.enable_project_indexer}")

    if not settings.application.enable_project_indexer:
        print("Indexer is disabled in config. Test aborted.")
        return

    script_path = settings.project_root / "scripts" / "vibe_context.py"

    print("Starting watcher subprocess...")
    p = subprocess.Popen(
        [sys.executable, str(script_path), "--watch"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for initial indexing to complete
    print("Waiting 5 seconds for initial index...")
    time.sleep(5)

    # Create a dummy file
    dummy_file = "dummy_watcher_test.py"
    print(f"Creating {dummy_file}...")
    with open(dummy_file, "w") as f:
        f.write("def dummy(): pass\n")

    print("Waiting 3 seconds for debounce...")
    time.sleep(3)

    # Update the file
    print(f"Updating {dummy_file}...")
    with open(dummy_file, "a") as f:
        f.write("    print('updated')\n")

    print("Waiting 3 seconds for debounce...")
    time.sleep(3)

    # Delete the file
    print(f"Deleting {dummy_file}...")
    os.remove(dummy_file)

    print("Waiting 3 seconds for debounce...")
    time.sleep(3)

    print("Terminating watcher...")
    p.terminate()
    out, err = p.communicate()

    print("\n--- WATCHER STDOUT ---")
    print(out)
    print("--- END STDOUT ---\n")

    if err:
        print("--- WATCHER STDERR ---")
        print(err)
        print("--- END STDERR ---\n")


if __name__ == "__main__":
    test_watcher()
