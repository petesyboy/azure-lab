############################################################
# SSH Key Generation
############################################################
# This file generates an ED25519 private key and saves it locally.

resource "tls_private_key" "lab_key" {
  algorithm = "ED25519"
}

resource "azurerm_key_vault_secret" "lab_key" {
  name         = "lab-ssh-private-key"
  value        = tls_private_key.lab_key.private_key_openssh
  key_vault_id = azurerm_key_vault.fm_token_kv.id

  depends_on = [
    azurerm_role_assignment.kv_secrets_officer_current_user
  ]
}

resource "local_sensitive_file" "lab_key_pem" {
  content         = tls_private_key.lab_key.private_key_openssh
  filename        = "${path.module}/lab_key.pem"
  file_permission = "0400"
}
