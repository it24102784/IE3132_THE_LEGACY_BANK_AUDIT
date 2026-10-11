#!/bin/bash
set -e

echo "[+] Starting linux_challenge (Legacy Bank vault server)..."

# Flags are the single source of truth, mounted at /flags (read-only)
STAGE3_FLAG="$(cat /flags/stage3.txt 2>/dev/null | tr -d '\r\n')"
STAGE5_FLAG="$(cat /flags/stage5.txt 2>/dev/null | tr -d '\r\n')"
STAGE6_FLAG="$(cat /flags/stage6.txt 2>/dev/null | tr -d '\r\n')"

if [ -z "$STAGE3_FLAG" ] || [ -z "$STAGE5_FLAG" ] || [ -z "$STAGE6_FLAG" ]; then
  echo "ERROR: /flags/stage{3,5,6}.txt missing or empty. Add './flags:/flags:ro' to linux_challenge volumes."
  exit 1
fi

# --- SSH daemon setup ---
mkdir -p /run/sshd
ssh-keygen -A >/dev/null 2>&1 || true
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
grep -q "^AllowUsers" /etc/ssh/sshd_config || echo "AllowUsers vaultadmin" >> /etc/ssh/sshd_config

# --- Low-privileged user: the Stage 4 -> 5 chain ---
# Username revealed by the 2FA gate, password is the Stage 3 decoded credential
if ! id vaultadmin >/dev/null 2>&1; then
  useradd -m -s /bin/bash vaultadmin
fi
printf 'vaultadmin:%s\n' "$STAGE3_FLAG" | chpasswd
echo "[+] user vaultadmin ready"

# --- THE VULNERABILITY (Stage 5: find it / Stage 6: exploit it) ---
# Root cron job, every minute, running a world-writable script
mkdir -p /opt/legacy
cat > /opt/legacy/maintenance.sh <<'SCRIPT_EOF'
#!/bin/bash
# Legacy Bank - automated vault maintenance (runs as root every minute)
echo "maintenance run at $(date)" >> /var/log/legacy-maintenance.log
find /var/tmp -name 'legacy_*.tmp' -mtime +7 -delete 2>/dev/null || true
SCRIPT_EOF
chmod 777 /opt/legacy/maintenance.sh
printf '* * * * * root /opt/legacy/maintenance.sh\n' > /etc/cron.d/legacy-maintenance
chmod 644 /etc/cron.d/legacy-maintenance

# Stage 5 flag: sits beside the vulnerable job. You only find it by
# tracing the cron entry to this directory (enumeration reward).
printf '%s\n' "$STAGE5_FLAG" > /opt/legacy/scheduler_audit.txt
cat >> /opt/legacy/scheduler_audit.txt <<'NOTE_EOF'
# Internal audit note: the legacy-maintenance cron job runs the script
# above as root every minute. Its permissions were "temporarily" loosened
# during the 2019 migration and never restored.
NOTE_EOF
chmod 644 /opt/legacy/scheduler_audit.txt

# Decoy: a properly-configured root cron job (root-owned, not writable).
# Forces real enumeration instead of guessing the first cron entry found.
cat > /usr/local/bin/disk-cleanup.sh <<'SCRIPT_EOF'
#!/bin/bash
# System disk cleanup (root-owned, not writable - nothing to see here)
journalctl --vacuum-time=7d >/dev/null 2>&1 || true
SCRIPT_EOF
chmod 755 /usr/local/bin/disk-cleanup.sh
chown root:root /usr/local/bin/disk-cleanup.sh
printf '*/15 * * * * root /usr/local/bin/disk-cleanup.sh\n' > /etc/cron.d/system-cleanup
chmod 644 /etc/cron.d/system-cleanup

# --- Stage 6 flag: root only ---
printf '%s\n' "$STAGE6_FLAG" > /root/flag.txt
chmod 600 /root/flag.txt
chown root:root /root/flag.txt

# --- Start services ---
service cron start
touch /tmp/healthy
echo "[+] linux_challenge ready: SSH on 10.10.10.10:22, cron armed."
exec /usr/sbin/sshd -D
