-- ═══════════════════════════════════════════════════════════════════════════════
-- Macro Terminal v8.0 — TimescaleDB Initialization
-- Run this first before application starts
-- ═══════════════════════════════════════════════════════════════════════════════

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create TimescaleDB hypertables for time-series data
-- These will be created by the application on startup,
-- but we include them here for reference

-- Note: The application uses SQLAlchemy models with init_db() function
-- to create tables and hypertables automatically.
-- See api/database/connection.py for the initialization logic.

-- Grant permissions (if using a separate app user)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO macro_app;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO macro_app;
