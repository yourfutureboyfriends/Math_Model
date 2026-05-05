#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Macro Research Platform — Update Script
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

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        Macro Research Platform — Updating Services             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Pull latest changes
echo "📥 Pulling latest changes..."
git pull

# Create backup before update
echo "💾 Creating pre-update backup..."
./scripts/backup.sh || true

# Rebuild and restart
echo "🔨 Rebuilding containers..."
docker-compose build --no-cache backend

echo "🚀 Restarting services..."
docker-compose up -d

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Update complete!                                            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Check status with: make status"
