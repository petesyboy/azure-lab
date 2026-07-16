#!/usr/bin/env python3
import sys
import hashlib
import shutil


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
    version = "6.14" # Fallback default
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
        # If there is exactly one deb file, try to match and update variables.tf automatically
        if len(deb_files) == 1:
            fn = os.path.basename(deb_files[0])
            m = re.search(r'gigamon-gigavue-uctv-([0-9.]+)-amd64\.deb', fn)
            if m:
                full_ver = m.group(1)
                parts = full_ver.split('.')
                if len(parts) >= 2:
                    detected_major_minor = f"{parts[0]}.{parts[1]}"
                    if detected_major_minor != version:
                        print(f"[*] Auto-detected UCT-V package version: {detected_major_minor} (from {fn})")
                        print(f"[*] Updating 'gigamon_version' in 'variables.tf' to match your package...")
                        try:
                            with open("variables.tf", "r") as f:
                                var_content = f.read()
                            
                            pattern = r'(variable\s+"gigamon_version"\s+\{[^}]*default\s*=\s*")([^"]+)(")'
                            updated_content = re.sub(pattern, rf'\1{detected_major_minor}\3', var_content, flags=re.DOTALL)
                            
                            with open("variables.tf", "w") as f:
                                f.write(updated_content)
                            print(f"[+] Successfully updated 'variables.tf' default to '{detected_major_minor}'.")
                            version = detected_major_minor
                            expected_file = deb_files[0]
                        except Exception as e:
                            print(f"[!] Warning: Could not automatically update 'variables.tf': {e}")

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
                    "--overwrite",
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
    # (Skipped: Keys are natively generated in standard PEM format in keys.tf)

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

def check_mgmt_ip_warning():
    """Warns the user if management access is wide-open (*)."""
    mgmt_ip = "*"
    if os.path.exists("variables.tf"):
        try:
            with open("variables.tf", "r") as f:
                content = f.read()
                # Look for variable "allowed_mgmt_ip" default
                match = re.search(r'variable\s+"allowed_mgmt_ip"\s+\{[^}]*default\s*=\s*"([^"]+)"', content, re.DOTALL)
                if match:
                    mgmt_ip = match.group(1)
        except Exception:
            pass
            
    if mgmt_ip == "*":
        print("\n" + "#"*80)
        print("[WARNING] SECURITY NOTICE: Management access is set to wide-open ('*')!")
        print("          This exposes management ports (SSH, GigaVUE-FM, ntopng, Kibana)")
        print("          to the entire internet. For production or secure deployments,")
        print("          please change 'allowed_mgmt_ip' to 'dynamic' or a specific CIDR.")
        print("#"*80 + "\n")

def bootstrap_remote_state():
    """Ensures that the resource group and storage account for Terraform remote state exist in Azure."""
    az_cmd = shutil.which("az") or ("az.cmd" if os.name == 'nt' else "az")
    
    # 1. Fetch current subscription ID
    print("[*] Fetching subscription details from Azure CLI...")
    res = subprocess.run([az_cmd, "account", "show", "--query", "id", "-o", "tsv"], capture_output=True, text=True, shell=(os.name == 'nt'))
    if res.returncode != 0:
        print("[!] Error: You must be logged into Azure CLI ('az login') to manage remote state.")
        sys.exit(1)
        
    sub_id = res.stdout.strip()
    if not sub_id:
        print("[!] Error: Could not retrieve active subscription ID.")
        sys.exit(1)
        
    # Resolve Azure Region (Location), Owner, and Project from variables.tf for tagging
    location = "uksouth"
    email = "pete.connolly@gigamon.com"
    project = "connolly-transitory-demo-tf-3po"
    if os.path.exists("variables.tf"):
        try:
            with open("variables.tf", "r") as f:
                content = f.read()
                match_loc = re.search(r'variable\s+"location"\s+\{[^}]*default\s*=\s*"([^"]+)"', content, re.DOTALL)
                if match_loc:
                    location = match_loc.group(1)
                match_email = re.search(r'variable\s+"gigamon_email"\s+\{[^}]*default\s*=\s*"([^"]+)"', content, re.DOTALL)
                if match_email:
                    email = match_email.group(1)
                match_project = re.search(r'variable\s+"project_name"\s+\{[^}]*default\s*=\s*"([^"]+)"', content, re.DOTALL)
                if match_project:
                    project = match_project.group(1)
        except Exception:
            pass

    # Generate unique 24-character storage account name
    # "tfstate" (7 chars) + md5 hash of sub_id (12 chars) = 19 chars (safe and globally unique)
    h = hashlib.md5((sub_id + project).encode('utf-8')).hexdigest()[:12]
    storage_account_name = f"tfstate{h}"
    rg_name = f"{project}-tfstate-rg"
    container_name = "tfstate"
    key_name = "azure-lab.terraform.tfstate"

    tags_arg = [
        "--tags",
        f"owner={email}",
        f"Project={project}",
        "Environment=demo",
        "hours needed=8",
        "DeploymentType=connolly-demo"
    ]

    # 2. Check if Resource Group exists, create if not
    print(f"[*] Ensuring Resource Group '{rg_name}' exists in region '{location}'...")
    res_rg = subprocess.run([az_cmd, "group", "exists", "--name", rg_name], capture_output=True, text=True, shell=(os.name == 'nt'))
    if res_rg.stdout.strip() != "true":
        print(f"[*] Resource Group '{rg_name}' not found. Creating with mandatory tags...")
        subprocess.run([az_cmd, "group", "create", "--name", rg_name, "--location", location] + tags_arg, shell=(os.name == 'nt'), check=True)
    else:
        print(f"[+] Resource Group '{rg_name}' exists.")

    # 3. Check if Storage Account exists, create if not
    print(f"[*] Ensuring Storage Account '{storage_account_name}' exists...")
    res_sa = subprocess.run([az_cmd, "storage", "account", "show", "--name", storage_account_name, "--resource-group", rg_name], capture_output=True, text=True, shell=(os.name == 'nt'))
    if res_sa.returncode != 0:
        print(f"[*] Storage Account '{storage_account_name}' not found. Creating with mandatory tags (this might take 30s)...")
        subprocess.run([
            az_cmd, "storage", "account", "create",
            "--name", storage_account_name,
            "--resource-group", rg_name,
            "--location", location,
            "--sku", "Standard_LRS",
            "--encryption-services", "blob"
        ] + tags_arg, shell=(os.name == 'nt'), check=True)
    else:
        print(f"[+] Storage Account '{storage_account_name}' exists.")

    # 4. Ensure container exists
    print(f"[*] Ensuring blob container '{container_name}' exists...")
    subprocess.run([
        az_cmd, "storage", "container", "create",
        "--name", container_name,
        "--account-name", storage_account_name
    ], shell=(os.name == 'nt'), capture_output=True)
    
    print("[+] Remote state backend bootstrap complete.")
    return rg_name, storage_account_name, container_name, key_name

def main():
    print("===========================================================")
    print(" Azure Lab - Gigamon V Series Deployment Wrapper v1.0 ")
    print("===========================================================")
    
    # Check management IP security warning
    check_mgmt_ip_warning()
    
    # 1. Check dependencies
    check_dependencies()
    
    # 2. Bootstrap Azure Remote State Backend
    print("[*] Bootstrapping remote state backend...")
    rg_name, sa_name, container_name, key_name = bootstrap_remote_state()
    
    # 3. Initialize Terraform with Remote Backend
    print("[*] Initializing Terraform with remote state storage...")
    run_command([
        "terraform", "init",
        "-reconfigure",
        f"-backend-config=resource_group_name={rg_name}",
        f"-backend-config=storage_account_name={sa_name}",
        f"-backend-config=container_name={container_name}",
        f"-backend-config=key={key_name}"
    ])
    
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
            print("[!] WARNING: Configuration script failed (SSH connection dropped).")
            print("    Your infrastructure was successfully deployed, but post-deployment")
            print("    configuration over SSH was blocked (likely by a Corporate VPN/Proxy).")
            print("    VMs will continue to provision via cloud-init in the background.")
            print("!"*80 + "\n")
            sys.exit(result.returncode)
    else:
        print(f"\n[!] Configuration script {config_script} not found.")
        print("    Please ensure Terraform generated it correctly from the template.")


if __name__ == "__main__":
    main()