#!/usr/bin/env python3
"""
Deploys the CEF -> Cribl relay to an existing VM (e.g. the NtopNG box already
running in this vCenter) via SSH. Same relay logic as the Azure lab's
deploy_cribl_relay() in scripts/configure_lab.py.tftpl - this is standalone
because the target VM here is pre-existing and not managed by vmware/main.tf,
so there's no Terraform-rendered version of this script.

Fill in the config block below, then run:
    python3 deploy_cribl_relay.py

Requires SSH access to TARGET_HOST as TARGET_USER using SSH_KEY_PATH (or
whatever key/agent your `ssh` already uses if you leave SSH_KEY_PATH as None -
i.e. this script does not need or handle any password).
"""
import subprocess
import sys

# -----------------------------------------------------------------------
# Config - fill these in for your environment
# -----------------------------------------------------------------------
TARGET_HOST = ""  # e.g. "192.168.0.xx" - the NtopNG VM's IP
TARGET_USER = ""  # e.g. "ubuntu"
SSH_KEY_PATH = None  # e.g. "/path/to/key.pem", or None to use your default SSH identity/agent

LISTEN_PORT = 1515
CRIBL_ENDPOINT = ""  # e.g. "https://xxx.cribl.cloud/services/collector/..."
CRIBL_AUTH_TOKEN = ""  # Authorization header value
BATCH_INTERVAL_SECONDS = 5
# -----------------------------------------------------------------------

RELAY_SCRIPT_TEMPLATE = '''#!/usr/bin/env python3
import socket
import threading
import time
import urllib.request
import urllib.error
import logging

LISTEN_PORT = __PORT__
CRIBL_ENDPOINT = "__CRIBL_ENDPOINT__"
CRIBL_AUTH_TOKEN = "__CRIBL_AUTH_TOKEN__"
BATCH_INTERVAL_SECONDS = __BATCH_INTERVAL__

logging.basicConfig(
    filename="/var/log/cef-cribl-relay.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

_buffer = []
_lock = threading.Lock()


def flush_loop():
    while True:
        time.sleep(BATCH_INTERVAL_SECONDS)
        with _lock:
            if not _buffer:
                continue
            batch = _buffer[:]
            _buffer.clear()
        payload = "\\n".join(batch).encode("utf-8")
        req = urllib.request.Request(
            CRIBL_ENDPOINT,
            data=payload,
            headers={"Authorization": CRIBL_AUTH_TOKEN, "Content-Type": "text/plain"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                logging.info("Sent %d records (%d bytes) - HTTP %s", len(batch), len(payload), resp.status)
        except urllib.error.HTTPError as e:
            logging.error("Cribl POST failed: HTTP %s %s", e.code, e.read()[:200])
        except Exception as e:
            logging.error("Cribl POST failed: %s", e)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", LISTEN_PORT))
    logging.info(
        "Listening on UDP :%d, batching every %ds to %s", LISTEN_PORT, BATCH_INTERVAL_SECONDS, CRIBL_ENDPOINT
    )
    threading.Thread(target=flush_loop, daemon=True).start()
    while True:
        data, _ = sock.recvfrom(65535)
        with _lock:
            _buffer.append(data.decode("utf-8", errors="replace"))


if __name__ == "__main__":
    main()
'''

RELAY_SERVICE = """[Unit]
Description=CEF to Cribl relay
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/cef-cribl-relay.py
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
"""


def main():
    if not TARGET_HOST or not TARGET_USER:
        print("[ERROR] Set TARGET_HOST and TARGET_USER at the top of this script first.")
        sys.exit(1)

    script_content = (
        RELAY_SCRIPT_TEMPLATE
        .replace("__PORT__", str(LISTEN_PORT))
        .replace("__CRIBL_ENDPOINT__", CRIBL_ENDPOINT)
        .replace("__CRIBL_AUTH_TOKEN__", CRIBL_AUTH_TOKEN)
        .replace("__BATCH_INTERVAL__", str(BATCH_INTERVAL_SECONDS))
    )

    ssh_base = ["ssh", "-o", "ConnectTimeout=10"]
    if SSH_KEY_PATH:
        ssh_base += ["-i", SSH_KEY_PATH]
    ssh_base += [f"{TARGET_USER}@{TARGET_HOST}"]

    print(f"--- Deploying CEF->Cribl relay to {TARGET_HOST} ---")
    try:
        subprocess.run(
            ssh_base + ["sudo bash -c 'cat > /opt/cef-cribl-relay.py'"],
            input=script_content, text=True, capture_output=True, check=True, timeout=20,
        )
        subprocess.run(
            ssh_base + ["sudo bash -c 'cat > /etc/systemd/system/cef-cribl-relay.service'"],
            input=RELAY_SERVICE, text=True, capture_output=True, check=True, timeout=20,
        )
        subprocess.run(
            ssh_base + [
                "sudo systemctl daemon-reload && "
                "sudo systemctl enable --now cef-cribl-relay.service && "
                "sudo systemctl restart cef-cribl-relay.service"
            ],
            capture_output=True, check=True, timeout=20,
        )
        print(f"[SUCCESS] Relay deployed and running on UDP :{LISTEN_PORT}, batching every {BATCH_INTERVAL_SECONDS}s.")
        print("Tail the log with: ssh ... 'tail -f /var/log/cef-cribl-relay.log'")
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if isinstance(e.stderr, str) else (e.stderr or b"").decode(errors="replace")
        print(f"[ERROR] Deployment failed: {stderr}")
        sys.exit(1)


if __name__ == "__main__":
    main()
