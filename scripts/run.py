#!/usr/bin/env python3
"""
Universal runner for Youmind skill scripts.
Ensures scripts always run inside the local virtual environment.
"""

import os
import subprocess
import sys
from pathlib import Path


def get_venv_python() -> Path:
    """Return venv python path for current platform."""
    skill_dir = Path(__file__).parent.parent
    venv_dir = skill_dir / ".venv"

    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def ensure_venv() -> Path:
    """Create/setup virtual environment when missing."""
    skill_dir = Path(__file__).parent.parent
    venv_dir = skill_dir / ".venv"
    setup_script = skill_dir / "scripts" / "setup_environment.py"

    if not venv_dir.exists():
        print("🔧 First-time setup: creating virtual environment...")
        result = subprocess.run([sys.executable, str(setup_script)])
        if result.returncode != 0:
            print("❌ Failed to set up environment")
            raise SystemExit(1)
        print("✅ Environment ready")

    return get_venv_python()


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/run.py <script_name> [args...]")
        print("\nAvailable scripts:")
        print("  board_manager.py   - Board APIs (list/find/get/create)")
        print("  material_manager.py - Material APIs (add-link/upload-file/get-snips)")
        print("  chat_manager.py    - Chat APIs (create/send/history/detail)")
        print("  ask_question.py    - Compatibility wrapper over chat APIs")
        print("  auth_manager.py    - Browser login bootstrap/validation")
        print("  cleanup_manager.py - Clean local skill data")
        raise SystemExit(1)

    script_name = sys.argv[1]
    script_args = sys.argv[2:]

    if script_name.startswith("scripts/"):
        script_name = script_name[8:]

    if not script_name.endswith(".py"):
        script_name += ".py"

    skill_dir = Path(__file__).parent.parent
    script_path = skill_dir / "scripts" / script_name

    if not script_path.exists():
        print(f"❌ Script not found: {script_name}")
        print(f"   Looked for: {script_path}")
        raise SystemExit(1)

    venv_python = ensure_venv()
    cmd = [str(venv_python), str(script_path)] + script_args

    try:
        result = subprocess.run(cmd)
        raise SystemExit(result.returncode)
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
        raise SystemExit(130)
    except Exception as e:
        print(f"❌ Error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
