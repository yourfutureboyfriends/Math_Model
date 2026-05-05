#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Macro Research Platform — Stop Script
# ═══════════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        Macro Research Platform — Stopping Services           ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Stop services
docker-compose down

echo ""
echo -e "${GREEN}✓ Platform stopped. Data preserved in Docker volumes.${NC}"
echo ""
echo "To start again: make start"
