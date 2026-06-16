#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:?Usage: install-fail2ban.sh /srv/fortrx}"
FAIL2BAN_FILTER="/etc/fail2ban/filter.d/fortrx-caddy-probes.conf"
FAIL2BAN_JAIL="/etc/fail2ban/jail.d/fortrx.local"
LOG_PATH="$APP_DIR/ops/host/logs/caddy-access.log"

sudo_run() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

sudo_run apt-get update
sudo_run apt-get install -y fail2ban

mkdir -p "$APP_DIR/ops/host/logs"
sudo_run touch "$LOG_PATH"

sudo_run tee "$FAIL2BAN_FILTER" >/dev/null <<EOF
[Definition]
failregex = ^.*"remote_ip":"<HOST>".*"status":403.*$
ignoreregex =
EOF

sudo_run tee "$FAIL2BAN_JAIL" >/dev/null <<EOF
[sshd]
enabled = true
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h

[fortrx-caddy-probes]
enabled = true
filter = fortrx-caddy-probes
port = http,https
logpath = $LOG_PATH
backend = auto
maxretry = 8
findtime = 10m
bantime = 12h
EOF

sudo_run systemctl enable --now fail2ban
sudo_run systemctl restart fail2ban
sudo_run fail2ban-client status

echo "Installed fail2ban with sshd and fortrx-caddy-probes jails."
