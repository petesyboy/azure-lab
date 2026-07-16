# Azure Lab: Gigamon V Series Cloud Tap Deployment v1.0

This repository contains Terraform Infrastructure-as-Code (IaC) and Python automation to deploy a complete Gigamon V Series traffic visibility lab in Microsoft Azure.

## TL;DR / Quick Start

The deployment wrapper scripts (`runme.sh`, `runme.bat`, `runme.ps1`) handle environment setup, dependency installation, Terraform execution, and will output the total elapsed deployment time upon completion.

### Mac / Linux
```bash
bash runme.sh
```

### Windows
```powershell
.\runme.ps1
```

## Prerequisites & Marketplace Terms
Ensure you have Terraform >= 1.5.0, Azure CLI, and Python 3 installed.

> [!IMPORTANT]
> **UCT-V Agent Package Requirement**  
> Prior to running the deployment script, you **must** place the UCT-V agent Debian package (e.g., `gigamon-gigavue-uctv-6.xx.00-amd64.deb` matching your configured `gigamon_version` in `variables.tf`) in the `UCTV-files` directory. The deployment script performs a pre-flight check to verify this file exists and will halt with an error if it is missing.

You **must** accept the Azure Marketplace terms for the Gigamon images before deploying:


```bash
az vm image terms accept --publisher gigamon-inc --offer gigamon-gigavue-cloud-suite-v2 --plan gfm-azure-v61300
az vm image terms accept --publisher gigamon-inc --offer gigamon-gigavue-cloud-suite-v2 --plan uctv-cntlr-v61300
az vm image terms accept --publisher gigamon-inc --offer gigamon-gigavue-cloud-suite-v2 --plan vseries-node-v61300
```

## Architecture Overview

```mermaid
graph TD
    %% Styling
    classDef prod fill:#2563eb,stroke:#3b82f6,stroke-width:2px,color:#ffffff;
    classDef vis fill:#1f2937,stroke:#4b5563,stroke-width:2px,color:#f3f4f6;

    subgraph Production Subnet
        Prod["Production Systems<br>(UCT-V Agent Workloads)"]:::prod
    end

    subgraph Visibility Subnet
        vSeries["v-Series Node<br>(Traffic Processing)"]:::vis
        
        Tool["Tool VM<br>(Raw Packet Dump & Traffic Analysis via ntopng)"]:::vis
        
        AMI["AMI VM<br>(Transformed to Metadata as CEF)"]:::vis
        AMX["AMX Server<br>(Converted to JSON)"]:::vis
        CloudTool["Cloud Tool<br>(Logstash/Elastic on Tool VM or Cribl Cloud)"]:::vis
    end

    %% Flow Paths
    Prod -->|Mirrored Traffic| vSeries
    
    %% Branch A: Raw Packets
    vSeries -->|Branch A: Raw VXLAN| Tool
    
    %% Branch B: Metadata Pipeline
    vSeries -->|Branch B: Mirrored Traffic| AMI
    AMI -->|AMI Metadata| AMX
    AMX -->|JSON/CEF over UDP| CloudTool
```

- **Networking**: Single VNet with two subnets (Visibility and Production).
- **Gigamon Fabric**: GigaVUE-FM (Management), UCT-V Controller (Tap Management), vSeries & AMX Nodes (Traffic Processing).
- **Workloads**: 
  - **Tool VM**: Sink for mirrored traffic, ntopng, and ELK stack (Elasticsearch, Logstash, Kibana) for ingesting Application Metadata Intelligence (AMI) records (Visibility Subnet).
  - **Production VMs**: Ubuntu workloads for traffic generation (Production Subnet).

## Post-Deployment Configuration (CRITICAL)
GigaVUE-FM requires a manual password change and token generation before the fabric can register.

1. **Access GigaVUE-FM**: Open `https://<fm_public_ip>` (IP found via `terraform output`).
2. **Login & Change Password**: Use `admin` / `admin123A!!`. Uncheck SSH Key-Based Auth.
3. **Generate Token**: Navigate to **Administration → User Management → Tokens → Current User Tokens**. Create a new token (105 days, Super Admin Group) and **copy it**.
4. **Upload Token to Key Vault**:

### Bash / Linux
```bash
KV_NAME="$(terraform output -raw key_vault_name)"
SECRET_NAME="$(terraform output -raw fm_token_secret_name)"
az keyvault secret set --vault-name "$KV_NAME" --name "$SECRET_NAME" --value "<PASTE_FM_TOKEN_HERE>"
```

### PowerShell / Windows
```powershell
$KV_NAME = terraform output -raw key_vault_name
$SECRET_NAME = terraform output -raw fm_token_secret_name
az keyvault secret set --vault-name $KV_NAME --name $SECRET_NAME --value "<PASTE_FM_TOKEN_HERE>"
```
*Note: Agents automatically fetch this token from the Key Vault via managed identity to self-register. They will continually retry every 60 seconds until a valid token is found.*

## Monitoring Session (Automated)

`scripts/configure_lab.py` fully automates both Monitoring Sessions — no manual steps in the FM UI are required. It's idempotent throughout: re-running it detects whatever already exists (domain, session, map, tunnel, app, link) and only creates/deploys what's missing, so it's always safe to run again.

It's also self-healing across a fresh deploy: FM rejects a session deploy or link change until the corresponding vSeries/AMX node has finished registering, which lags a few minutes behind the SSH-based node registration. Rather than requiring a second manual invocation, the script waits for each node to appear registered and then retries the session build/deploy until it succeeds (bounded timeout, ~5 minutes).

### Main session — `Azure-Lab-Session` (vSeries node, domain `Azure-3PO-MD`)

1. Creates the Monitoring Domain and AnyCloud Connection.
2. Creates the session and a traffic map with a pass-all-IPv4 rule.
3. **Branch A — raw packet mirror**: creates a VXLAN tunnel to the Tool VM's private IP, port `4789`, VNI `123` *(the Tool VM's automated configuration expects VNI `123` — do not change without updating both sides)*, and links the map to it. Feeds ntopng / raw `tcpdump` on the Tool VM.
4. **Branch B — metadata pipeline**: adds the AMI ("Application Metadata Intelligence" / `appmetadata`) GigaSMART app to the map, using the `SplunkMetadataTemplate` export profile (CEF-formatted, per-protocol field extraction for krb5/ssh/ssl/ftp/smb/smtp/dhcp/dns/telnet/rdp/http). The AMI app exports to two UDP destinations:
   - **Elastic**: the Tool VM's Logstash listener, port `1514` (already provisioned with a CEF codec writing into the `gigamon-ami-*` Elasticsearch index — see [Verify AMI](#4-verify-application-metadata-intelligence-ami) below).
   - **AMX-Ingress**: the AMX node's ingress data interface (`eth1`), so the same metadata also reaches the AMX session below.
5. Deploys the session.

### AMX session — `Azure-AMX-Session` (AMX node, domain `Azure-3PO-AMX`)

1. Creates the Monitoring Domain and AnyCloud Connection.
2. Creates the session and a traffic map.
3. Creates `Ingress-Raw-Endpoint` and `Egress-Raw-Endpoint` entities and links them as Ingress → Map → Egress.
4. Binds the raw endpoints to the AMX node's two data interfaces (`eth1`/`eth2`) via `endpointIfaceMappings`.
5. Deploys the session.

**Status: not yet complete.** The AMX node currently receives the CEF metadata (from the main session's AMI app, above) on its ingress interface, but nothing yet converts it to JSON or forwards it onward — the AMX-side GigaSMART app and the final Cribl destination on the egress interface are still unconfigured, pending the Cribl endpoint details and a corresponding FM UI capture. Once available, the egress tunnel to Cribl follows the same `create_udp_tunnel()` pattern already used for Elastic.

If you need to build the session manually instead (e.g. for a custom traffic rule), use **Traffic** > **Virtual** > **Orchestrated Flows** > **Azure** in the FM UI and mirror the steps above.

## Usage & Verification

### 1. SSH Access
Retrieve ready-to-use SSH commands from Terraform:

#### Bash / Linux
```bash
terraform output | grep ssh_
```

#### PowerShell / Windows
```powershell
terraform output | Select-String "ssh_"
```
*(Example: `ssh -i ./lab_key.pem peter@<ip>`)*


### 2. Generate Traffic
You can generate test traffic using the provided web traffic simulation script or manually via `iperf3`.

**Option A: Web Traffic Simulation**
A script is provided to simulate staggered DNS and HTTP/HTTPS requests to over 500 websites.
This script is automatically deployed to the production VMs during provisioning.
1. SSH into one of the Production VMs.
2. Run the script: `/usr/local/bin/generate_web_traffic.sh`

**Option B: iPerf3**
Run `iperf3` between the two production VMs to generate inspectable traffic:
- **On Prod VM 2 (Server):** `iperf3 -s`
- **On Prod VM 1 (Client):** `iperf3 -c <prod2_private_ip> -t 300`

**Option C: UDP Barrage (Python)**
A Python script is provided to generate a high volume of UDP messages to the netcat listener.
- **On Prod VM 2 (Server):** Run `/usr/local/bin/start_nc_listener.sh`
- **On Prod VM 1 (Client):** Run `udp_barrage.py <prod2_private_ip> --count 5000`

### 3. Verify Visibility
- **ntopng**: Access `http://<tool_vm_public_ip>:3000` (admin/admin), select the `vxlan0` interface to see real-time mirrored traffic.
- **Raw Packet Dump**: Run `sudo tcpdump -i vxlan0 -n` on the Tool VM.

### 4. Verify Application Metadata Intelligence (AMI)
- **Kibana**: Access `http://<tool_vm_public_ip>:5601`.
- Create a Data View in Kibana matching `gigamon-ami-*` to visualize the parsed metadata records.
- This is fully automated (see [Monitoring Session (Automated)](#monitoring-session-automated) above) — no manual FM configuration needed. Traffic should already be flowing once `configure_lab.py` completes.

---

---

## Troubleshooting

**Configuration Script Fails (SSH Delay):**
If the final step of the deployment script (`configure_lab.py`) fails due to an SSH timeout (VMs are fully provisioned but SSH daemons are not yet responsive), the underlying infrastructure was still successfully deployed. You can safely retry the post-deployment SSH configuration at any time by running:
`python scripts/configure_lab.py`

**vSeries/AMX Node Landed on Unsupported Hardware (MANA):**
Gigamon's DPDK build doesn't yet support Azure's newer MANA network adapter. If a vSeries or AMX node's data interface fails to bind (`dpdk-devbind.py --status` shows it `unused` rather than bound to a kernel driver, and `vseries-node` logs repeat `Error: No devices specified`), the VM landed on MANA-capable hardware. All Gigamon Marketplace VMs in this repo carry the `LegacyVMNVA` tag (Azure's documented NVA opt-out — see [modules/gigamon-vm/main.tf](modules/gigamon-vm/main.tf)), which should prevent this on a fresh deploy. If it still happens, force a re-placement:
```bash
az vm deallocate --resource-group <rg_name> --name <vm_name>
az vm start --resource-group <rg_name> --name <vm_name>
```
A `reapply` alone is not sufficient — it only re-asserts the tag on the VM's *current* allocation, it doesn't trigger a fresh hardware placement decision.

## Support & Contact
For questions, issues, or contributions regarding this lab configuration, please reach out to:
* **Contact**: [pete.connolly@gigamon.com][def]
