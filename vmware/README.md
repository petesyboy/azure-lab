# VMware / vCenter Lab — Trimmed for Reuse of an Existing Lab

This directory is a **separate, standalone** Terraform root — it does not
touch or depend on the Azure deployment one level up.

## Why this is so much smaller than the Azure lab

The target vCenter (`192.168.0.47`) already has a working lab deployment:
a VMware connection in FM (`MD1-1`) configured with **Traffic Acquisition
Method: Platform Tapping**, plus an existing GigaVUE-FM and one vSeries
node (`VSeries.192.168.0.45-1`). Platform Tapping means FM captures traffic
directly from a source VM's vNIC via the vCenter/ESXi API once that VM is
added as a monitoring source in FM — no per-VM agent install, and no manual
promiscuous-port-group wiring needed. That changes the architecture
significantly compared to the Azure version of this lab:

| Azure lab | This vSphere lab |
|---|---|
| Terraform deploys FM from a Marketplace image | **FM already exists — reused, not deployed** |
| Terraform deploys a UCT-V controller + installs a UCT-V agent on every traffic VM | **No UCT-V** — Platform Tapping captures via the vCenter API, not an installed agent (there is a stray `gigamon-gigavue-uctv-cntlr-static` VM on this host, but it belongs to unrelated earlier experimentation, not this connection) |
| Terraform deploys an AMX node running the `ogw` GigaSMART app for metadata | **No AMX** — this lab only needs raw tapped traffic, not app-metadata generation |
| Terraform deploys a vSeries node from a Marketplace image | **vSeries already exists — reused, not deployed** |

Note the `Gigamon-network-vSwitch0__...` port group (the only one with
promiscuous mode enabled) is **not** the Platform Tapping capture path —
its members (`GigaVUE-TA200E`, `GigaVUE-TA25E`, `GigaVUE-HCT`) are named
after physical Gigamon hardware product lines and look like a separate,
self-contained hardware-simulator network unrelated to this connection.

There's also an existing "Ubuntu 24 - NtopNG" VM on this host, which can run
the CEF→Cribl relay directly — so Terraform doesn't need to deploy a tool VM
either. **Terraform's entire job here is one VM: `prod1`**, a single
traffic-source VM (iperf3/tcpreplay).

The relay itself is [scripts/deploy_cribl_relay.py](scripts/deploy_cribl_relay.py)
— an SSH-push script (same relay logic as the Azure lab's
`deploy_cribl_relay()`), run manually against the existing NtopNG VM since
that VM isn't Terraform-managed. Fill in `TARGET_HOST`/`TARGET_USER`/
`SSH_KEY_PATH`/`CRIBL_ENDPOINT`/`CRIBL_AUTH_TOKEN` at the top and run it
yourself with `python3 scripts/deploy_cribl_relay.py` — it only uses
whatever SSH access you already have to that box (a key or agent), nothing
handled by Claude.

## Host capacity this was sized against

Single ESXi host (`192.168.0.45`, Intel Client Systems / i7-10710U, 6
logical CPUs, 65,242MB RAM), reported at 81.6% RAM / 41.2% CPU already in
use by the existing lab:

- Free RAM: ~11.7GB
- Free CPU: ~5.7GHz (~3.5 cores at the host's current sustained clock)
- Datastore free space: 3,087GB / 223.6GB — not a constraint

New allocation (`prod1` only): **1 vCPU / 1GB** — trivial against that
headroom. The relay reuses an existing VM's spare capacity rather than
consuming any more of the host's budget. The full Azure-lab-equivalent
footprint (~18 vCPU/66GB) was never going to fit this host — reusing the
existing FM/vSeries/NtopNG and dropping UCT-V/AMX/tool-VM is what makes
this workable at all.

## Still manual / not in Terraform

- **Adding `prod1` as a monitoring source in FM after `apply`.** Platform
  Tapping is opt-in per VM through FM (UI or `/cloud/vmware/...` API) —
  Terraform deploying the VM on `VM Network` is necessary but not
  sufficient; it won't be tapped until FM is told to watch it.
- **Running `scripts/deploy_cribl_relay.py`** against the NtopNG VM (see
  above) — not wired into `terraform apply` since that VM isn't managed
  here.
- Confirming the existing vSeries node's export is pointed at the relay's
  UDP port (`LISTEN_PORT` in the relay script, default 1515) — or
  reconfiguring it to do so via FM if not. That's an FM API/UI change
  against the existing session.

## Cloud-init delivery: NoCloud ISO, not vApp properties or guestinfo

Two other approaches were tried first and abandoned - worth knowing if this
ever needs debugging again:

1. **VMware guestinfo** (`extra_config` on the VM) - never worked. This
   template's cloud-init picks the **OVF datasource** over VMware/guestinfo,
   so `guestinfo.userdata` was silently ignored.
2. **OVF vApp properties** (`vapp.properties["user-data"]`) - targeted the
   datasource that's actually active, but proved unreliable in practice on
   the specific template in use at the time (which had accumulated a lot of
   manual history - several rounds of boot/cloud-config/clean/reconvert).
   Also discovered along the way: `vsphere_virtual_machine`'s
   `vapp.properties` replaces the *entire* property map, not a per-key
   patch - setting only `user-data` silently cleared the template's
   `hostname`/`password`/`public-keys` defaults too.

What's actually in use now: `modules/linux-vm` builds a small NoCloud seed
ISO (`scripts/build_nocloud_iso.py`, pure-Python via `pycdlib` - no
`genisoimage`/`mkisofs` dependency) containing `user-data`/`meta-data`,
uploads it to the datastore, and attaches it as a second CD-ROM. cloud-init's
NoCloud datasource is detected purely by the ISO's `cidata` volume label -
no dependency on this template's OVF/vApp behavior at all. Confirmed
working via `cloud-init status --long` showing
`detail: DataSourceNoCloud [seed=/dev/sr0]`.

This only actually proved out on a **freshly imported, never-booted,
never-customized** template (`ubuntu-resolute-26.04-cloudimg`, converted
straight from the stock Canonical OVA) - the original hand-customized
template never got cloud-init working reliably through any of the three
methods, and was abandoned rather than kept debugging. The cloud-init in
`main.tf`'s `prod_cloud_init` is fully self-contained (`user: ${var.admin_username}`
sets up the account itself) specifically so the template needs zero manual
setup - just import the OVA and convert to template.

### Two more cloud-init gotchas hit while adding the traffic generators

Both caused a fresh boot to silently fail (SSH auth denied, or files
missing) with no obvious error until `/var/log/cloud-init.log` was checked
directly - worth knowing before changing `prod_cloud_init` again:

1. **`%{for~}`/`%{endfor~}` inside a `<<-EOT` heredoc corrupts indentation.**
   The chomp (`~`) markers interact badly with the heredoc's own
   indent-stripping and can silently break the entire YAML document's
   structure (not just the loop's own output) - confirmed via a boot where
   cloud-init never even got as far as `ssh_authorized_keys`. Fix: build
   the multi-line block as its own string first (e.g.
   `join("\n", [for k in ... : "      - ${k}"])`) and interpolate it as a
   single `${...}` value instead of using an inline template directive.
   Same reasoning applies to embedding multi-line secrets like a private
   key - use `jsonencode(...)` (single-line, properly escaped), not a
   `content: |` block scalar with manual `indent()` - the latter was tested
   and produced a key `ssh-keygen -y` couldn't even parse.
2. **`write_files` runs before user creation.** Setting `owner: peter:peter`
   on a file under `/home/peter/...` crashes the whole `write_files` module
   (`KeyError: getpwnam(): name not found: 'peter'`) if `peter` hasn't been
   created yet - and takes down every write_files entry after the failing
   one, not just that file. Leave `owner` unset (defaults to root) for
   anything under a not-yet-existing user's home directory, and fix
   ownership afterward in `runcmd` (which runs in the "final" stage, well
   after user creation).

General lesson: after any `prod_cloud_init` change, validate before
spending a ~90s boot cycle - `terraform console` with
`nonsensitive(local.prod_cloud_init)` (if it embeds a sensitive value) or
plain `local.prod_cloud_init`, piped through a real YAML parser
(`python -c "import yaml; yaml.safe_load(...)"`), catches most of these
instantly.

### SSH traffic generation

`prod1` also runs `scripts/generate_ssh_traffic.sh` (via `ssh-traffic.service`),
periodically SSHing into the NtopNG box (`var.ssh_traffic_target_ip`) and
running a few benign commands, alongside `generate_web_traffic.sh`'s DNS/HTTPS
traffic. Uses a dedicated key (`ssh_traffic_key.pem` locally,
`~/.ssh/ssh_traffic_key` on the VM) rather than reusing `lab_key.pem`, so
the two can be rotated/revoked independently. Its public half needs adding
to the target's `authorized_keys` once - already done for the NtopNG box in
this environment.

## Prerequisites

- A vCenter user scoped to clone/deploy VMs into the target
  cluster/datastore/network (avoid using the full Administrator account for
  ongoing Terraform use if you can help it).
- A pristine Ubuntu cloud image template (`var.ubuntu_template_name`) -
  import the official OVA from `cloud-images.ubuntu.com/releases/` and
  convert straight to template, no manual customization needed or
  recommended (see above).
- `pycdlib` installed in the repo's `.venv` (`pip install pycdlib`) - used
  by `scripts/build_nocloud_iso.py`, invoked automatically via a
  `null_resource` provisioner during `apply`.
- SSH access to the existing NtopNG VM (your own key/agent) to run the relay
  deploy script.
