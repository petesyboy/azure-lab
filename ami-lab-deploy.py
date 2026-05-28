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

def _win_current_user():
    """
    Returns the Windows-qualified username that icacls expects (DOMAIN\\user or
    COMPUTERNAME\\user).  getpass.getuser() only returns the bare username which
    is NOT recognised by icacls on domain-joined or Microsoft Account machines.
    """
    res = subprocess.run(["whoami"], capture_output=True, text=True)
    return res.stdout.strip() if res.returncode == 0 else ""

def _win_unlock_key(key_file, _unused_user=None):
    """
    Strips all inherited/group ACEs and grants the current user Full Control.
    Must be called before any write operation (normalise, ssh-keygen conversion).
    ssh-keygen checks permissions before processing and rejects files that are
    readable by groups such as NT AUTHORITY\\Authenticated Users.
    """
    user = _win_current_user()
    subprocess.run(["takeown",  "/f", key_file],                                           capture_output=True)  # ensure ownership so we can modify ACL
    subprocess.run(["icacls",   key_file, "/inheritance:r"],                               capture_output=True)  # remove inherited ACEs
    subprocess.run(["icacls",   key_file, "/remove", "Everyone"],                          capture_output=True)  # strip Everyone
    subprocess.run(["icacls",   key_file, "/remove", "BUILTIN\\Users"],                    capture_output=True)  # strip Users group
    subprocess.run(["icacls",   key_file, "/remove", "NT AUTHORITY\\Authenticated Users"], capture_output=True)  # strip Auth Users
    if user:
        subprocess.run(["icacls", key_file, "/grant:r", f"{user}:F"],                     capture_output=True)  # owner: Full Control
    subprocess.run(["attrib", "-R", key_file],                                             capture_output=True)  # clear read-only file attribute

def _win_lockdown_key(key_file, _unused_user=None):
    """Downgrades owner access to Read-only so SSH accepts the key file."""
    user = _win_current_user()
    if user:
        subprocess.run(["icacls", key_file, "/grant:r", f"{user}:R"], capture_output=True)
    subprocess.run(["attrib", "+R", key_file], capture_output=True)  # set read-only file attribute



def fetch_and_fix_ssh_key():
    """Downloads the SSH private key from Key Vault and ensures correct file permissions."""
    import shutil as _shutil

    key_file = "lab_key.pem"
    print(f"[*] Fetching SSH private key from Azure Key Vault...")

    # ── Step 1: Download from Key Vault ──────────────────────────────────────
    # On Windows, 'az' is a .cmd batch wrapper that subprocess cannot invoke
    # directly — use shutil.which() to resolve the full path (same pattern as
    # configure_lab.py) and run with shell=True on Windows.
    try:
        kv_res  = subprocess.run(["terraform", "output", "-raw", "key_vault_name"],    capture_output=True, text=True)
        sec_res = subprocess.run(["terraform", "output", "-raw", "lab_key_secret_name"], capture_output=True, text=True)

        if kv_res.returncode == 0 and sec_res.returncode == 0:
            kv_name  = kv_res.stdout.strip()
            sec_name = sec_res.stdout.strip()
            if kv_name and sec_name and "No outputs" not in kv_name:
                # Make existing file writable before overwriting
                if os.path.exists(key_file):
                    if os.name == 'posix':
                        os.chmod(key_file, 0o600)
                    elif os.name == 'nt':
                        _win_unlock_key(key_file)

                az_cmd = _shutil.which("az") or ("az.cmd" if os.name == 'nt' else "az")
                dl_cmd = [
                    az_cmd, "keyvault", "secret", "download",
                    "--vault-name", kv_name,
                    "--name",       sec_name,
                    "--file",       key_file,
                    "--encoding",   "ascii",   # prevent BOM/CRLF on Windows
                ]
                # .cmd files require the Windows shell to execute
                subprocess.run(dl_cmd, shell=(os.name == 'nt'))
    except Exception as e:
        print(f"[!] Warning: Failed to download SSH key from Key Vault: {e}")

    if not os.path.exists(key_file):
        print(f"[!] Warning: {key_file} not found — skipping key fixup.")
        return

    # ── Step 2: Unlock file for all subsequent write operations ──────────────
    print(f"[*] Unlocking {key_file} for processing...")
    try:
        if os.name == 'posix':
            os.chmod(key_file, 0o600)
        elif os.name == 'nt':
            _win_unlock_key(key_file)
    except Exception as e:
        print(f"[!] Warning: Could not unlock {key_file}: {e}")

    # ── Step 3: Normalise line endings (CRLF → LF) ───────────────────────────
    # az keyvault secret download on Windows can write CRLF which corrupts
    # both OpenSSH and PEM key boundaries.
    print(f"[*] Normalising line endings in {key_file}...")
    try:
        with open(key_file, "rb") as f:
            raw = f.read()
        normalised = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        with open(key_file, "wb") as f:
            f.write(normalised)
        print(f"[*] Line endings normalised.")
    except Exception as e:
        print(f"[!] Warning: Could not normalise line endings in {key_file}: {e}")

    # ── Step 4: Windows-only — convert OpenSSH format → RSA PEM ─────────────
    # Windows OpenSSH cannot reliably load "BEGIN OPENSSH PRIVATE KEY" files.
    # ssh-keygen -p -m pem converts in-place.  It requires the file to be
    # accessible only by the owner (guaranteed by _win_unlock_key above).
    if os.name == 'nt':
        print(f"[*] Converting key to RSA PEM format for Windows SSH compatibility...")
        try:
            result = subprocess.run(
                ["ssh-keygen", "-p", "-m", "pem", "-f", key_file, "-P", "", "-N", ""],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"[*] Key converted to RSA PEM format successfully.")
            else:
                print(f"[!] Warning: ssh-keygen conversion returned code {result.returncode}.")
                if result.stderr:
                    print(f"    {result.stderr.strip()}")
        except FileNotFoundError:
            print(f"[!] Warning: ssh-keygen not found. Ensure the Windows OpenSSH Feature is installed.")
        except Exception as e:
            print(f"[!] Warning: Could not convert key format: {e}")

    # ── Step 5: Final permission lock-down ───────────────────────────────────
    print(f"[*] Locking down permissions for {key_file}...")
    try:
        if os.name == 'posix':
            os.chmod(key_file, 0o400)
        elif os.name == 'nt':
            # Downgrade from Full Control to Read-only.  All group ACEs were
            # already stripped in Step 2, so only the owner retains access.
            _win_lockdown_key(key_file)
    except Exception as e:
        print(f"[!] Warning: Could not lock down permissions on {key_file}: {e}")

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
    # On Windows, lab_key.pem may be locked to read-only from a previous run's
    # icacls lockdown.  Terraform's local_sensitive_file resource will fail with
    # "Access is denied" if it cannot overwrite the file.  Unlock it here so
    # Terraform can write the fresh key; fetch_and_fix_ssh_key() re-applies the
    # correct permissions after the apply completes.
    if os.name == 'nt':
        _key = "lab_key.pem"
        if os.path.exists(_key):
            print(f"[*] Pre-apply: unlocking {_key} so Terraform can overwrite it...")
            _win_unlock_key(_key)

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