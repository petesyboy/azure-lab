#!/usr/bin/env python3
import sys

# Ensure that the script is run using the Python 3 interpreter
if sys.version_info.major < 3:
    print("Error: This script must be run using the Python 3 interpreter.")
    sys.exit(1)

import subprocess
import os

def run_command(command, cwd=None):
    print(f"[*] Running: {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd)
    if result.returncode != 0:
        print(f"[!] Error executing {' '.join(command)}")
        sys.exit(result.returncode)

import glob
import re

def check_dependencies():
    try:
        import requests
    except ImportError:
        print("[*] Required module 'requests' not found. Installing...")
        run_command([sys.executable, "-m", "pip", "install", "requests"])

def check_uctv_deb():
    """Checks if the required UCT-V agent Debian package exists in the root directory."""
    deb_files = glob.glob("gigamon-gigavue-uctv-*.deb")
    
    # Try to parse the default gigamon_version from variables.tf
    version = "6.13" # Fallback default
    if os.path.exists("variables.tf"):
        try:
            with open("variables.tf", "r") as f:
                content = f.read()
                # Look for variable "gigamon_version" default
                match = re.search(r'variable\s+"gigamon_version"\s+\{[^}]*default\s*=\s*"([^"]+)"', content, re.DOTALL)
                if match:
                    version = match.group(1)
        except Exception:
            pass
            
    expected_file = f"gigamon-gigavue-uctv-{version}.00-amd64.deb"
    
    if not os.path.exists(expected_file):
        print("\n" + "!"*80)
        print(f"[!] ERROR: Required UCT-V agent Debian package not found in root directory!")
        print(f"    Expected file: {expected_file}")
        if deb_files:
            print(f"    Found other .deb file(s) in directory: {', '.join(deb_files)}")
            print(f"    Please update the 'gigamon_version' in 'variables.tf' to match your file.")
        else:
            print("    Please ensure the UCT-V agent deb package is placed in the workspace root.")
        print("!"*80 + "\n")
        sys.exit(1)

def main():
    print("======================================================")
    print(" Azure Lab 6.1x - Gigamon V Series Deployment Wrapper ")
    print("======================================================")
    
    # 0. Check UCT-V Debian package existence
    check_uctv_deb()
    
    # 1. Check dependencies
    check_dependencies()
    
    # 2. Initialize Terraform
    run_command(["terraform", "init"])
    
    # 3. Plan Terraform deployment
    run_command(["terraform", "plan", "-out=tfplan"])
    
    # 4. Apply Terraform deployment
    print("\n[*] Applying Terraform configuration...")
    run_command(["terraform", "apply", "tfplan"])
    
    # 5. Run the generated configuration script
    config_script = os.path.join("scripts", "configure_lab.py")
    if os.path.exists(config_script):
        print(f"\n[*] Infrastructure deployed. Executing {config_script}...")
        # Use sys.executable to run it with the same Python interpreter
        run_command([sys.executable, config_script])
    else:
        print(f"\n[!] Configuration script {config_script} not found.")
        print("    Please ensure Terraform generated it correctly from the template.")


if __name__ == "__main__":
    main()