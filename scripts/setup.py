#!/usr/bin/env python3
import os
import sys
import venv
import subprocess
from pathlib import Path

def print_message(msg: str, is_error: bool = False):
    prefix = "[ERROR]" if is_error else "[INFO]"
    print(f"{prefix} {msg}")

def main():
    root_dir = Path(__file__).resolve().parent.parent
    venv_dir = root_dir / ".venv"
    req_file = root_dir / "requirements.txt"

    if not req_file.exists():
        print_message(f"Dependency file not found at {req_file}", is_error=True)
        sys.exit(1)

    # 1. Create or reuse the virtual environment
    if not venv_dir.exists():
        print_message(f"Creating virtual environment at {venv_dir}...")
        try:
            # Create a virtual environment using the built-in venv module
            builder = venv.EnvBuilder(with_pip=True)
            builder.create(venv_dir)
            print_message("Virtual environment created successfully.")
        except Exception as e:
            print_message(f"Failed to create virtual environment: {e}", is_error=True)
            sys.exit(1)
    else:
        print_message(f"Found existing virtual environment at {venv_dir}. Reusing it.")

    # Determine pip path based on OS
    if os.name == 'nt':
        pip_path = venv_dir / "Scripts" / "pip.exe"
    else:
        pip_path = venv_dir / "bin" / "pip"

    if not pip_path.exists():
        print_message(f"Pip executable not found in virtual environment ({pip_path}). Environment might be corrupted.", is_error=True)
        sys.exit(1)

    # 2. Install dependencies
    print_message(f"Installing missing dependencies from {req_file.name}...")
    try:
        # We run pip install -r requirements.txt
        # pip inherently avoids reinstalling if the version satisfies the requirement
        result = subprocess.run(
            [str(pip_path), "install", "-r", str(req_file)],
            cwd=root_dir,
            check=True,
            capture_output=True,
            text=True
        )
        print_message("Dependencies installed successfully.")
        # Optional: Print output if needed
        # print(result.stdout)
    except subprocess.CalledProcessError as e:
        print_message(f"Failed to install dependencies: {e}", is_error=True)
        print_message(e.stderr, is_error=True)
        sys.exit(1)



    # 3. Setup Frontend
    frontend_dir = root_dir / "frontend"
    if frontend_dir.exists() and (frontend_dir / "package.json").exists():
        print_message("Found frontend directory. Checking for Node.js...")
        try:
            subprocess.run(["node", "--version"], check=True, capture_output=True, text=True)
            subprocess.run(["npm", "--version"], check=True, capture_output=True, text=True)

            print_message("Installing frontend dependencies...")
            subprocess.run(
                ["npm", "install"],
                cwd=frontend_dir,
                check=True,
                capture_output=True,
                text=True
            )
            print_message("Frontend dependencies installed successfully.")

            # Copy .env.example to .env if .env doesn't exist
            env_example = frontend_dir / ".env.example"
            env_file = frontend_dir / ".env"
            if env_example.exists() and not env_file.exists():
                import shutil
                shutil.copy(env_example, env_file)
                print_message("Created frontend/.env from frontend/.env.example")

        except FileNotFoundError:
            print_message("Node.js or npm not found. Skipping frontend setup.", is_error=True)
        except subprocess.CalledProcessError as e:
            print_message(f"Failed to setup frontend: {e}", is_error=True)
            print_message(e.stderr, is_error=True)
            sys.exit(1)
    else:
        print_message("No frontend directory with package.json found. Skipping frontend setup.")

    print_message("Setup completed successfully.")

if __name__ == "__main__":
    main()
