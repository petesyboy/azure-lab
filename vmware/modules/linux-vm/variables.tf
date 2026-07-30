############################################################
# vSphere Linux VM Module – Variables
############################################################

variable "vm_name" {
  type        = string
  description = "Name of the VM."
}

variable "resource_pool_id" {
  type        = string
  description = "Resource pool (or cluster root resource pool) to place the VM in."
}

variable "datastore_id" {
  type        = string
  description = "Datastore to place the VM's disks on."
}

variable "datacenter_name" {
  type        = string
  description = "Datacenter name (not ID) - required by vsphere_file for the NoCloud ISO upload."
}

variable "datastore_name" {
  type        = string
  description = "Datastore name (not ID) - required by vsphere_file for the NoCloud ISO upload."
}

variable "folder" {
  type        = string
  default     = null
  description = "Optional vSphere VM folder path."
}

variable "network_id" {
  type        = string
  description = "Port group / network ID for the VM's primary NIC."
}

variable "template_uuid" {
  type        = string
  description = "Managed object ID of the source template to clone."
}

variable "num_cpus" {
  type        = number
  description = "Number of vCPUs."
}

variable "memory_mb" {
  type        = number
  description = "Memory in MB."
}

variable "disk_size_gb" {
  type        = number
  default     = 20
  description = "OS disk size in GB. Must be >= the template's disk size."
}

variable "guest_id" {
  type        = string
  default     = "ubuntu64Guest"
  description = "vSphere guest OS identifier."
}

variable "cloud_init_userdata" {
  type        = string
  description = "Raw #cloud-config userdata, delivered via a NoCloud seed ISO."
}
