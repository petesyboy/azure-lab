# Local values for cloud-init scripts and Ubuntu image details
# These are separated from main.tf to keep it more readable

locals {
  # Gigamon version configuration
  # These locals derive the correct image SKU and version strings from the `gigamon_version` variable.
  gigamon_version_sku_code = replace(var.gigamon_version, ".", "") # e.g., "6.13" -> "613"

  fm_image_sku     = "gfm-azure-v${local.gigamon_version_sku_code}00"
  fm_image_version = "${var.gigamon_version}.00" # NOTE: This was 6.12.1099. Using .00 as a default for the new version.

  uctv_image_sku     = "uctv-cntlr-v${local.gigamon_version_sku_code}00"
  uctv_image_version = "${var.gigamon_version}.00"

  vseries_image_sku     = "vseries-node-v${local.gigamon_version_sku_code}00"
  vseries_image_version = "${var.gigamon_version}.00"

  # Ubuntu image configuration
  ubuntu_publisher = "Canonical"
  ubuntu_offer     = var.ubuntu_version == "24.04" ? "ubuntu-24_04-lts" : "ubuntu-22_04-lts"
  ubuntu_sku       = "server"
  ubuntu_version   = "latest"

  # FM Cloud-Init: Minimal init.
  # Configuration is handled post-deployment via API.
  fm_cloud_init = replace(<<-EOF
    #cloud-config
    packages: []
    runcmd:
      - echo "GigaVUE-FM ${var.gigamon_version} initializing..."
  EOF
  , "\r", "")

  # UCT-V Controller Cloud-Init
  # Configuration is handled post-deployment via SSH direct push.
  uctv_cloud_init = replace(<<-EOF
    #cloud-config
    packages: []
    runcmd:
      - echo "UCT-V Controller initialized. Waiting for configuration via SSH..."
  EOF
  , "\r", "")

  # Reusable Bash Script for fetching tokens from Key Vault
  shared_token_fetch_script = replace(<<-EOF
    #!/usr/bin/env bash
    set -euo pipefail
    LOG="/var/log/gigamon-bootstrap.log"
    exec > >(tee -a "$LOG") 2>&1

    echo "[$(date)] Starting Token Fetch from Key Vault..."
    CONF="/etc/gigamon-cloud.conf"
    KV_NAME="${azurerm_key_vault.fm_token_kv.name}"
    SECRET_NAME="${var.fm_token_secret_name}"
    KV_API_VERSION="7.4"
    if [[ ! -f "$CONF" ]]; then exit 0; fi
    if ! grep -q "PLACEHOLDER_TOKEN" "$CONF"; then
      systemctl disable --now fm-token-fetch.timer >/dev/null 2>&1 || true
      exit 0
    fi
    if ! command -v curl >/dev/null 2>&1; then exit 0; fi

    MSI_JSON="$(curl -sS -H 'Metadata: true' 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fvault.azure.net' || true)"
    ACCESS_TOKEN=""
    if command -v jq >/dev/null 2>&1; then
      ACCESS_TOKEN="$(echo "$MSI_JSON" | jq -r '.access_token // empty' || true)"
    elif command -v python3 >/dev/null 2>&1; then
      ACCESS_TOKEN="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' <<<"$MSI_JSON")"
    else
      ACCESS_TOKEN="$(echo "$MSI_JSON" | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
    fi

    if [[ -z "$ACCESS_TOKEN" ]]; then exit 0; fi
    SECRET_URL="https://$${KV_NAME}.vault.azure.net/secrets/$${SECRET_NAME}?api-version=$${KV_API_VERSION}"
    FM_TOKEN=""
    
    for i in {1..30}; do
      SECRET_JSON="$(curl -sS -H "Authorization: Bearer $${ACCESS_TOKEN}" "$SECRET_URL" || true)"
      if command -v jq >/dev/null 2>&1; then
        FM_TOKEN="$(echo "$SECRET_JSON" | jq -r '.value // empty' || true)"
      else
        FM_TOKEN="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("value",""))' <<<"$SECRET_JSON")"
      fi

      FM_TOKEN="$(echo "$FM_TOKEN" | tr -d '[:space:]')"
      if [[ -n "$FM_TOKEN" && "$FM_TOKEN" != "null" && "$FM_TOKEN" != "<PASTE_FM_TOKEN_HERE>" ]]; then
        break
      fi
      echo "[$(date)] Token is empty or invalid placeholder. Attempting to obtain it again in 10 seconds..."
      sleep 10
    done

    if [[ -z "$FM_TOKEN" || "$FM_TOKEN" == "null" || "$FM_TOKEN" == "<PASTE_FM_TOKEN_HERE>" ]]; then exit 0; fi
    sed -i "s|^\\([[:space:]]*token:\\).*|\\1 $${FM_TOKEN}|" "$CONF"
    echo "[$(date)] Token successfully updated in $CONF"
    systemctl start gigamon-agent-refresh.service >/dev/null 2>&1 || true
    systemctl disable --now fm-token-fetch.timer >/dev/null 2>&1 || true
  EOF
  , "\r", "")

  # Reusable Bash Script for refreshing the agent service
  # Note: ${1} is passed from the cloud-init path definition
  shared_agent_refresh_script = replace(<<-EOF
    #!/usr/bin/env bash
    set -euo pipefail
    LOG="/var/log/gigamon-bootstrap.log"
    exec > >(tee -a "$LOG") 2>&1

    CONF="/etc/gigamon-cloud.conf"
    if [[ ! -f "$CONF" ]] || grep -q "PLACEHOLDER_TOKEN" "$CONF"; then exit 0; fi
    for srv in vseries-node uctv; do
      if systemctl is-enabled "$${srv}" >/dev/null 2>&1; then
        echo "[$(date)] Restarting service: $${srv}"
        systemctl restart "$${srv}"
      fi
    done
  EOF
  , "\r", "")

  # Reusable UCT-V Download logic
  shared_uctv_download_script = replace(<<-EOF
    #!/usr/bin/env bash
    set -euo pipefail
    LOG="/var/log/gigamon-bootstrap.log"
    exec > >(tee -a "$LOG") 2>&1

    echo "[$(date)] Fetching Managed Identity Token for Azure Storage..."
    MSI_JSON="$(curl -sS -H 'Metadata: true' 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fstorage.azure.com%2F' || true)"
    STORAGE_TOKEN=""
    if command -v jq >/dev/null 2>&1; then
      STORAGE_TOKEN="$(echo "$MSI_JSON" | jq -r '.access_token // empty' || true)"
    elif command -v python3 >/dev/null 2>&1; then
      STORAGE_TOKEN="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' <<<"$MSI_JSON")"
    else
      STORAGE_TOKEN="$(echo "$MSI_JSON" | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
    fi

    echo "[$(date)] Downloading UCT-V agent..."
    sleep 20
    AGENT_URL="${azurerm_storage_account.lab_sa.primary_blob_endpoint}${azurerm_storage_container.uctv_container.name}/UCTV-files/gigamon-gigavue-uctv-${local.uctv_image_version}-amd64.deb"
    for i in {1..30}; do
      if [[ -n "$STORAGE_TOKEN" ]]; then
        if curl -fSL --retry 5 -H "Authorization: Bearer $STORAGE_TOKEN" -H "x-ms-version: 2021-08-06" "$${AGENT_URL}" -o /tmp/uctv-agent.deb; then
          echo "Download successful using Managed Identity."
          break
        fi
      else
        if curl -fSL --retry 5 "$${AGENT_URL}" -o /tmp/uctv-agent.deb; then
          echo "Download successful."
          break
        fi
      fi
      sleep 10
    done
    if [ -f /tmp/uctv-agent.deb ]; then
      echo "[$(date)] Installing agent package..."
      dpkg -i /tmp/uctv-agent.deb || DEBIAN_FRONTEND=noninteractive apt-get install -f -y
    else
      echo "ERROR: Failed to download UCT-V agent after 10 attempts."
      WEBHOOK_URL="https://your-webhook.endpoint.here/api/webhook"
      curl -X POST -H "Content-Type: application/json" -d "{\"text\":\"🚨 *Alert*: UCT-V agent download failed on VM **$(hostname)** after 10 retries.\"}" "$${WEBHOOK_URL}" || true
      exit 1
    fi
  EOF
  , "\r", "")

  # Standard runcmd for agents
  agent_standard_runcmd = [
    "systemctl daemon-reload",
    "systemctl enable --now fm-token-fetch.timer",
    "systemctl start fm-token-fetch.service",
    "systemctl enable --now gigamon-agent-refresh.path",
    "systemctl start gigamon-agent-refresh.service",
    "if [ -f /var/run/reboot-required ]; then reboot; fi"
  ]

  # vSeries Cloud-Init
  vseries_cloud_init = replace(<<-EOF
    #cloud-config
    write_files:
      - path: /etc/gigamon-cloud.conf
        permissions: '0644'
        owner: root:root
        content: |
          Registration:
            groupName: ${var.fm_group_name}
            subGroupName: ${var.fm_subgroup_name}
            token: PLACEHOLDER_TOKEN
            remoteAddress: ${module.fm.private_ip}
            remotePort: 443

      - path: /usr/local/sbin/fetch-fm-token-from-keyvault.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(local.shared_token_fetch_script)}

      - path: /etc/systemd/system/fm-token-fetch.service
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Fetch FM token from Azure Key Vault
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=oneshot
          ExecStart=/usr/local/sbin/fetch-fm-token-from-keyvault.sh

      - path: /etc/systemd/system/fm-token-fetch.timer
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Periodically fetch FM token from Azure Key Vault

          [Timer]
          OnBootSec=30s
          OnUnitActiveSec=60s
          RandomizedDelaySec=15s

          [Install]
          WantedBy=timers.target

      - path: /usr/local/sbin/gigamon-agent-refresh.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(local.shared_agent_refresh_script)}

      - path: /etc/systemd/system/gigamon-agent-refresh.service
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Refresh Gigamon agent after config change
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=oneshot
          ExecStart=/usr/local/sbin/gigamon-agent-refresh.sh

      - path: /etc/systemd/system/gigamon-agent-refresh.path
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Watch /etc/gigamon-cloud.conf for changes

          [Path]
          PathChanged=/etc/gigamon-cloud.conf
          Unit=gigamon-agent-refresh.service

          [Install]
          WantedBy=multi-user.target

    runcmd:
      - echo "vSeries Node initialized. Waiting for configuration..."
%{for cmd in local.agent_standard_runcmd~}
      - ${cmd}
%{endfor~}
  EOF
  , "\r", "")

  # Tool VM: ntopng + VXLAN termination
  # Deployed in Visibility Subnet
  tool_vm_cloud_init = replace(<<-EOF
    #cloud-config
    package_upgrade: true
    packages:
      - ntopng
      - ufw
      - curl
      - jq

    write_files:
      # Script to configure VXLAN interface
      - path: /usr/local/sbin/configure-vxlan0.sh
        permissions: '0755'
        owner: root:root
        content: |
          #!/bin/bash
          set -e

          IFACE="eth0"
          VXLAN_IF="vxlan0"
          VNI="123"
          DSTPORT="4789"

          # Get the IPv4 address on the underlying interface (CIDR)
          UNDERLAY_IP=$(ip -4 addr show dev "$${IFACE}" | awk '/inet / {print $2}' | head -n1)

          echo "Configuring $${VXLAN_IF} on $${IFACE} (IP: $${UNDERLAY_IP}) with VNI $${VNI}, dstport $${DSTPORT}"

          # Create vxlan0 if it doesn't exist
          if ! ip link show "$${VXLAN_IF}" >/dev/null 2>&1; then
            ip link add "$${VXLAN_IF}" type vxlan id "$${VNI}" dev "$${IFACE}" dstport "$${DSTPORT}"
          fi

          # Bring interface up
          ip link set "$${VXLAN_IF}" up

      # Systemd service to ensure VXLAN persists across reboots
      - path: /etc/systemd/system/vxlan0.service
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Configure vxlan0 interface
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=oneshot
          ExecStart=/usr/local/sbin/configure-vxlan0.sh
          RemainAfterExit=yes

          [Install]
          WantedBy=multi-user.target

    ssh_authorized_keys:
      - ${tls_private_key.lab_key.public_key_openssh}

    runcmd:
      - systemctl daemon-reload
      - systemctl enable vxlan0.service
      - systemctl start vxlan0.service
      # Configure ntopng interfaces
      - echo "--daemon" > /etc/ntopng.conf
      - echo "-i=eth0" >> /etc/ntopng.conf
      - echo "-i=vxlan0" >> /etc/ntopng.conf
      - systemctl enable ntopng || true
      - systemctl restart ntopng || true
      # Add local firewall exception for VXLAN UDP 4789 (no-op if ufw disabled)
      - ufw allow 4789/udp || true
      # Allow ingress from UCT-V Controller and FM (if needed for tool VM logic)
      - ufw allow from uctv.connolly.lab || true
      - if [ -f /var/run/reboot-required ]; then reboot; fi
  EOF
  , "\r", "")

  # prod1: iperf3 + uctv-agent config placeholder
  # Removed ntopng/vxlan from here
  prod1_cloud_init = replace(<<-EOF
    #cloud-config
    package_upgrade: true
    packages:
      - iperf3
      - curl
      - jq
      - tcpreplay

    write_files:
      # UCT-V Agent Config Placeholder
      - path: /etc/gigamon-cloud.conf
        permissions: '0644'
        owner: root:root
        content: |
          Registration:
            groupName: ${var.fm_group_name}
            subGroupName: ${var.fm_subgroup_name}
            token: PLACEHOLDER_TOKEN
            remoteAddress: ${module.uctv_controller.private_ip}
            remotePort: 8892

      - path: /usr/local/sbin/fetch-fm-token-from-keyvault.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(local.shared_token_fetch_script)}

      - path: /etc/systemd/system/fm-token-fetch.service
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Fetch FM token from Azure Key Vault
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=oneshot
          ExecStart=/usr/local/sbin/fetch-fm-token-from-keyvault.sh

      - path: /etc/systemd/system/fm-token-fetch.timer
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Periodically fetch FM token from Azure Key Vault

          [Timer]
          OnBootSec=30s
          OnUnitActiveSec=60s
          RandomizedDelaySec=15s

          [Install]
          WantedBy=timers.target

      - path: /usr/local/sbin/gigamon-agent-refresh.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(local.shared_agent_refresh_script)}

      - path: /etc/systemd/system/gigamon-agent-refresh.service
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Refresh Gigamon agent after config change
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=oneshot
          ExecStart=/usr/local/sbin/gigamon-agent-refresh.sh

      - path: /etc/systemd/system/gigamon-agent-refresh.path
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Watch /etc/gigamon-cloud.conf for changes

          [Path]
          PathChanged=/etc/gigamon-cloud.conf
          Unit=gigamon-agent-refresh.service

          [Install]
          WantedBy=multi-user.target

      - path: /usr/local/sbin/download-uctv.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(local.shared_uctv_download_script)}

      - path: /usr/local/bin/generate_web_traffic.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(file("${path.module}/scripts/generate_web_traffic.sh"))}

      - path: /usr/local/bin/start_nc_listener.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(file("${path.module}/scripts/start_nc_listener.sh"))}

    ssh_authorized_keys:
      - ${tls_private_key.lab_key.public_key_openssh}

    runcmd:
      - /usr/local/sbin/download-uctv.sh
%{for cmd in local.agent_standard_runcmd~}
      - ${cmd}
%{endfor~}
  EOF
  , "\r", "")

  # prod2: iperf3 + uctv-agent config placeholder
  prod2_cloud_init = replace(<<-EOF
    #cloud-config
    package_upgrade: true
    packages:
      - iperf3
      - curl
      - jq
      - tcpreplay

    write_files:
      # UCT-V Agent Config Placeholder
      - path: /etc/gigamon-cloud.conf
        permissions: '0644'
        owner: root:root
        content: |
          Registration:
            groupName: ${var.fm_group_name}
            subGroupName: ${var.fm_subgroup_name}
            token: PLACEHOLDER_TOKEN
            remoteAddress: ${module.uctv_controller.private_ip}
            remotePort: 8892

      - path: /usr/local/sbin/fetch-fm-token-from-keyvault.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(local.shared_token_fetch_script)}

      - path: /etc/systemd/system/fm-token-fetch.service
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Fetch FM token from Azure Key Vault
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=oneshot
          ExecStart=/usr/local/sbin/fetch-fm-token-from-keyvault.sh

      - path: /etc/systemd/system/fm-token-fetch.timer
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Periodically fetch FM token from Azure Key Vault

          [Timer]
          OnBootSec=30s
          OnUnitActiveSec=60s
          RandomizedDelaySec=15s

          [Install]
          WantedBy=timers.target

      - path: /usr/local/sbin/gigamon-agent-refresh.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(local.shared_agent_refresh_script)}

      - path: /etc/systemd/system/gigamon-agent-refresh.service
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Refresh Gigamon agent after config change
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=oneshot
          ExecStart=/usr/local/sbin/gigamon-agent-refresh.sh

      - path: /etc/systemd/system/gigamon-agent-refresh.path
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Watch /etc/gigamon-cloud.conf for changes

          [Path]
          PathChanged=/etc/gigamon-cloud.conf
          Unit=gigamon-agent-refresh.service

          [Install]
          WantedBy=multi-user.target

      - path: /usr/local/sbin/download-uctv.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(local.shared_uctv_download_script)}

      - path: /usr/local/bin/generate_web_traffic.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(file("${path.module}/scripts/generate_web_traffic.sh"))}

      - path: /usr/local/bin/start_nc_listener.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(file("${path.module}/scripts/start_nc_listener.sh"))}

    ssh_authorized_keys:
      - ${tls_private_key.lab_key.public_key_openssh}

    runcmd:
      - /usr/local/sbin/download-uctv.sh
%{for cmd in local.agent_standard_runcmd~}
      - ${cmd}
%{endfor~}
  EOF
  , "\r", "")
}
