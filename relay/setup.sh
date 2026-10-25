#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Swapnote relay setup for a Raspberry Pi (Raspberry Pi OS Lite, Debian 12+), run as root:
#   sudo ./setup.sh --server-ip 100.x.y.z [--server-port 8080] [--authkey tskey-...]
#                   [--relay-user U --relay-pass P] [--upstream-user U --upstream-pass P]
#
#   --server-ip      the Swapnote server's Tailscale address (tailscale ip -4 on the server)
#   --authkey        a Tailscale auth key, so the Pi joins your tailnet without a login
#                    (create one in the Tailscale admin console; pre-approved, tagged)
#   --relay-user/--relay-pass        password the 3DS must enter for this relay (optional)
#   --upstream-user/--upstream-pass  the server's [proxy] username/password, if set
set -euo pipefail
cd "$(dirname "$0")"

SERVER_IP= SERVER_PORT=8080 AUTHKEY= RELAY_USER= RELAY_PASS= UP_USER= UP_PASS=
while [ $# -gt 0 ]; do
    case "$1" in
        --server-ip) SERVER_IP=$2; shift 2 ;;
        --server-port) SERVER_PORT=$2; shift 2 ;;
        --authkey) AUTHKEY=$2; shift 2 ;;
        --relay-user) RELAY_USER=$2; shift 2 ;;
        --relay-pass) RELAY_PASS=$2; shift 2 ;;
        --upstream-user) UP_USER=$2; shift 2 ;;
        --upstream-pass) UP_PASS=$2; shift 2 ;;
        *) echo "unknown option $1"; exit 1 ;;
    esac
done
[ -n "$SERVER_IP" ] || { echo "--server-ip is required"; exit 1; }
[ "$(id -u)" = 0 ] || { echo "run as root (sudo)"; exit 1; }

echo "== Installing Tailscale and tinyproxy"
apt-get update -q
apt-get install -y -q tinyproxy curl
if ! command -v tailscale >/dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi
systemctl enable --now tailscaled
if [ -n "$AUTHKEY" ]; then
    tailscale up --authkey "$AUTHKEY" --hostname swapnote-relay
else
    tailscale up --hostname swapnote-relay   # prints a login link
fi

echo "== Configuring tinyproxy"
LAN_SUBNET=$(ip -4 route show scope link | awk '!/tailscale/ {print $1; exit}')
[ -n "$LAN_SUBNET" ] || { echo "could not detect the local network"; exit 1; }
AUTH_LINE="# no relay password"
[ -n "$RELAY_USER" ] && AUTH_LINE="BasicAuth $RELAY_USER $RELAY_PASS"
UPSTREAM_AUTH=
[ -n "$UP_USER" ] && UPSTREAM_AUTH="$UP_USER:$UP_PASS@"
sed -e "s#LAN_SUBNET#$LAN_SUBNET#" -e "s#RELAY_AUTH#$AUTH_LINE#" \
    -e "s#UPSTREAM_AUTH#$UPSTREAM_AUTH#" -e "s#SERVER_TAILNET_ADDRESS#$SERVER_IP#" \
    -e "s#SERVER_PORT#$SERVER_PORT#" tinyproxy.conf.template > /etc/tinyproxy/tinyproxy.conf
chmod 640 /etc/tinyproxy/tinyproxy.conf
chgrp tinyproxy /etc/tinyproxy/tinyproxy.conf
systemctl enable tinyproxy
systemctl restart tinyproxy

LAN_IP=$(ip -4 route get 1.1.1.1 | awk '{for(i=1;i<NF;i++) if($i=="src") print $(i+1)}')
echo
echo "Relay ready. On the 3DS: System Settings -> Internet Settings -> Connection Settings"
echo "-> (this Wi-Fi) -> Change Settings -> Proxy Settings -> Yes -> Detailed Setup:"
echo "   Proxy server: $LAN_IP    Port: 8080"
[ -n "$RELAY_USER" ] && echo "   Authentication: Yes, user $RELAY_USER"
echo "Ask the router to always give this Pi the address $LAN_IP (DHCP reservation)."
