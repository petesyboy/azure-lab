############################################################
# vSphere Linux VM Module
############################################################
# Injects cloud-init via a NoCloud seed ISO (volume label "cidata",
# user-data + meta-data at its root) rather than OVF vApp properties or
# VMware guestinfo. Both of those were tried first and abandoned: this
# template's cloud-init picks the OVF datasource, whose "user-data"/
# "public-keys" vApp properties turned out unreliable in practice (see
# vmware/README.md for the full story). NoCloud via a real CD-ROM is the
# well-documented, provider-agnostic path and doesn't depend on this
# template's specific OVF property behavior at all.
#
# The ISO is built locally (scripts/build_nocloud_iso.py, pycdlib - no
# native genisoimage/mkisofs dependency) and uploaded to the same
# datastore the VM lives on. Its filename includes a content hash so a
# cloud-init change forces both a rebuild and a re-upload.
#
# This module intentionally mirrors the interface shape of
# ../../../modules/linux-vm (the Azure version) so the two stay easy
# to compare, but it is NOT a drop-in replacement - see root
# vmware/README.md for what's still missing (FM/vSeries/AMX).
############################################################

locals {
  # abspath(), not a bare path.root interpolation - a leading "./" (what
  # "${path.root}/..." produces when run from within path.root itself)
  # confuses cmd.exe's tokenizer on Windows local-exec.
  root_abs        = abspath(path.root)
  cloud_init_hash = substr(md5(var.cloud_init_userdata), 0, 8)
  nocloud_dir     = "${local.root_abs}/.nocloud"
  user_data_path  = "${local.nocloud_dir}/${var.vm_name}-user-data.yaml"
  iso_filename    = "nocloud-${var.vm_name}-${local.cloud_init_hash}.iso"
  iso_local_path  = "${local.nocloud_dir}/${local.iso_filename}"
  venv_python     = abspath("${local.root_abs}/../.venv/Scripts/python.exe")
  build_script    = "${local.root_abs}/scripts/build_nocloud_iso.py"
}

resource "local_file" "user_data" {
  filename = local.user_data_path
  content  = var.cloud_init_userdata
}

resource "null_resource" "build_iso" {
  triggers = {
    content_hash = local.cloud_init_hash
    vm_name      = var.vm_name
  }

  # No quoting - Terraform's local-exec on Windows double-escapes manually
  # quoted args passed through cmd /C, corrupting the path. None of these
  # values contain spaces (repo path, vm_name), so plain space-separation
  # works and avoids that entirely.
  provisioner "local-exec" {
    command = "${local.venv_python} ${local.build_script} ${local.user_data_path} ${var.vm_name} ${local.iso_local_path}"
  }

  depends_on = [local_file.user_data]
}

resource "vsphere_file" "nocloud_iso" {
  datacenter         = var.datacenter_name
  datastore          = var.datastore_name
  source_file        = local.iso_local_path
  destination_file   = "nocloud/${local.iso_filename}"
  create_directories = true

  # The filename is content-hash-suffixed, so the old and new ISO never
  # collide - safe to create the new one before destroying the old, which
  # is required anyway: the old file is still mounted on the live VM's
  # CD-ROM until the VM resource itself updates to point at the new one.
  lifecycle {
    create_before_destroy = true
  }

  depends_on = [null_resource.build_iso]
}

resource "vsphere_virtual_machine" "vm" {
  name             = var.vm_name
  resource_pool_id = var.resource_pool_id
  datastore_id     = var.datastore_id
  folder           = var.folder

  num_cpus = var.num_cpus
  memory   = var.memory_mb
  guest_id = var.guest_id

  network_interface {
    network_id = var.network_id
  }

  disk {
    label            = "disk0"
    size             = var.disk_size_gb
    thin_provisioned = true
  }

  # Satisfies vSphere's "requires a client CDROM device to deliver vApp
  # properties" requirement (this template still has them defined, even
  # though we no longer manage/rely on them - see header comment).
  cdrom {
    client_device = true
  }

  # The actual cloud-init seed.
  cdrom {
    datastore_id = var.datastore_id
    path         = vsphere_file.nocloud_iso.destination_file
  }

  clone {
    template_uuid = var.template_uuid
  }

  lifecycle {
    ignore_changes = [
      clone[0].template_uuid,
    ]
  }
}
