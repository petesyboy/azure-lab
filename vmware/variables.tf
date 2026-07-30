############################################################
# vCenter connection
############################################################

variable "vsphere_server" {
  type        = string
  description = "vCenter server FQDN or IP."
}

variable "vsphere_user" {
  type        = string
  description = "vCenter username."
}

variable "vsphere_password" {
  type        = string
  sensitive   = true
  description = "vCenter password."
}

variable "vsphere_allow_unverified_ssl" {
  type        = bool
  default     = true
  description = "Set to false once vCenter has a trusted certificate."
}

############################################################
# vCenter inventory targets
############################################################

variable "datacenter" {
  type        = string
  description = "vSphere datacenter name."
}

variable "esxi_host" {
  type        = string
  description = "ESXi host name/IP to place the VM on directly (this environment is a standalone host, not a cluster)."
}

variable "datastore" {
  type        = string
  description = "Datastore name for VM disks."
}

variable "network_name" {
  type        = string
  default     = "VM Network"
  description = "Port group for prod1's NIC. FM's VMware connection (MD1-1) uses Platform Tapping, which captures from a source VM's vNIC directly once added in FM - NOT a manually-wired promiscuous port group - so this should be the same ordinary network the other monitored VMs already sit on, not the Gigamon-network-vSwitch0 tap/simulator segment."
}

variable "ubuntu_template_name" {
  type        = string
  description = "Name of a pre-staged Ubuntu vSphere template with open-vm-tools installed, used as the clone source for all VMs in this phase."
}

variable "admin_username" {
  type        = string
  default     = "peter"
  description = "Default user baked into the template (matches the rest of this repo's admin_username convention). Used only for the SSH command in outputs.tf - Terraform doesn't create this user, the template already has it."
}

variable "admin_ssh_public_key" {
  type        = string
  default     = ""
  description = "Your own SSH public key (e.g. the ed25519 one already baked into the template's cloud-config), added alongside the Terraform-generated lab_key.pem. Not sensitive - public keys are safe to commit. Leave blank to skip."
}

############################################################
# SSH traffic generation
############################################################

variable "ssh_traffic_target_ip" {
  type        = string
  default     = "192.168.0.61"
  description = "Host prod1's automated SSH traffic loop connects to - the existing NtopNG VM by default. Not Terraform-managed, so update this if that VM's IP changes."
}

variable "ssh_traffic_target_user" {
  type        = string
  default     = "peter"
  description = "SSH username on the traffic target."
}

############################################################
# VM sizing - see README.md for how this floor was estimated.
# Trimmed to fit a single resource-constrained host (~12GB/~3.5 cores free).
# FM, vSeries, and the Cribl relay's target VM (NtopNG) are all reused, so
# prod1 is the only VM this root actually provisions.
############################################################

variable "prod_num_cpus" {
  type    = number
  default = 1
}

variable "prod_memory_mb" {
  type    = number
  default = 1024
}
