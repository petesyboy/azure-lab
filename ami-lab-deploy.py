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
    """Checks if the required UCT-V agent Debian package exists in the UCTV-files directory."""
    deb_dir = "UCTV-files"
    deb_files = glob.glob(os.path.join(deb_dir, "gigamon-gigavue-uctv-*.deb"))
    
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
            
    expected_file = os.path.join(deb_dir, f"gigamon-gigavue-uctv-{version}.00-amd64.deb")
    
    if not os.path.exists(expected_file):
        print("\n" + "!"*80)
        print(f"[!] ERROR: Required UCT-V agent Debian package not found in the {deb_dir} directory!")
        print(f"    Expected file: {expected_file}")
        if deb_files:
            print(f"    Found other .deb file(s) in directory: {', '.join(deb_files)}")
            print(f"    Please update the 'gigamon_version' in 'variables.tf' to match your file.")
        else:
            print(f"    Please ensure the UCT-V agent deb package is placed in the {deb_dir} directory.")
        print("!"*80 + "\n")
        sys.exit(1)

def fetch_and_fix_ssh_key():
    """Downloads the SSH private key from Key Vault and ensures correct file permissions."""
    key_file = "lab_key.pem"
    print(f"[*] Fetching SSH private key from Azure Key Vault...")
    
    try:
        kv_res = subprocess.run(["terraform", "output", "-raw", "key_vault_name"], capture_output=True, text=True)
        sec_res = subprocess.run(["terraform", "output", "-raw", "lab_key_secret_name"], capture_output=True, text=True)
        
        if kv_res.returncode == 0 and sec_res.returncode == 0:
            kv_name = kv_res.stdout.strip()
            sec_name = sec_res.stdout.strip()
            if kv_name and sec_name and "No outputs" not in kv_name:
                # If the file already exists and is read-only, make it writable first
                if os.path.exists(key_file) and os.name == 'posix':
                    os.chmod(key_file, 0o600)
                    
                dl_cmd = [
                    "az", "keyvault", "secret", "download",
                    "--vault-name", kv_name,
                    "--name", sec_name,
                    "--file", key_file
                ]
                subprocess.run(dl_cmd)
    except Exception as e:
        print(f"[!] Warning: Failed to download SSH key from Key Vault: {e}")

    if os.path.exists(key_file):
        print(f"[*] Ensuring correct permissions for {key_file}...")
        try:
            if os.name == 'posix':
                os.chmod(key_file, 0o400)
            elif os.name == 'nt':
                # Lock down file using Windows icacls
                subprocess.run(["icacls", key_file, "/inheritance:r"], capture_output=True)
                import getpass
                user = getpass.getuser()
                subprocess.run(["icacls", key_file, "/grant:r", f"{user}:F"], capture_output=True)
        except Exception as e:
            print(f"[!] Warning: Could not adjust permissions on {key_file}: {e}")

def main():
    print("======================================================")
    print(" Azure Lab 6.1x - Gigamon V Series Deployment Wrapper ")
    print("======================================================")
    
    # 1. Check dependencies
    check_dependencies()
    
    # 2. Initialize Terraform
    run_command(["terraform", "init"])
    
    # 3. Check UCT-V Debian package existence (moved after init to check blob storage)
    check_uctv_deb()
    
    # 4. Plan Terraform deployment
    run_command(["terraform", "plan", "-out=tfplan"])
    
    # 5. Apply Terraform deployment
    print("\n[*] Applying Terraform configuration...")
    run_command(["terraform", "apply", "tfplan"])
    
    # 6. Run the generated configuration script
    config_script = os.path.join("scripts", "configure_lab.py")
    if os.path.exists(config_script):
        # Download SSH key from KV and fix permissions before attempting connection
        fetch_and_fix_ssh_key()
        
        print(f"\n[*] Infrastructure deployed. Executing {config_script}...")
        # Use sys.executable to run it with the same Python interpreter
        result = subprocess.run([sys.executable, config_script])
        if result.returncode != 0:
            print("\n" + "!"*80)
            print("[!] WARNING: Configuration script failed (often due to SSH initialization delays).")
            print("    Your infrastructure was successfully deployed, but post-deployment")
            print("    configuration via SSH encountered an error.")
            print(f"    You can safely retry this configuration step later by running:")
            print(f"        {sys.executable} {config_script}")
            print("!"*80 + "\n")
            sys.exit(result.returncode)
    else:
        print(f"\n[!] Configuration script {config_script} not found.")
        print("    Please ensure Terraform generated it correctly from the template.")


if __name__ == "__main__":
    main()