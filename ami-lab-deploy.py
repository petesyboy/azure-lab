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

def check_dependencies():
    try:
        import requests
    except ImportError:
        print("[*] Required module 'requests' not found. Installing...")
        run_command([sys.executable, "-m", "pip", "install", "requests"])

def main():
    print("======================================================")
    print(" Azure Lab 6.1x - Gigamon V Series Deployment Wrapper ")
    print("======================================================")
    
    # 0. Check dependencies
    check_dependencies()
    
    # 1. Initialize Terraform
    run_command(["terraform", "init"])
    
    # 2. Plan Terraform deployment
    run_command(["terraform", "plan", "-out=tfplan"])
    
    # 3. Apply Terraform deployment
    print("\n[*] Applying Terraform configuration...")
    run_command(["terraform", "apply", "tfplan"])
    
    # 4. Run the generated configuration script
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