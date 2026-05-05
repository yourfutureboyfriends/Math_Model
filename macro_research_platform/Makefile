# ═══════════════════════════════════════════════════════════════════════════════
# Macro Research Platform — Makefile
# Quick commands for development and production operations
# ═══════════════════════════════════════════════════════════════════════════════

.PHONY: help install data test run export clean start stop restart logs backup update shell db status ps rebuild

# ═══════════════════════════════════════════════════════════════════════════════
# Development Commands (Local)
# ═══════════════════════════════════════════════════════════════════════════════

help:
	@echo "Macro Research Platform - Available Commands:"
	@echo ""
	@echo "Development (Local):"
	@echo "  make install    - Install all dependencies"
	@echo "  make data       - Generate sample data"
	@echo "  make test       - Run test suite"
	@echo "  make run        - Start the Streamlit dashboard"
	@echo "  make export     - Export data to Excel/PDF"
	@echo "  make clean      - Clean cache and temp files"
	@echo ""
	@echo "Production (Docker):"
	@echo "  make start      - Start platform (docker-compose up)"
	@echo "  make stop       - Stop platform (docker-compose down)"
	@echo "  make restart    - Restart backend service"
	@echo "  make logs       - View live logs"
	@echo "  make backup     - Backup database and reports"
	@echo "  make update     - Update to latest version"
	@echo "  make shell      - Access backend container shell"
	@echo "  make db         - Open SQLite database shell"
	@echo "  make status     - Check platform health"
	@echo "  make ps         - List running containers"
	@echo "  make rebuild    - Rebuild containers"
	@echo ""

# Install dependencies
install:
	pip install -r requirements.txt
	@echo "Dependencies installed. Copy .env.example to .env and add your FRED_API_KEY"

# Generate sample data
data:
	python scripts/generate_sample_data.py
	@echo "Sample data generated in data/raw/"

# Run tests
test:
	pytest tests/ -v

# Start dashboard (legacy Streamlit)
run:
	streamlit run dashboard.py

# Export data to files
export:
	@echo "Export functionality available in dashboard"

# Clean cache and temp files
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Cache cleaned"

# ═══════════════════════════════════════════════════════════════════════════════
# Production Commands (Docker)
# ═══════════════════════════════════════════════════════════════════════════════

# Start the platform
start:
	@./scripts/start.sh

# Stop the platform
stop:
	@./scripts/stop.sh

# Restart backend only
restart:
	@docker-compose restart backend
	@echo "Backend restarted"

# View live logs
logs:
	@docker-compose logs -f backend

# Backup database and reports
backup:
	@./scripts/backup.sh

# Update to latest version
update:
	@./scripts/update.sh

# Open shell in backend container
shell:
	@docker exec -it macro-backend bash

# Open SQLite database shell
db:
	@docker exec -it macro-backend sqlite3 /app/database/macro_platform.db

# Check platform status
status:
	@echo "Platform Status"
	@echo "═══════════════════════════════════════════════"
	@docker-compose ps
	@echo ""
	@echo "Health Check:"
	@curl -s http://localhost:5000/api/health/full 2>/dev/null | python3 -m json.tool || echo "Backend not responding"

# List running containers
ps:
	@docker-compose ps

# Rebuild containers
rebuild:
	@docker-compose build --no-cache backend
	@docker-compose up -d
	@echo "Containers rebuilt"
