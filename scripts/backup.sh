#!/usr/bin/env bash
# ==============================================================================
# Agentic Legal Assistant Automated Backup Script
# Performs PostgreSQL database dump and encrypted document volume snapshot
# ==============================================================================

set -euo pipefail

BACKUP_DIR="/var/backups/lexground"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DEST_DIR="${BACKUP_DIR}/${TIMESTAMP}"

mkdir -p "${DEST_DIR}"
chmod 700 "${DEST_DIR}"

echo "[$(date)] Starting LexGround backup to ${DEST_DIR}..."

# 1. PostgreSQL Database Dump
echo "[$(date)] Exporting PostgreSQL database..."
docker compose exec -T postgres pg_dump -U lexground -d lexground -F c -b -v -f /tmp/backup.dump
docker compose cp postgres:/tmp/backup.dump "${DEST_DIR}/database.dump"
docker compose exec -T postgres rm /tmp/backup.dump

# 2. Encrypted Document Volume Snapshot
echo "[$(date)] Archiving encrypted document storage..."
docker compose cp lexground-backend:/app/data/corpus "${DEST_DIR}/corpus"

# 3. Create compressed and secured archive
echo "[$(date)] Compressing backup bundle..."
tar -czf "${BACKUP_DIR}/lexground_backup_${TIMESTAMP}.tar.gz" -C "${BACKUP_DIR}" "${TIMESTAMP}"
rm -rf "${DEST_DIR}"
chmod 600 "${BACKUP_DIR}/lexground_backup_${TIMESTAMP}.tar.gz"

# 4. Prune backups older than 30 days
find "${BACKUP_DIR}" -name "lexground_backup_*.tar.gz" -type f -mtime +30 -delete

echo "[$(date)] Backup completed successfully: ${BACKUP_DIR}/lexground_backup_${TIMESTAMP}.tar.gz"
