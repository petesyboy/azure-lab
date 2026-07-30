################################################################################
# VMWARE / VCENTER LAB - PHASE 1 (TRIMMED FOR EXISTING LAB REUSE)
#
# This lab already has GigaVUE-FM, a vSeries node, and an NtopNG box running
# on it. So unlike the Azure lab: no UCT-V, no AMX, no new FM/vSeries, and
# no new tool VM either - the CEF->Cribl relay runs on the existing NtopNG
# VM via scripts/deploy_cribl_relay.py (SSH push, run manually - that VM
# isn't Terraform-managed). Terraform's whole job here is one VM: `prod1`.
# See ./README.md for the full reasoning and what's still manual.
################################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    vsphere = {
      source  = "hashicorp/vsphere"
      version = "~> 2.7"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.3"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

provider "vsphere" {
  user                 = var.vsphere_user
  password             = var.vsphere_password
  vsphere_server       = var.vsphere_server
  allow_unverified_ssl = var.vsphere_allow_unverified_ssl
}

############################################################
# Data sources - existing vCenter inventory
############################################################

data "vsphere_datacenter" "dc" {
  name = var.datacenter
}

# This host isn't in a cluster (confirmed via its inventory path,
# /Datacenter/host/192.168.0.45/192.168.0.45 - vCenter only nests a host
# under a folder named after itself like that for a standalone host, not a
# real cluster), so this targets the host directly rather than using
# vsphere_compute_cluster, which looks for an actual ClusterComputeResource
# and would find nothing here.
data "vsphere_host" "esxi_host" {
  name          = var.esxi_host
  datacenter_id = data.vsphere_datacenter.dc.id
}

data "vsphere_datastore" "datastore" {
  name          = var.datastore
  datacenter_id = data.vsphere_datacenter.dc.id
}

data "vsphere_network" "lab_network" {
  name          = var.network_name
  datacenter_id = data.vsphere_datacenter.dc.id
}

# Pre-staged template: Ubuntu cloud image imported as a vSphere template,
# with open-vm-tools installed so cloud-init can read guestinfo. This repo
# does not build that template - it must exist in vCenter before `apply`.
data "vsphere_virtual_machine" "ubuntu_template" {
  name          = var.ubuntu_template_name
  datacenter_id = data.vsphere_datacenter.dc.id
}

############################################################
# SSH key (same pattern as the Azure lab's keys.tf, minus Key Vault)
############################################################

resource "tls_private_key" "lab_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "local_sensitive_file" "lab_key_pem" {
  content         = tls_private_key.lab_key.private_key_pem
  filename        = "${path.module}/lab_key.pem"
  file_permission = "0400"
}

############################################################
# SSH traffic-generation key
############################################################
# Dedicated key for prod1 -> ssh_traffic_target_ip automation, kept
# separate from lab_key.pem (operator access) so the two can be rotated or
# revoked independently. Private key goes onto prod1 via cloud-init; the
# public key needs adding to the target's authorized_keys once (done via
# ssh_public_keys_to_authorize.sh below, or by hand).

resource "tls_private_key" "ssh_traffic_key" {
  algorithm = "ED25519"
}

resource "local_sensitive_file" "ssh_traffic_key_pem" {
  content         = tls_private_key.ssh_traffic_key.private_key_openssh
  filename        = "${path.module}/ssh_traffic_key.pem"
  file_permission = "0400"
}

############################################################
# Cloud-init
############################################################

locals {
  # Include the user's own key alongside the generated one, when given -
  # gives a second way in independent of lab_key.pem specifically.
  prod_ssh_keys = compact([
    tls_private_key.lab_key.public_key_openssh,
    var.admin_ssh_public_key,
  ])

  # Pre-rendered as its own YAML block and interpolated as a single value
  # below, rather than using an inline %{for~}/%{endfor~} directive - that
  # combined badly with the heredoc's own indent-stripping and silently
  # corrupted the whole document's YAML structure (confirmed via a failed
  # boot: cloud-init never even got as far as ssh_authorized_keys).
  prod_ssh_keys_yaml = join("\n", [for k in local.prod_ssh_keys : "      - ${k}"])

  # Same placeholder-token + replace() pattern already used for the Cribl
  # relay script (scripts/deploy_cribl_relay.py's RELAY_SCRIPT_TEMPLATE) -
  # deliberately not templatefile(), since that would try to interpret the
  # script's own native bash ${...} variable syntax as Terraform expressions.
  ssh_traffic_script = replace(
    replace(
      file("${path.root}/scripts/generate_ssh_traffic.sh"),
      "__TARGET_USER__", var.ssh_traffic_target_user
    ),
    "__TARGET_HOST__", var.ssh_traffic_target_ip
  )

  # Traffic-source VM: just enough to generate/receive test traffic that
  # Platform Tapping can pick up once prod1 is added as a source in FM.
  #
  # Sets up admin_username as the default user itself via the `user:`
  # shorthand, rather than assuming it already exists - a stock Canonical
  # OVA defaults to "ubuntu", not "peter". Self-contained: doesn't depend
  # on anything being pre-baked into the template.
  prod_cloud_init = <<-EOT
    #cloud-config
    user: ${var.admin_username}
    package_upgrade: true
    packages:
      - iperf3
      - curl
      - jq
      - tcpreplay
    ssh_authorized_keys:
    ${local.prod_ssh_keys_yaml}
    write_files:
      - path: /usr/local/bin/generate_web_traffic.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(file("${path.root}/../scripts/generate_web_traffic.sh"))}
      - path: /etc/systemd/system/web-traffic.service
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Automated Web Traffic Generator
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=simple
          ExecStart=/usr/local/bin/generate_web_traffic.sh
          Restart=always
          RestartSec=5

          [Install]
          WantedBy=multi-user.target
      - path: /home/${var.admin_username}/.ssh/ssh_traffic_key
        permissions: '0600'
        # owner deliberately not set to peter:peter here - write_files runs
        # before user creation in this cloud-init's module order, so
        # chown-ing to a not-yet-existing user crashes the whole module
        # (confirmed via /var/log/cloud-init.log: KeyError on getpwnam).
        # runcmd below fixes ownership once the user actually exists.
        content: ${jsonencode(tls_private_key.ssh_traffic_key.private_key_openssh)}
      - path: /usr/local/bin/generate_ssh_traffic.sh
        permissions: '0755'
        owner: root:root
        content: ${jsonencode(local.ssh_traffic_script)}
      - path: /etc/systemd/system/ssh-traffic.service
        permissions: '0644'
        owner: root:root
        content: |
          [Unit]
          Description=Automated SSH Traffic Generator
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=simple
          User=${var.admin_username}
          ExecStart=/usr/local/bin/generate_ssh_traffic.sh
          Restart=always
          RestartSec=5

          [Install]
          WantedBy=multi-user.target
    runcmd:
      - mkdir -p /home/${var.admin_username}/.ssh && chmod 700 /home/${var.admin_username}/.ssh && chown ${var.admin_username}:${var.admin_username} /home/${var.admin_username}/.ssh
      - chmod 600 /home/${var.admin_username}/.ssh/ssh_traffic_key && chown ${var.admin_username}:${var.admin_username} /home/${var.admin_username}/.ssh/ssh_traffic_key
      - systemctl enable --now web-traffic.service
      - systemctl enable --now ssh-traffic.service
  EOT
}

############################################################
# VMs
############################################################
# NOT here: GigaVUE-FM, UCT-V controller, vSeries node, AMX node, tool VM -
# FM/vSeries already exist in this vCenter; UCT-V/AMX aren't needed under
# Platform Tapping; and the CEF->Cribl relay runs on the existing NtopNG VM
# (see scripts/deploy_cribl_relay.py) instead of a new VM. See README.md.

module "prod1" {
  source = "./modules/linux-vm"

  vm_name             = "connolly-prod-ubuntu-1"
  resource_pool_id    = data.vsphere_host.esxi_host.resource_pool_id
  datastore_id        = data.vsphere_datastore.datastore.id
  datacenter_name     = var.datacenter
  datastore_name      = var.datastore
  network_id          = data.vsphere_network.lab_network.id
  template_uuid       = data.vsphere_virtual_machine.ubuntu_template.id
  num_cpus            = var.prod_num_cpus
  memory_mb           = var.prod_memory_mb
  cloud_init_userdata = local.prod_cloud_init
}
