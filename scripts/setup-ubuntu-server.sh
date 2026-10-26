#!/usr/bin/env bash
# One-time preparation of a fresh Ubuntu server (written for Oracle Cloud's free Ampere/ARM machines,
# works on any Ubuntu 22.04/24.04 server).
#
#   ./scripts/setup-ubuntu-server.sh                         # Docker, tools, firewall
#   ./scripts/setup-ubuntu-server.sh <duckdns-name> <token>  # ...and keep <name>.duckdns.org pointing here
#
# Safe to run again.
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this as your normal user (for example 'ubuntu'), not as root. It uses sudo where needed." >&2
  exit 1
fi

echo "== Installing Docker, make and git"
sudo apt-get update -qq
sudo apt-get install -y -qq make git curl ca-certificates iptables-persistent >/dev/null
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"
sudo systemctl enable --now docker >/dev/null

echo "== Opening ports 80 and 443 in the server's own firewall"
# Oracle's Ubuntu images block everything except SSH with iptables, in addition to the cloud
# security list. Insert the web ports ahead of the final REJECT rule.
open_port() {
  local proto=$1 port=$2
  if ! sudo iptables -C INPUT -p "$proto" --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 1 -p "$proto" --dport "$port" -m state --state NEW -j ACCEPT
  fi
}
open_port tcp 80
open_port tcp 443
open_port udp 443
sudo netfilter-persistent save >/dev/null

if [ "$#" -ge 2 ]; then
  name=$1 token=$2
  echo "== Keeping ${name}.duckdns.org pointed at this server"
  install -d -m 700 "$HOME/.duckdns"
  printf '%s' "$token" > "$HOME/.duckdns/token"
  chmod 600 "$HOME/.duckdns/token"
  cat > "$HOME/.duckdns/update.sh" <<SH
#!/bin/sh
# Tell DuckDNS this server's current public address. Run every 5 minutes by cron.
curl -fsS "https://www.duckdns.org/update?domains=${name}&token=\$(cat "\$HOME/.duckdns/token")&ip=" -o "\$HOME/.duckdns/last.log"
SH
  chmod 700 "$HOME/.duckdns/update.sh"
  "$HOME/.duckdns/update.sh"
  echo "   DuckDNS answered: $(cat "$HOME/.duckdns/last.log") (OK means it worked)"
  ( crontab -l 2>/dev/null | grep -v duckdns/update.sh || true; echo "*/5 * * * * $HOME/.duckdns/update.sh" ) | crontab -
fi

echo
echo "Done. Log out and back in once (so Docker works without sudo), then continue with the guide."
