#!/bin/bash
BACKUP_DIR="/opt/olga-coaching-bot/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="$BACKUP_DIR/olga_bot_backup_$TIMESTAMP.tar.gz"

echo "Creating backup..."
tar --exclude="$BACKUP_DIR" --exclude="node_modules" -czf "$FILENAME" /opt/olga-coaching-bot

# Keep only the last 10 backups to save disk space
ls -t $BACKUP_DIR/olga_bot_backup_*.tar.gz | tail -n +11 | xargs -r rm --

echo "Backup completed successfully: $FILENAME"
