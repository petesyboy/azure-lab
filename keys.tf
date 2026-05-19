############################################################
# SSH Key Generation
############################################################
# This file generates an RSA private key and saves it locally.

resource "tls_private_key" "lab_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "local_file" "lab_key_pem" {
  content         = tls_private_key.lab_key.private_key_pem
  filename        = "${path.module}/lab_key.pem"
  file_permission = "0400"
}