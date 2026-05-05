#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Macro Research Platform — Backup Script
# ═══════════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="./backups/$DATE"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           Creating Backup — $DATE             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

mkdir -p "$BACKUP_DIR"

# Check if container is running
if docker ps | grep -q "macro-backend"; then
    echo "📦 Backing up database..."
    # Create SQLite backup inside container
    docker exec macro-backend sqlite3 /app/database/macro_platform.db ".backup /tmp/backup.db"
    # Copy to host
    docker cp macro-backend:/tmp/backup.db "$BACKUP_DIR/macro_platform.db"
    echo -e "${GREEN}✓ Database backed up${NC}"

    echo "📄 Backing up reports..."
    if docker exec macro-backend test -d /app/reports/archive; then
        docker cp macro-backend:/app/reports/archive "$BACKUP_DIR/reports"
        echo -e "${GREEN}✓ Reports backed up${NC}"
    else
        echo -e "${YELLOW}⚠ No reports directory found${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Backend container not running, attempting direct backup...${NC}"
    if [ -f "database/macro_platform.db" ]; then
        cp database/macro_platform.db "$BACKUP_DIR/macro_platform.db"
        echo -e "${GREEN}✓ Database backed up (direct copy)${NC}"
    fi
fi

# Create metadata file
cat > "$BACKUP_DIR/backup_info.txt" << EOF
Macro Research Platform Backup
Generated: $(date)
Hostname: $(hostname)
User: $(whoami)

Contents:
- macro_platform.db: SQLite database
- reports/: Archived reports
EOF

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Backup complete!                                            ║${NC}"
echo -e "${GREEN}║  Location: $BACKUP_DIR              ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"

# Cleanup old backups (keep last 30)
echo ""
echo "🧹 Cleaning up old backups..."
BACKUP_COUNT=$(find ./backups -maxdepth 1 -type d | wc -l)
if [ "$BACKUP_COUNT" -gt 31 ]; then  # +1 for the backups directory itself
    find ./backups -maxdepth 1 -type d -printf '%T@ %p\n' | sort -n | head -n -30 | cut -d' ' -f2- | xargs -r rm -rf
    echo -e "${GREEN}✓ Kept 30 most recent backups${NC}"
fi

echo ""
echo "Available backups:"
ls -lt ./backups | head -11
