#!/usr/bin/env python3
import subprocess
import sys
import concurrent.futures

def check_vm(rg_name, display_name, vm_name):
    # A universally applicable one-liner shell script.
    # 1. Confirms Azure VM Agent responsiveness (PING).
    # 2. Checks gigamon-cloud.conf to see if the Key Vault token was successfully replaced.
    # 3. Checks standard agent services for active running status.
    script = (
        'echo "PING: PONG"; '
        'if [ -f /etc/gigamon-cloud.conf ]; then grep -q "PLACEHOLDER_TOKEN" /etc/gigamon-cloud.conf && echo "TOKEN_STATUS: PENDING" || echo "TOKEN_STATUS: REGISTERED"; else echo "TOKEN_STATUS: NOT_FOUND"; fi; '
        'if systemctl list-units --full -all | grep -q "vseries-node.service"; then systemctl is-active vseries-node >/dev/null 2>&1 && echo "SERVICE_STATUS: ACTIVE" || echo "SERVICE_STATUS: INACTIVE"; '
        'elif systemctl list-units --full -all | grep -q "uctv.service"; then systemctl is-active uctv >/dev/null 2>&1 && echo "SERVICE_STATUS: ACTIVE" || echo "SERVICE_STATUS: INACTIVE"; '
        'else echo "SERVICE_STATUS: UNKNOWN"; fi'
    )
    
    cmd = [
        "az", "vm", "run-command", "invoke",
        "--command-id", "RunShellScript",
        "--name", vm_name,
        "-g", rg_name,
        "--scripts", script,
        "--query", "value[0].message",
        "-o", "tsv"
    ]
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            return display_name, False, "UNREACHABLE", "UNREACHABLE"
    except subprocess.TimeoutExpired:
        return display_name, False, "TIMEOUT (Azure Agent Busy)", "UNKNOWN"
        
    out = res.stdout.strip()
    token_status = "UNKNOWN"
    svc_status = "UNKNOWN"
    ping = False
    
    for line in out.splitlines():
        if "TOKEN_STATUS:" in line:
            token_status = line.split(":")[1].strip()
        if "SERVICE_STATUS:" in line:
            svc_status = line.split(":")[1].strip()
        if "PING: PONG" in line:
            ping = True
            
    is_healthy = ping and (token_status in ["REGISTERED", "NOT_FOUND"]) and (svc_status in ["ACTIVE", "UNKNOWN"])
    if token_status == "PENDING":
        is_healthy = False
        
    return display_name, is_healthy, svc_status, token_status

def main():
    print("==========================================")
    print(" Gigamon Fabric Health & Registration Check ")
    print("==========================================")
    
    print("[*] Determining Resource Group from Terraform state...")
    rg_cmd = subprocess.run(["terraform", "state", "show", "azurerm_resource_group.rg"], capture_output=True, text=True)
    rg_name = None
    for line in rg_cmd.stdout.splitlines():
        if line.strip().startswith("name ") or line.strip().startswith("name="):
            parts = line.split("=")
            rg_name = parts[1].strip().strip('"') if len(parts) > 1 else line.split()[2].strip('"')
            break
    
    if not rg_name:
        print("[!] Could not determine Resource Group from terraform state. Is the lab deployed?")
        sys.exit(1)
        
    print(f"[*] Resource Group: {rg_name}")
    print("[*] Querying VMs via Azure CLI (this may take 1-2 minutes)...\n")
    
    vms = [
        ("vSeries Node", "connolly-vseries-node"),
        ("UCTV Controller", "connolly-uctv-controller"),
        ("Production VM 1", "connolly-prod-ubuntu-1"),
        ("Production VM 2", "connolly-prod-ubuntu-2")
    ]

    all_healthy = True
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(check_vm, rg_name, disp, name): disp for disp, name in vms}
        
        for future in concurrent.futures.as_completed(futures):
            disp, healthy, svc, token = future.result()
            status_mark = "[+]" if healthy else "[-]"
            print(f"{status_mark} {disp}:")
            print(f"    - Service Status : {svc}")
            print(f"    - Token Status   : {token}")
            if not healthy:
                all_healthy = False
            print()
            
    if all_healthy:
        print("[+] All checked fabric components are responsive and healthy!")
        sys.exit(0)
    else:
        print("[-] Some fabric components are not fully healthy or registered.")
        print("    If Token Status is PENDING, ensure you have uploaded the FM token to Key Vault.")
        sys.exit(1)

if __name__ == "__main__":
    main()