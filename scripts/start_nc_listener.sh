#!/bin/bash
#
# start_nc_listener.sh
# Starts a basic netcat listener on the primary ethernet card IP on port 1514

# Get the primary IP address (typically eth0 on Azure Ubuntu VMs)
PRIMARY_IP=$(ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n 1)

# Fallback to hostname -I if eth0 is not present
if [ -z "$PRIMARY_IP" ]; then
    PRIMARY_IP=$(hostname -I | awk '{print $1}')
fi

if [ -z "$PRIMARY_IP" ]; then
    echo "Error: Could not determine primary IP address."
    exit 1
fi

echo "Starting netcat listener on ${PRIMARY_IP}:1514..."
echo "Listening for incoming data (Press Ctrl+C to exit)..."

# Wrap in a loop so it resumes listening after a client disconnects
while true; do
    nc -u -l "$PRIMARY_IP" 1514
    sleep 1
done
