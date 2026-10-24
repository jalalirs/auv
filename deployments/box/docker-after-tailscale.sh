#!/usr/bin/env bash
# Makes Docker start after Tailscale has its address, so the services that
# listen on the Tailscale address (iocean's, areen's) come back by themselves
# after a reboot. On 2026-10-24 they failed at boot with "failed to bind":
# Docker started them before 100.76.65.1 existed, and does not retry.
#
# Run on the box, as yourself (it asks for sudo):
#   bash ~/code/auv/deployments/box/docker-after-tailscale.sh
# It adds one systemd drop-in for docker.service: start after tailscaled, and
# wait up to 60 s for the address before starting (then start anyway, so a box
# with Tailscale down still runs everything else). Nothing restarts now; it
# takes effect at the next boot. To undo: sudo rm the file below and run
# sudo systemctl daemon-reload.
set -euo pipefail
ADDRESS=100.76.65.1
DROPIN=/etc/systemd/system/docker.service.d/after-tailscale.conf
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee "$DROPIN" >/dev/null <<UNIT
[Unit]
After=tailscaled.service
Wants=tailscaled.service

[Service]
ExecStartPre=/bin/sh -c 'for i in \$(seq 1 60); do ip -4 addr show tailscale0 2>/dev/null | grep -q "$ADDRESS" && exit 0; sleep 1; done; exit 0'
UNIT
sudo systemctl daemon-reload
systemctl show docker.service -p After | tr ' ' '\n' | grep -q tailscaled.service && echo "docker now starts after tailscaled ($DROPIN)"
