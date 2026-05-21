#!/usr/bin/env python3
"""ASTRA quickstart — checks prerequisites and launches the UI."""

import os
import sys
import subprocess
import shutil


REQUIRED_ENV_KEYS = ["ANTHROPIC_API_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"]


def check_python():
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 11):
        print(f"✗ Python ≥ 3.11 required (found {v.major}.{v.minor})")
        return False
    print(f"✓ Python {v.major}.{v.minor}.{v.micro}")
    return True


def check_node():
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node:
        print("✗ Node.js not found. Install from https://nodejs.org")
        return False
    if not npm:
        print("✗ npm not found")
        return False
    result = subprocess.run(["node", "--version"], capture_output=True, text=True)
    print(f"✓ Node {result.stdout.strip()}")
    return True


def check_env():
    env_file = ".env"
    if not os.path.exists(env_file):
        print(f"✗ {env_file} not found. Run: cp .env.example .env")
        return False

    import dotenv
    dotenv.load_dotenv(env_file)

    missing = [k for k in REQUIRED_ENV_KEYS if not os.environ.get(k)]
    if missing:
        print(f"✗ Missing env vars in .env: {', '.join(missing)}")
        return False

    print("✓ .env file found with required keys")
    return True


def main():
    print("ASTRA Quickstart — Checking prerequisites...\n")
    ok = all([check_python(), check_node(), check_env()])

    if not ok:
        print("\n✗ Prerequisites not met. Fix the issues above and re-run.")
        sys.exit(1)

    print("\n✓ All prerequisites met. Starting ASTRA...\n")
    start_script = os.path.join("src", "astra", "ui", "start.sh")
    if os.path.exists(start_script):
        subprocess.run(["bash", start_script])
    else:
        print(f"✗ start.sh not found at {start_script}")
        sys.exit(1)


if __name__ == "__main__":
    main()
