#!/usr/bin/env python3
"""
Builds a NoCloud cloud-init seed ISO: a small ISO 9660 image, volume label
CIDATA, containing user-data and meta-data at its root. cloud-init's NoCloud
datasource detects this purely by volume label - no vApp/OVF properties, no
VMware guestinfo, no network dependency. Chosen after the vApp-properties
approach proved unreliable against this template's OVF datasource behavior
(see vmware/README.md).

Usage: python build_nocloud_iso.py <user_data_file> <instance_id> <output_iso>
"""
import sys
import pycdlib


def main():
    if len(sys.argv) != 4:
        print("Usage: build_nocloud_iso.py <user_data_file> <instance_id> <output_iso>", file=sys.stderr)
        sys.exit(1)

    user_data_path, instance_id, output_iso = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(user_data_path, "rb") as f:
        user_data = f.read()

    meta_data = f"instance-id: {instance_id}\nlocal-hostname: {instance_id}\n".encode("utf-8")

    iso = pycdlib.PyCdlib()
    iso.new(joliet=3, vol_ident="cidata")

    iso.add_fp(
        __import__("io").BytesIO(user_data), len(user_data),
        "/USERDATA.;1", joliet_path="/user-data",
    )
    iso.add_fp(
        __import__("io").BytesIO(meta_data), len(meta_data),
        "/METADATA.;1", joliet_path="/meta-data",
    )

    iso.write(output_iso)
    iso.close()
    print(f"Wrote {output_iso}")


if __name__ == "__main__":
    main()
