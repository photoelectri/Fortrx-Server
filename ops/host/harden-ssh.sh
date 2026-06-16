#!/usr/bin/env bash
set -euo pipefail

APPROVAL_FLAG="${1:-}"
ALLOWED_USER="${2:-ubuntu}"
SSH_PORT="${3:-22}"
SSH_HARDENING_FILE="/etc/ssh/sshd_config.d/99-fortrx-hardening.conf"

if [[ "$APPROVAL_FLAG" != "--yes-i-have-a-working-ssh-key" ]]; then
  echo "Usage: bash ops/host/harden-ssh.sh --yes-i-have-a-working-ssh-key [allowed_user] [ssh_port]" >&2
  exit 1
fi

sudo_run() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

sudo_run mkdir -p /etc/ssh/sshd_config.d
sudo_run tee "$SSH_HARDENING_FILE" >/dev/null <<EOF
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 30
AllowUsers $ALLOWED_USER
Port $SSH_PORT
EOF

sudo_run sshd -t
sudo_run systemctl restart ssh
sudo_run systemctl status ssh --no-pager

echo "SSH hardening applied for user '$ALLOWED_USER' on port $SSH_PORT."
