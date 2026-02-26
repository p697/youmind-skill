#!/usr/bin/env python3
"""
Universal runner for Youmind skill scripts.
Ensures scripts always run inside the local virtual environment.
"""

import os
import subprocess
import sys


MIN_PYTHON = (3, 10)


def get_venv_python():
    """Return venv python path for current platform."""
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_dir = os.path.join(skill_dir, ".venv")

    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def ensure_venv():
    """Create/setup virtual environment when missing."""
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_dir = os.path.join(skill_dir, ".venv")
    setup_script = os.path.join(skill_dir, "scripts", "setup_environment.py")

    if not os.path.exists(venv_dir):
        print("First-time setup: creating virtual environment...")
        result = subprocess.call([sys.executable, setup_script])
        if result != 0:
            print("Failed to set up environment")
            raise SystemExit(1)
        print("Environment ready")

    return get_venv_python()


def main():
    if sys.version_info[:2] < MIN_PYTHON:
        print(f"ERROR: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required (current: {sys.version_info[0]}.{sys.version_info[1]})")
        raise SystemExit(1)

    if len(sys.argv) < 2:
        print("Usage: python scripts/run.py <script_name> [args...]")
        print("\nAvailable scripts:")
        print("  board_manager.py    - Board APIs (list/find/get/create)")
        print("  material_manager.py - Material APIs (add-link/upload-file/get-snips)")
        print("  chat_manager.py     - Chat APIs (create/send/history/detail)")
        print("  artifact_manager.py - Extract image/slides/doc artifacts from chats")
        print("  ask_question.py     - Compatibility wrapper over chat APIs")
        print("  auth_manager.py     - Browser login bootstrap/validation")
        print("  cleanup_manager.py  - Clean local skill data")
        raise SystemExit(1)

    script_name = sys.argv[1]
    script_args = sys.argv[2:]

    if script_name.startswith("scripts/"):
        script_name = script_name[8:]

    if not script_name.endswith(".py"):
        script_name += ".py"

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(skill_dir, "scripts", script_name)

    if not os.path.exists(script_path):
        print(f"Script not found: {script_name}")
        print(f"Looked for: {script_path}")
        raise SystemExit(1)

    venv_python = ensure_venv()
    cmd = [venv_python, script_path] + script_args

    try:
        result = subprocess.call(cmd)
        raise SystemExit(result)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        raise SystemExit(130)
    except Exception as e:
        print(f"Error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
