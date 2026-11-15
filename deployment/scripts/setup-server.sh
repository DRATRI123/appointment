#!/usr/bin/env bash
# One-time preparation of a fresh Ubuntu 24.04 server (for example a Hostinger KVM VPS). Run as root:
#
#   sudo deployment/scripts/setup-server.sh --user deploy [--ssh-port 22]
#
# Installs and configures, and nothing else:
#   * security updates now, and automatic security updates from now on (unattended-upgrades)
#   * Docker Engine + Compose plugin from Docker's official repository (log rotation, no-new-privileges by default,
#     userland proxy off so the app sees real visitor IPs)
#   * firewall (ufw): only SSH, 80 and 443 open; fail2ban for SSH
#   * a non-root user that runs the app (--user), in the docker group
#   * SSH: root login and passwords off, but ONLY when that user already has an SSH key (so you cannot be locked out)
#   * 2 GB swap when the server has none; kernel settings for Redis and many connections
# Safe to run again. It does not deploy the app: afterwards, as the new user, clone the repository and run deploy.sh.

set -Eeuo pipefail
trap 'echo "ERROR: stopped at line $LINENO. Fix the problem above and run the script again (it is safe to repeat)." >&2' ERR

APP_USER="" SSH_PORT=22 FORCE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --user) APP_USER="${2:?--user needs a name}"; shift 2 ;;
        --ssh-port) SSH_PORT="${2:?--ssh-port needs a number}"; shift 2 ;;
        --force) FORCE=1; shift ;;
        -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 1 ;;
    esac
done
say() { printf '\033[1m==>\033[0m %s\n' "$*"; }

[ "$(id -u)" = 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }
[ -n "$APP_USER" ] || { echo "Give the user that will run the app: --user deploy" >&2; exit 1; }
[[ "$APP_USER" =~ ^[a-z][a-z0-9_-]{0,30}$ ]] || { echo "--user: lowercase letters, digits, - and _ only" >&2; exit 1; }
[[ "$SSH_PORT" =~ ^[0-9]+$ ]] || { echo "--ssh-port must be a number" >&2; exit 1; }
. /etc/os-release
if [ "${ID:-}" != ubuntu ] || [ "${VERSION_ID:-}" != "24.04" ]; then
    [ "$FORCE" = 1 ] || { echo "This script is written for Ubuntu 24.04 (found ${PRETTY_NAME:-unknown}). --force to try anyway." >&2; exit 1; }
fi
export DEBIAN_FRONTEND=noninteractive

say "Installing security updates and base tools"
apt-get update -q
apt-get -y -q upgrade
apt-get -y -q install ca-certificates curl gnupg git ufw fail2ban unattended-upgrades python3 openssl

say "Turning on automatic security updates"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
systemctl enable --now unattended-upgrades >/dev/null

if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
    say "Installing Docker Engine and the Compose plugin (official Docker repository)"
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -q
    apt-get -y -q install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

say "Configuring Docker (log rotation, no-new-privileges, real client IPs)"
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "5"},
  "no-new-privileges": true,
  "userland-proxy": false,
  "live-restore": true
}
EOF
systemctl enable docker >/dev/null
systemctl restart docker

say "Creating the app user '$APP_USER'"
id "$APP_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$APP_USER"
usermod -aG docker "$APP_USER"   # note: docker group members can control Docker, i.e. are effectively root
install -d -m 0750 -o "$APP_USER" -g "$APP_USER" /opt/appointment

say "Firewall: only SSH ($SSH_PORT), 80 and 443"
ufw --force default deny incoming >/dev/null
ufw --force default allow outgoing >/dev/null
ufw allow "$SSH_PORT/tcp" >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
# Docker publishes ports past ufw. compose.production.yaml publishes only Nginx (80/443) and binds Prometheus to
# 127.0.0.1, so nothing else is reachable; never add other "ports:" entries on a server.
systemctl enable --now fail2ban >/dev/null

say "SSH hardening"
keys="/home/$APP_USER/.ssh/authorized_keys"
if [ ! -s "$keys" ] && [ -s /root/.ssh/authorized_keys ]; then
    install -d -m 0700 -o "$APP_USER" -g "$APP_USER" "/home/$APP_USER/.ssh"
    install -m 0600 -o "$APP_USER" -g "$APP_USER" /root/.ssh/authorized_keys "$keys"
    echo "  copied root's SSH key(s) to $APP_USER"
fi
if [ -s "$keys" ]; then
    cat > /etc/ssh/sshd_config.d/60-appointment.conf <<EOF
Port $SSH_PORT
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
MaxAuthTries 4
EOF
    sshd -t && systemctl reload ssh
    echo "  root login and passwords are off; sign in as: ssh -p $SSH_PORT $APP_USER@<server>"
else
    echo "  ! $APP_USER has no SSH key yet, so passwords stay ON (you would be locked out otherwise)."
    echo "    Add your public key to $keys, then run this script again to switch passwords off."
fi

if [ "$(swapon --show --noheadings | wc -l)" = 0 ]; then
    say "Adding a 2 GB swap file (protects against out-of-memory kills during builds)"
    fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
cat > /etc/sysctl.d/60-appointment.conf <<'EOF'
vm.overcommit_memory = 1
vm.swappiness = 10
net.core.somaxconn = 4096
EOF
sysctl -q --system

cat <<EOF

Server ready. Next, as $APP_USER:
  ssh -p $SSH_PORT $APP_USER@<server>
  git clone <your repository URL> /opt/appointment && cd /opt/appointment
  deployment/scripts/deploy.sh --domain book.yourclinic.in --email you@yourclinic.in
(Point the domain's DNS A record at this server first.) Full guide: docs/production-deployment.md
EOF
