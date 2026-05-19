#!/usr/bin/env python3
import subprocess
import sys
import os

def run_command(command, cwd=None):
    print(f"[*] Running: {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd)
    if result.returncode != 0:
        print(f"[!] Error executing {' '.join(command)}")
        sys.exit(result.returncode)

def main():
    print("======================================================")
    print(" Azure Lab 6.12 - Gigamon V Series Deployment Wrapper ")
    print("======================================================")
    
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