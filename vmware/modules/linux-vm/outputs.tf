############################################################
# vSphere Linux VM Module – Outputs
############################################################

output "private_ip" {
  description = "IP address reported back by VMware Tools/cloud-init once the guest boots."
  value       = vsphere_virtual_machine.vm.default_ip_address
}

output "moid" {
  description = "Managed object ID of the deployed VM."
  value       = vsphere_virtual_machine.vm.moid
}
