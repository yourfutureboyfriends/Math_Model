#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Macro Research Platform — Start Script
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
echo -e "${BLUE}║        Macro Research Platform — Starting Services           ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠ .env file not found. Copying from .env.example...${NC}"
    cp .env.example .env
    echo "✓ Created .env file. Please edit it with your API keys before continuing."
    exit 1
fi

# Check if docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Build and start services
echo "🔨 Building containers..."
docker-compose build --no-cache backend

echo "🚀 Starting services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for health checks..."
sleep 15

echo ""
echo "🔍 Checking service health..."

# Check backend health
if curl -s http://localhost:5000/api/health/full > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend is healthy${NC}"
    HEALTH_STATUS=$(curl -s http://localhost:5000/api/health/full | python3 -m json.tool 2>/dev/null || echo "Health check response received")
    echo "$HEALTH_STATUS"
else
    echo -e "${YELLOW}⚠ Backend health check pending (may need more time)${NC}"
fi

# Check frontend
if curl -s http://localhost:3002 > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Frontend is responding${NC}"
else
    echo -e "${YELLOW}⚠ Frontend may still be starting${NC}"
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Platform running successfully!                              ║${NC}"
echo -e "${GREEN}║  • Frontend: http://localhost:3002                           ║${NC}"
echo -e "${GREEN}║  • API:     http://localhost:5000                          ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Useful commands:"
echo "  make logs     - View live logs"
echo "  make status   - Check health"
echo "  make shell    - Access backend shell"
echo "  make stop     - Stop the platform"
