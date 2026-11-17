# Azure Lab – What it builds and how it's linked

> Cribl egress (relay, AMX ogw session, `Cribl-Relay` / `AMX-Ingress` exports) is **disabled by default** (`enable_cribl = false`). The diagrams show the full topology; the Cribl and AMX-session parts only run when it is enabled.

Three views: the Azure resources, the traffic/metadata data flow, and the deployment sequence.

## 1. What gets built (Azure resources)

```mermaid
graph TB
    classDef gig fill:#1f2937,stroke:#4b5563,stroke-width:2px,color:#f3f4f6;
    classDef prod fill:#2563eb,stroke:#3b82f6,stroke-width:2px,color:#ffffff;
    classDef svc fill:#7c3aed,stroke:#a78bfa,stroke-width:2px,color:#ffffff;
    classDef ext fill:#047857,stroke:#34d399,stroke-width:2px,color:#ffffff;

    Operator["Operator PC<br>runme.ps1 → ami-lab-deploy.py<br>Terraform + configure_lab.py"]:::ext
    Cribl["Cribl Cloud<br>HTTPS endpoint :20010"]:::ext

    subgraph RG["Resource Group (project_name)"]
        KV["Key Vault<br>FM API token + SSH key"]:::svc
        SA["Storage Account<br>UCT-V agent .deb"]:::svc
        SHUT["Auto-shutdown<br>19:00 GMT on every VM"]:::svc

        subgraph VNET["VNet"]
            subgraph VIS["Visibility subnet"]
                FM["GigaVUE-FM<br>management + REST API"]:::gig
                UCTVC["UCT-V Controller<br>tap management"]:::gig
                VS["vSeries node<br>mgmt NIC + data NIC"]:::gig
                AMX["AMX node<br>mgmt + 2 data NICs"]:::gig
                TOOL["Tool VM<br>ntopng, ELK, cef-cribl-relay"]:::gig
            end
            subgraph PRD["Production subnet"]
                P1["prod-ubuntu-1<br>UCT-V agent"]:::prod
                P2["prod-ubuntu-2<br>UCT-V agent"]:::prod
            end
        end
    end

    Operator -->|"terraform apply"| RG
    Operator -->|"FM REST API (HTTPS)"| FM
    Operator -->|"SSH register nodes,<br>deploy relay"| UCTVC
    Operator -->|SSH| VS
    Operator -->|SSH| AMX
    Operator -->|SSH| TOOL

    FM --- UCTVC
    UCTVC -->|"controls agents"| P1
    UCTVC -->|"controls agents"| P2
    P1 -.->|"agents fetch token<br>(managed identity)"| KV
    P2 -.-> KV
    P1 -.->|"download .deb"| SA
    P2 -.-> SA
    FM -->|"manages"| VS
    FM -->|"manages"| AMX
    TOOL ==>|"batched HTTPS POST every 5s"| Cribl
```

## 2. How traffic and metadata flow

```mermaid
graph LR
    classDef gig fill:#1f2937,stroke:#4b5563,color:#f3f4f6;
    classDef prod fill:#2563eb,stroke:#3b82f6,color:#ffffff;
    classDef ext fill:#047857,stroke:#34d399,color:#ffffff;
    classDef dead fill:#7f1d1d,stroke:#f87171,color:#ffffff,stroke-dasharray: 5 5;

    P["prod-ubuntu-1 / 2<br>UCT-V agents<br>generate + mirror traffic"]:::prod
    VS["vSeries node<br>session: Azure-Lab-Session<br>map: pass all IPv4"]:::gig

    subgraph TOOLVM["Tool VM"]
        NTOP["ntopng / tcpdump<br>raw packets"]:::gig
        LS["Logstash :1514<br>CEF to Elasticsearch<br>gigamon-ami-* index"]:::gig
        REL["cef-cribl-relay :1515<br>buffers, flushes every 5s"]:::gig
    end

    AMX["AMX node<br>session: Azure-AMX-Session<br>ingress raw to ogw app to egress raw"]:::dead
    CR["Cribl Cloud"]:::ext

    P -->|"UCT-V mirrored traffic"| VS
    VS -->|"Branch A: VXLAN :4789, VNI 123"| NTOP
    VS -->|"Branch B: AMI app (appmetadata)<br>exporter: Elastic, UDP 1514"| LS
    VS -->|"AMI exporter: Cribl-Relay, UDP 1515"| REL
    VS -.->|"AMI exporter: AMX-Ingress, UDP 2055"| AMX
    REL -->|"HTTPS POST + Authorization header"| CR
    AMX -.->|"ogw cloudUpload JSON"| CR
```

Dashed red = wired up but not currently delivering. The README documents an AMX/ogw ingestor bug, so the relay on the Tool VM is the working path to Cribl. On 6.14 the ogw app also needs the AMX connection set to `tappingMethod: none` and `maxEntries` of at least 5000, both now handled in `configure_lab.py.tftpl`.

## 3. Deployment sequence

```mermaid
sequenceDiagram
    autonumber
    participant Op as Operator
    participant Py as ami-lab-deploy.py
    participant TF as Terraform
    participant AZ as Azure
    participant FM as GigaVUE-FM API
    participant N as Nodes and Tool VM (SSH)
    participant KV as Key Vault

    Op->>Py: runme.ps1
    Py->>AZ: bootstrap remote state (RG, storage, container)
    Py->>TF: init + apply
    TF->>AZ: VNet, Key Vault, Storage, 8 VMs, shutdown schedules
    TF->>Py: render scripts/configure_lab.py from .tftpl
    Py->>KV: fetch SSH private key to lab_key.pem
    Py->>FM: wait until API is ready (5-10 min)
    Py->>FM: change default password, create API token
    Py->>KV: upload FM token (agents self-register with it)
    Py->>FM: create monitoring domains and AnyCloud connections
    Note over Py,FM: AMX connection gets tappingMethod none
    Py->>N: register UCT-V controller, vSeries, AMX over SSH
    Py->>N: deploy cef-cribl-relay service to Tool VM
    Py->>FM: main session: map, VXLAN tunnel, AMI app, 3 exporter tunnels, deploy
    Py->>FM: AMX session: raw endpoints, ogw app, interface binding, deploy
    Note over Py,FM: steps retry until nodes finish registering (about 5 min)
```
