output "prod1_ip" {
  value = module.prod1.private_ip
}

output "ssh_private_key_path" {
  value = local_sensitive_file.lab_key_pem.filename
}

output "prod1_ssh_command" {
  description = "Works once the template is cloud-init-clean and lab_key.pem has been added; your own existing key/password against admin_username also works regardless."
  value       = "ssh -i ${local_sensitive_file.lab_key_pem.filename} ${var.admin_username}@${module.prod1.private_ip}"
}
