############################################################
# SSH Key Generation
############################################################
# This file generates an RSA private key and saves it locally.

resource "tls_private_key" "lab_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
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
  # Use the PKCS#1 PEM format ("BEGIN RSA PRIVATE KEY") rather than
  # the OpenSSH format ("BEGIN OPENSSH PRIVATE KEY").  On Windows,
  # OpenSSH-format keys produce "type 0 / no identity pubkey loaded"
  # errors because the Windows SSH client handles the two formats
  # differently and is far stricter about the OpenSSH variant.
  content         = tls_private_key.lab_key.private_key_pem
  filename        = "${path.module}/lab_key.pem"
  file_permission = "0400"
}
