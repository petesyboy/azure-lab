############################################################
# Networking Module – VNets, Subnets, NSGs
############################################################

variable "resource_group_name" {
  type        = string
  description = "Name of the resource group."
}

variable "location" {
  type        = string
  description = "Azure region."
}

variable "owner_email" {
  type        = string
  description = "Email address for owner tag."
}

variable "project_tag" {
  type        = string
  description = "Value for the Project tag."
}

variable "allowed_mgmt_ip" {
  type        = string
  description = "The IP address or CIDR range allowed for management access."
}