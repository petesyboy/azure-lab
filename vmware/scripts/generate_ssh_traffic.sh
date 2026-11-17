#!/bin/bash
#
# generate_ssh_traffic.sh
# Periodically SSHes into a target host and runs a few benign commands, to
# put real SSH protocol traffic through the tap alongside the DNS/HTTPS
# traffic from generate_web_traffic.sh. Uses a dedicated key
# (~/.ssh/ssh_traffic_key), not the operator's own access key.

TARGET_USER="__TARGET_USER__"
TARGET_HOST="__TARGET_HOST__"
KEY_PATH="$HOME/.ssh/ssh_traffic_key"

COMMANDS=(
  "uptime"
  "whoami"
  "date"
  "df -h"
  "ls -la /tmp"
  "ps aux | head -5"
  "echo hello from prod1"
)

echo "=========================================================="
echo " Generating SSH Traffic to ${TARGET_USER}@${TARGET_HOST}"
echo "=========================================================="

while true; do
  CMD="${COMMANDS[$((RANDOM % ${#COMMANDS[@]}))]}"

  DELAY=$(printf "0.%03d" $(( (RANDOM % 500) + 1 )))
  echo "[*] Waiting ${DELAY}s..."
  sleep "$DELAY"

  echo "[*] SSH ${TARGET_USER}@${TARGET_HOST}: ${CMD}"
  ssh -i "$KEY_PATH" \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      -o ConnectTimeout=5 \
      -o LogLevel=ERROR \
      "${TARGET_USER}@${TARGET_HOST}" "$CMD" || echo "[!] SSH session failed"

  SLEEP=$(( (RANDOM % 20) + 5 ))
  echo "[*] Sleeping ${SLEEP}s before next login..."
  sleep "$SLEEP"
done
