#!/usr/bin/env python3
import subprocess
import sys
import concurrent.futures
import os
import shutil
import platform
import json
import urllib.request

# Resolve az command path for cross-platform compatibility (especially Windows .cmd wrappers)
AZ_CMD = shutil.which("az") or ("az.cmd" if os.name == "nt" else "az")

def ping_host(ip):
    if not ip:
        return "NO IP"
    is_win = platform.system().lower() == 'windows'
    param = '-n' if is_win else '-c'
    timeout_flag = '-w' if is_win else '-W'
    timeout_val = '1000' if is_win else '1'
    cmd = ['ping', param, '1', timeout_flag, timeout_val, ip]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return "SUCCESS" if res.returncode == 0 else "FAILED"
    except Exception:
        return "FAILED"

def check_vm(rg_name, display_name, vm_name, vm_type="linux", vm_ip=None):
    # Perform ping check
    ping_status = ping_host(vm_ip)

    if vm_type == "appliance":
        # Proprietary NVAs block the Azure RunCommand extension.
        # We query the Azure Fabric directly for their PowerState instead.
        cmd = [
            AZ_CMD, "vm", "get-instance-view",
            "--name", vm_name,
            "-g", rg_name,
            "--query", "instanceView.statuses[?starts_with(code, 'PowerState/')].displayStatus",
            "-o", "tsv"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60, shell=(os.name == 'nt'))
            is_running = res.returncode == 0 and "VM running" in res.stdout
            is_healthy = is_running and (ping_status in ["SUCCESS", "NO IP"])
            status_text = "FABRIC OK" if is_running else "NOT RUNNING"
            return display_name, is_healthy, status_text, "APPLIANCE", ping_status, vm_ip
        except subprocess.TimeoutExpired:
            return display_name, False, "TIMEOUT (Azure API)", "UNKNOWN", ping_status, vm_ip

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
        AZ_CMD, "vm", "run-command", "invoke",
        "--command-id", "RunShellScript",
        "--name", vm_name,
        "-g", rg_name,
        "--scripts", script,
        "--query", "value[0].message",
        "-o", "tsv"
    ]
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120, shell=(os.name == 'nt'))
        if res.returncode != 0:
            return display_name, False, "UNREACHABLE", "UNREACHABLE", ping_status, vm_ip
    except subprocess.TimeoutExpired:
        return display_name, False, "TIMEOUT (Azure Agent Busy)", "UNKNOWN", ping_status, vm_ip
        
    out = res.stdout.strip()
    token_status = "UNKNOWN"
    svc_status = "UNKNOWN"
    agent_ping = False
    
    for line in out.splitlines():
        if "TOKEN_STATUS:" in line:
            token_status = line.split(":")[1].strip()
        if "SERVICE_STATUS:" in line:
            svc_status = line.split(":")[1].strip()
        if "PING: PONG" in line:
            agent_ping = True
            
    is_healthy = agent_ping and (token_status in ["REGISTERED", "NOT_FOUND"]) and (svc_status in ["ACTIVE", "UNKNOWN"]) and (ping_status in ["SUCCESS", "NO IP"])
    if token_status == "PENDING":
        is_healthy = False
        
    return display_name, is_healthy, svc_status, token_status, ping_status, vm_ip

def main():
    print("==========================================")
    print(" Gigamon Fabric Health & Registration Check ")
    print("==========================================")
    
    # Fetch deployer public IP
    try:
        my_ip = urllib.request.urlopen("https://ipv4.icanhazip.com", timeout=5).read().decode('utf-8').strip()
    except Exception:
        my_ip = "Unknown"
    print(f"[*] Deployer Public IP: {my_ip}")

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

    # Fetch public IP addresses dynamically
    ip_map = {}
    ip_cmd = [
        AZ_CMD, "vm", "list-ip-addresses",
        "-g", rg_name,
        "--query", "[].{name:virtualMachine.name, publicIp:virtualMachine.network.publicIpAddresses[0].ipAddress}",
        "-o", "json"
    ]
    try:
        res = subprocess.run(ip_cmd, capture_output=True, text=True, timeout=30, shell=(os.name == 'nt'))
        if res.returncode == 0:
            data = json.loads(res.stdout)
            for item in data:
                name = item.get("name")
                ip = item.get("publicIp")
                if name and ip:
                    ip_map[name] = ip
    except Exception as e:
        print(f"[!] Warning: Could not fetch IP addresses: {e}")
    
    vms = [
        ("vSeries Node", "connolly-vseries-node", "appliance"),
        ("AMX Node", "connolly-amx-node", "appliance"),
        ("UCTV Controller", "connolly-uctv-controller", "appliance"),
        ("Production VM 1", "connolly-prod-ubuntu-1", "linux"),
        ("Production VM 2", "connolly-prod-ubuntu-2", "linux")
    ]

    all_healthy = True
    failures = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(vms)) as executor:
        futures = {executor.submit(check_vm, rg_name, disp, name, vtype, ip_map.get(name)): (disp, name, vtype) for disp, name, vtype in vms}
        
        for future in concurrent.futures.as_completed(futures):
            disp, name, vtype = futures[future]
            disp, healthy, svc, token, ping_status, vm_ip = future.result()
            status_mark = "[+]" if healthy else "[-]"
            print(f"{status_mark} {disp}:")
            print(f"    - Service Status : {svc}")
            print(f"    - Token Status   : {token}")
            ip_display = f" ({vm_ip})" if vm_ip else " (No IP)"
            print(f"    - ICMP Ping      : {ping_status}{ip_display}")
            
            if not healthy:
                all_healthy = False
                reasons = []
                if ping_status == "FAILED":
                    reasons.append("ICMP Ping failure")
                if vtype == "appliance" and svc != "FABRIC OK":
                    reasons.append(f"Azure PowerState not running ({svc})")
                if vtype == "linux":
                    if svc == "UNREACHABLE":
                        reasons.append("Azure Agent unreachable")
                    elif token == "PENDING":
                        reasons.append("Token registration pending")
                    elif svc == "INACTIVE":
                        reasons.append("Agent service is INACTIVE")
                failures.append((disp, reasons))
            print()
            
    if all_healthy:
        print("[+] All checked fabric components are responsive and healthy!")
        sys.exit(0)
    else:
        print("[-] Some fabric components are not fully healthy or registered:")
        for disp, reasons in failures:
            reasons_str = ", ".join(reasons) if reasons else "Unknown reason"
            print(f"    - {disp}: unhealthy due to {reasons_str}")
        sys.exit(1)

if __name__ == "__main__":
    main()