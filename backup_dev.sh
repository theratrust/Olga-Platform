#!/bin/bash
BACKUP_DIR="/opt/olga-coaching-dev/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="$BACKUP_DIR/olga_dev_backup_$TIMESTAMP.tar.gz"

echo "Dumping development PostgreSQL database..."
docker exec olga_postgres_dev pg_dump -U postgres olga_db_dev > "$BACKUP_DIR/database_dump_$TIMESTAMP.sql" 2>/dev/null

echo "Creating full dev backup archive..."
tar --exclude="$BACKUP_DIR" --exclude="node_modules" -czf "$FILENAME" /opt/olga-coaching-dev "$BACKUP_DIR/database_dump_$TIMESTAMP.sql"

rm "$BACKUP_DIR/database_dump_$TIMESTAMP.sql"

# Keep only the last 10 backups
ls -t $BACKUP_DIR/olga_dev_backup_*.tar.gz | tail -n +11 | xargs -r rm --

echo "Development backup completed successfully: $FILENAME"
