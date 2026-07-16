# =============================================================================
# Root Variables
# =============================================================================
# This file defines the input variables for the Terraform configuration.
# Variables can be overridden via a `terraform.tfvars` file or `-var` CLI arguments.

# -----------------------------------------------------------------------------
# Region and Project Settings
# -----------------------------------------------------------------------------

variable "location" {
  type        = string
  default     = "uksouth"
  description = "Azure region to deploy resources in. (e.g. uksouth, eastus)"
}

variable "project_name" {
  type        = string
  default     = "connolly-transitory-demo-tf-3po"
  description = "Name of the project/resource group. Used for naming resources and tagging."
}

# -----------------------------------------------------------------------------
# Authentication and Access
# -----------------------------------------------------------------------------

variable "admin_username" {
  type        = string
  default     = "peter"
  description = "Admin username for SSH access to all VMs. Do not use 'admin' or 'root' as they are reserved/blocked by Azure."
}
# Note: For production, consider using Azure Key Vault to manage SSH keys securely.

variable "gigamon_email" {
  type        = string
  description = "Email address used as the owner tag on resources. Useful for resource tracking."
  default     = "pete.connolly@gigamon.com"
}

# -----------------------------------------------------------------------------
# FM Configuration & Credentials
# -----------------------------------------------------------------------------

variable "fm_group_name" {
  type        = string
  description = "Monitoring Domain (Group) name to create on FM."
  default     = "Azure-3PO-MD"
}

variable "fm_subgroup_name" {
  type        = string
  description = "Connection (Sub-Group) name to create on FM."
  default     = "Azure-3PO-Connection"
}

variable "amx_fm_group_name" {
  type        = string
  description = "Monitoring Domain (Group) name to create on FM for AMX."
  default     = "Azure-3PO-AMX"
}

variable "amx_fm_subgroup_name" {
  type        = string
  description = "Connection (Sub-Group) name to create on FM for AMX."
  default     = "Azure-3PO-AMX-Connection"
}

variable "cribl_endpoint" {
  type        = string
  description = "Cribl instance endpoint (e.g. HEC-style URL or host:port) that the AMX/AMI GigaSMART app exports metadata to. Leave empty until the destination is wired up."
  default     = ""
}

variable "cribl_auth_token" {
  type        = string
  description = "Auth token/API key for the Cribl endpoint, if required."
  default     = ""
  sensitive   = true
}

# -----------------------------------------------------------------------------
# General VM Configuration
# -----------------------------------------------------------------------------

variable "ubuntu_version" {
  type        = string
  description = "Ubuntu release to use for VM images. Allowed: \"22.04\" or \"24.04\"."
  default     = "22.04"

  validation {
    condition     = contains(["22.04", "24.04"], var.ubuntu_version)
    error_message = "The ubuntu_version must be either '22.04' or '24.04'."
  }
}

# -----------------------------------------------------------------------------
# VM Sizes (Compute Resources)
# -----------------------------------------------------------------------------
# Adjust these values to scale vertical compute resources.

variable "fm_vm_size" {
  type    = string
  default = "Standard_D4s_v5" # Recommended minimum for GigaVUE-FM
}

variable "uctv_vm_size" {
  type    = string
  default = "Standard_D2s_v5"
}

variable "vseries_vm_size" {
  type    = string
  default = "Standard_D4s_v5" # Adjust based on throughput requirements
}

variable "amx_vm_size" {
  type    = string
  default = "Standard_D8s_v5" # AMX node needs a VM size supporting at least 3 NICs (Standard_D8s_v5 supports up to 4 NICs)
}

variable "ubuntu_vm_size" {
  type    = string
  default = "Standard_B2s" # Burstable series suitable for low-traffic tests
}

variable "tool_vm_size" {
  type    = string
  default = "Standard_D4s_v5" # Tool VM (ntopng + ELK stack) requires more memory
}

# -----------------------------------------------------------------------------
# Gigamon Image References (Azure Marketplace)
# -----------------------------------------------------------------------------
# These variables define the specific version of Gigamon software to deploy.
# Ensure the subscription has accepted terms for these specific image URNs.

variable "gigamon_version" {
  type        = string
  description = "The major.minor version of the Gigamon Cloud Suite to deploy (e.g., '6.13', '6.14'). Defaults to the latest supported release, 6.14; set to '6.13' to pin the previous release."
  default     = "6.14"

  validation {
    condition     = can(regex("^6\\.\\d{2}$", var.gigamon_version))
    error_message = "The gigamon_version must be in the format '6.xx' (e.g., '6.13', '6.14')."
  }
}

variable "gigamon_image_publisher" {
  type    = string
  default = "gigamon-inc"
}

variable "gigamon_image_offer" {
  type    = string
  default = "gigamon-gigavue-cloud-suite-v2"
}

# -----------------------------------------------------------------------------
# Optional: FM API token delivery via Azure Key Vault
# -----------------------------------------------------------------------------
# This avoids putting the FM token into Terraform state and avoids manual "push token over SSH".

variable "fm_token_secret_name" {
  type        = string
  description = "Azure Key Vault secret name that will hold the GigaVUE-FM API token (JWT)."
  default     = "gigamon-fm-token"
}

variable "allowed_mgmt_ip" {
  type        = string
  description = "The IP address or CIDR range allowed for management access (SSH, HTTPS, HTTP, ntopng UI). Set to '*' to allow access from anywhere, or 'dynamic' to restrict it to your current public IP."
  default     = "*"
}
