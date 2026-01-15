#!/usr/bin/env python
"""
Setup script for e-flow project.
Initializes the environment and prepares the system for first use.
"""

import os
import sys
import subprocess
from pathlib import Path

def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def print_step(step_num, text):
    """Print a formatted step."""
    print(f"\n[{step_num}] {text}")

def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"    Running: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"    ✅ {description}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"    ❌ {description} failed")
        print(f"    Error: {e.stderr}")
        return False

def main():
    """Main setup function."""
    print_header("e-flow Setup")
    
    # Check Python version
    print_step(1, "Checking Python version")
    python_version = sys.version_info
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 10):
        print(f"    ❌ Python 3.10+ required (you have {python_version.major}.{python_version.minor})")
        return False
    print(f"    ✅ Python {python_version.major}.{python_version.minor} detected")
    
    # Check if venv exists
    print_step(2, "Checking virtual environment")
    venv_path = Path(".venv")
    if venv_path.exists():
        print("    ✅ Virtual environment already exists")
    else:
        print("    ⚠️  Creating new virtual environment")
        if not run_command(f"{sys.executable} -m venv .venv", "Virtual environment creation"):
            return False
    
    # Activate and install dependencies
    print_step(3, "Installing Python dependencies")
    if sys.platform == "win32":
        activate_cmd = ".venv\\Scripts\\activate && "
    else:
        activate_cmd = "source .venv/bin/activate && "
    
    if not run_command(f"{activate_cmd}pip install -r requirements.txt", "Dependency installation"):
        return False
    
    # Install Playwright browser
    print_step(4, "Installing Playwright browser")
    if not run_command(f"{activate_cmd}playwright install chromium", "Playwright chromium installation"):
        print("    ⚠️  Playwright installation had issues, but continuing...")
    
    # Initialize database
    print_step(5, "Initializing database")
    if not run_command(f"{activate_cmd}python database.py", "Database initialization"):
        return False
    
    # Verify database
    print_step(6, "Verifying setup")
    try:
        from database import FlowDatabase
        db = FlowDatabase()
        device_count = db.get_device_count()
        measurement_count = db.get_measurement_count()
        print(f"    ✅ Database verified")
        print(f"       - Devices: {device_count}")
        print(f"       - Measurements: {measurement_count}")
    except Exception as e:
        print(f"    ❌ Database verification failed: {e}")
        return False
    
    # Print next steps
    print_header("Setup Complete!")
    print("\n📋 Next Steps:\n")
    
    if sys.platform == "win32":
        activate = ".venv\\Scripts\\activate"
    else:
        activate = "source .venv/bin/activate"
    
    print(f"1. Activate the virtual environment:")
    print(f"   {activate}\n")
    
    print("2. Collect data from the monitor:")
    print("   python ingest.py\n")
    
    print("3. Start the dashboard:")
    print("   streamlit run app.py\n")
    
    print("4. Open your browser to:")
    print("   http://localhost:8501\n")
    
    print("📚 For more information, see:")
    print("   - README.md for full documentation")
    print("   - QUICKSTART.md for quick reference")
    print("   - config.py to customize settings\n")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
