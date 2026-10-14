# AGENTIC LEGAL ASSISTANT: Private Pilot VPS Deployment Guide

This guide describes how to deploy **Agentic Legal Assistant** on a dedicated single-node Virtual Private Server ($10–20/month, e.g. Hetzner CX22/CX32, DigitalOcean, or Linode) with automated HTTPS, daily encrypted backups, and non-root Docker security.

---

## 1. System Requirements

- **Operating System**: Ubuntu 24.04 LTS or 22.04 LTS x86_64
- **Specifications**: Minimum 2 vCPU, 4 GB RAM, 40 GB NVMe SSD
- **Public FQDN**: e.g., `legal.yourfirm.com` pointing to the VPS IP via DNS `A` record
- **Software**: Docker Engine 24+ and Docker Compose plugin

---

## 2. Server Preparation & Hardening

Log in to your VPS via SSH as root:

```bash
# Update system packages
apt update && apt upgrade -y

# Install prerequisite tools
apt install -y curl git ufw fail2ban ca-certificates

# Install Docker Engine & Compose plugin
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Configure strict firewall (allow SSH, HTTP, HTTPS only)
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

---

## 3. Clone Repository & Generate Secrets

```bash
# Clone the repository
git clone -b production https://github.com/your-org/lexground.git /opt/lexground
cd /opt/lexground

# Generate production cryptographic secrets
python3 scripts/generate_secrets.py
```

Create `/opt/lexground/.env` based on `.env.example`:

```bash
cp .env.example .env
nano .env
```

Ensure the following variables are configured in `.env`:
- `GROQ_API_KEY`: Your production Groq API key
- `JWT_SECRET`: The generated 64-character secret
- `ENCRYPTION_KEY`: The generated Fernet AES-256 base64 key
- `POSTGRES_PASSWORD`: The generated database password
- `REDIS_PASSWORD`: The generated Redis cache password
- `DOMAIN_NAME`: `legal.yourfirm.com`
- `ACME_EMAIL`: `admin@yourfirm.com`

---

## 4. Single-Command Launch

Launch the entire stack:

```bash
docker compose up -d
```

Monitor container boot and health status:

```bash
# Check container status
docker compose ps

# View backend startup logs and Alembic schema migration
docker compose logs -f lexground-backend
```

Once running, verify health via curl or browser:

```bash
curl -I https://legal.yourfirm.com/health
```

Expected response: `HTTP/2 200` with JSON `{"status": "ok", "app": "Agentic Legal Assistant"}`.

---

## 5. Automated Backups & Retention

Configure daily encrypted backups of the database and documents:

```bash
# Make backup script executable
chmod +x /opt/lexground/scripts/backup.sh

# Add cron job to run every night at 02:00 UTC
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/lexground/scripts/backup.sh >> /var/log/lexground_backup.log 2>&1") | crontab -
```

Backups are saved to `/var/backups/lexground/` and automatically pruned after 30 days.

---

## 6. Restore Validation Procedure

To verify backup integrity or perform disaster recovery:

1. Extract the backup bundle:
   ```bash
   tar -xzf /var/backups/lexground/lexground_backup_YYYYMMDD_HHMMSS.tar.gz -C /tmp/restore
   ```
2. Restore the PostgreSQL database:
   ```bash
   docker compose cp /tmp/restore/*/database.dump postgres:/tmp/restore.dump
   docker compose exec -T postgres pg_restore -U lexground -d lexground --clean --if-exists /tmp/restore.dump
   docker compose exec -T postgres rm /tmp/restore.dump
   ```
3. Restore the encrypted corpus volume:
   ```bash
   docker compose cp /tmp/restore/*/corpus/. lexground-backend:/app/data/corpus/
   ```
4. Restart the backend container and run healthchecks:
   ```bash
   docker compose restart lexground-backend
   curl -f http://127.0.0.1:8000/health
   ```

---

## 7. Zero Downtime Updates

To deploy updates without dropping user connections:

```bash
cd /opt/lexground
git pull origin production
docker compose build lexground-backend
docker compose up -d --no-deps lexground-backend
```
