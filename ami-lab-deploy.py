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
    """Checks if the required UCT-V agent Debian package exists locally or in blob storage."""
    print("[*] Checking for UCT-V agent Debian package...")
    
    # 1. Check local versions
    deb_files = glob.glob("gigamon-gigavue-uctv-*.deb")
    local_versions = []
    for f in deb_files:
        match = re.search(r'gigamon-gigavue-uctv-(.*?)-amd64\.deb', f)
        if match:
            local_versions.append(match.group(1))
            
    latest_local = None
    if local_versions:
        # Sort versions by interpreting parts as integers
        local_versions.sort(key=lambda x: [int(p) if p.isdigit() else p for p in x.split('.')])
        latest_local = local_versions[-1]
        print(f"[*] Found local UCT-V agent. Latest version: {latest_local}")
        
    # 2. Check blob storage
    blob_versions = []
    sa_name = None
    sc_name = None
    
    try:
        sa_res = subprocess.run(["terraform", "output", "-raw", "storage_account_name"], capture_output=True, text=True)
        sc_res = subprocess.run(["terraform", "output", "-raw", "storage_container_name"], capture_output=True, text=True)
        
        if sa_res.returncode == 0 and sc_res.returncode == 0:
            sa_name = sa_res.stdout.strip()
            sc_name = sc_res.stdout.strip()
            
            if sa_name and sc_name and "No outputs" not in sa_name:
                blob_cmd = [
                    "az", "storage", "blob", "list", 
                    "--account-name", sa_name, 
                    "--container-name", sc_name, 
                    "--auth-mode", "login", 
                    "--query", "[].name", "-o", "tsv"
                ]
                blob_res = subprocess.run(blob_cmd, capture_output=True, text=True)
                if blob_res.returncode == 0:
                    for line in blob_res.stdout.strip().split('\n'):
                        match = re.search(r'gigamon-gigavue-uctv-(.*?)-amd64\.deb', line)
                        if match:
                            blob_versions.append(match.group(1))
    except Exception as e:
        print(f"[*] Could not check blob storage: {e}")

    latest_blob = None
    if blob_versions:
        blob_versions.sort(key=lambda x: [int(p) if p.isdigit() else p for p in x.split('.')])
        latest_blob = blob_versions[-1]
        print(f"[*] Found UCT-V agent in Blob Storage. Latest version: {latest_blob}")

    # 3. Handle existence logic
    if not latest_local and not latest_blob:
        print("\n" + "!"*80)
        print("[!] ERROR: Required UCT-V agent Debian package not found in current directory OR Blob Storage!")
        print("    Please login to https://community.gigamon.com to download the required file.")
        print("    Place the .deb file in the workspace root directory before deploying.")
        print("!"*80 + "\n")
        sys.exit(1)
        
    # Determine the latest version between local and blob
    chosen_version = latest_local
    if latest_local and latest_blob:
        local_parts = [int(p) if p.isdigit() else p for p in latest_local.split('.')]
        blob_parts = [int(p) if p.isdigit() else p for p in latest_blob.split('.')]
        if local_parts > blob_parts:
            print(f"[*] Local version ({latest_local}) is newer than blob storage version ({latest_blob}). Will use local.")
            chosen_version = latest_local
        else:
            print(f"[*] Blob storage version ({latest_blob}) is greater than or equal to local version ({latest_local}).")
            chosen_version = latest_blob
    elif latest_blob:
        chosen_version = latest_blob

    # Download from blob if chosen_version is from blob and doesn't exist locally
    chosen_filename = f"gigamon-gigavue-uctv-{chosen_version}-amd64.deb"
    if not os.path.exists(chosen_filename) and chosen_version == latest_blob:
        print(f"[*] Required version {chosen_version} is missing locally. Downloading from Blob Storage for Terraform...")
        dl_cmd = [
            "az", "storage", "blob", "download",
            "--account-name", sa_name,
            "--container-name", sc_name,
            "--name", chosen_filename,
            "--file", chosen_filename,
            "--auth-mode", "login"
        ]
        res = subprocess.run(dl_cmd)
        if res.returncode != 0:
            print(f"[!] Warning: Failed to download {chosen_filename} from Blob Storage.")

    # 4. Update variables.tf to use the chosen version
    if chosen_version:
        parts = chosen_version.split('.')
        if len(parts) >= 2:
            # e.g., '6.13.00' -> '6.13'
            tf_version = f"{parts[0]}.{parts[1]}"
            print(f"[*] Ensuring target gigamon_version in variables.tf is {tf_version}...")
            if os.path.exists("variables.tf"):
                try:
                    with open("variables.tf", "r") as f:
                        content = f.read()
                    
                    new_content = re.sub(
                        r'(variable\s+"gigamon_version"\s+\{[\s\S]*?default\s*=\s*")[^"]+(")',
                        rf'\g<1>{tf_version}\g<2>',
                        content
                    )
                    
                    if new_content != content:
                        with open("variables.tf", "w") as f:
                            f.write(new_content)
                        print(f"[*] Updated variables.tf to use version {tf_version}.")
                except Exception as e:
                    print(f"[!] Warning: Could not update variables.tf automatically: {e}")

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
                os.chmod(key_file, 0o600)
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
    
    # 3. Plan Terraform deployment
    run_command(["terraform", "plan", "-out=tfplan"])
    
    # 4. Apply Terraform deployment
    print("\n[*] Applying Terraform configuration...")
    run_command(["terraform", "apply", "tfplan"])
    
    # 5. Run the generated configuration script
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