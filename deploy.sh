#!/bin/bash

# =============================================================================
# Spike AI Multi-Agent Analytics System - Deployment Script
# =============================================================================
#
# This script deploys the production-ready AI backend for the Spike AI Hackathon.
#
# Requirements (per PRD):
# - Must complete startup within 7 minutes
# - Must bind to port 8080 only
# - Must use .venv at repository root
# - Must use credentials.json at project root
#
# Usage:
#   bash deploy.sh
#
# =============================================================================

set -e  # Exit on any error

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
PYTHON_CMD="python3"
PIP_CMD="pip"
PORT=8080
LOG_FILE="$PROJECT_ROOT/deploy.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[DEPLOY]${NC} $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: $1" >> "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >> "$LOG_FILE"
    exit 1
}

# Header
echo "============================================================================="
echo "  Spike AI Multi-Agent Analytics System - Deployment"
echo "============================================================================="
echo ""

# Initialize log file
echo "=== Deployment started at $(date) ===" > "$LOG_FILE"

# Step 1: Check Python availability
log "Checking Python installation..."

# Try python3 first, then python
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    error "Python not found. Please install Python 3.10 or higher."
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1)
log "Found Python: $PYTHON_VERSION"

# Step 2: Verify project structure
log "Verifying project structure..."

cd "$PROJECT_ROOT"

# Check for required files
if [ ! -f "main.py" ]; then
    error "main.py not found in project root"
fi

if [ ! -f "requirements.txt" ]; then
    error "requirements.txt not found in project root"
fi

if [ ! -f "credentials.json" ]; then
    error "credentials.json not found in project root. This file is required for GA4 and Google Sheets authentication."
fi

if [ ! -d "src" ]; then
    error "src/ directory not found"
fi

log "✓ Project structure verified"

# Step 3: Create/Update virtual environment
log "Setting up virtual environment at .venv..."

if [ -d "$VENV_DIR" ]; then
    log "Virtual environment exists, checking activation..."
else
    log "Creating new virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"
fi

# Activate virtual environment
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
elif [ -f "$VENV_DIR/Scripts/activate" ]; then
    source "$VENV_DIR/Scripts/activate"
else
    error "Failed to locate virtual environment activation script"
fi

log "✓ Virtual environment activated"

# Step 4: Upgrade pip (using python -m pip for cross-platform compatibility)
log "Upgrading pip..."
$PYTHON_CMD -m pip install --upgrade pip -q

# Step 5: Install dependencies
log "Installing dependencies from requirements.txt..."
$PYTHON_CMD -m pip install -r requirements.txt -q

log "✓ Dependencies installed"

# Step 6: Verify critical environment variables
log "Checking environment configuration..."

# Load .env if exists
if [ -f ".env" ]; then
    log "Loading environment variables from .env"
    export $(grep -v '^#' .env | xargs)
fi

# Check for LITELLM_API_KEY
if [ -z "$LITELLM_API_KEY" ]; then
    warn "LITELLM_API_KEY not set in environment. Make sure it's configured in .env"
fi

# Check for SHEET_ID (optional but recommended)
if [ -z "$SHEET_ID" ]; then
    warn "SHEET_ID not set. SEO Agent queries will require explicit sheet ID."
fi

log "✓ Environment configuration checked"

# Step 7: Stop any existing process on port 8080
log "Checking if port $PORT is available..."

if command -v lsof &> /dev/null; then
    PID=$(lsof -t -i:$PORT 2>/dev/null || true)
    if [ -n "$PID" ]; then
        warn "Port $PORT is in use by PID $PID. Attempting to stop..."
        kill -9 $PID 2>/dev/null || true
        sleep 2
    fi
elif command -v netstat &> /dev/null; then
    # Windows/alternative check
    if netstat -tuln | grep -q ":$PORT "; then
        warn "Port $PORT appears to be in use. Please ensure it's free."
    fi
fi

log "✓ Port $PORT ready"

# Step 8: Validate Python modules can be imported
log "Validating Python imports..."

$PYTHON_CMD -c "
import sys
sys.path.insert(0, 'src')

# Test critical imports
try:
    from fastapi import FastAPI
    print('  ✓ FastAPI')
except ImportError as e:
    print(f'  ✗ FastAPI: {e}')
    sys.exit(1)

try:
    from openai import OpenAI
    print('  ✓ OpenAI SDK (for LiteLLM)')
except ImportError as e:
    print(f'  ✗ OpenAI: {e}')
    sys.exit(1)

try:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    print('  ✓ GA4 Data API')
except ImportError as e:
    print(f'  ✗ GA4 Data API: {e}')
    sys.exit(1)

try:
    import gspread
    print('  ✓ gspread (Google Sheets)')
except ImportError as e:
    print(f'  ✗ gspread: {e}')
    sys.exit(1)

try:
    import pandas
    print('  ✓ pandas')
except ImportError as e:
    print(f'  ✗ pandas: {e}')
    sys.exit(1)

print('All imports successful!')
"

if [ $? -ne 0 ]; then
    error "Import validation failed. Check dependencies."
fi

log "✓ All Python modules validated"

# Step 9: Start the server in background
log "Starting server on port $PORT..."

# Create a startup script for proper background execution
# Uses python3 with fallback to python for cross-platform compatibility
cat > "$PROJECT_ROOT/.start_server.sh" << 'STARTUP_EOF'
#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null

# Use python3 if available, otherwise python
if command -v python3 &> /dev/null; then
    exec python3 main.py
else
    exec python main.py
fi
STARTUP_EOF

chmod +x "$PROJECT_ROOT/.start_server.sh"

# Start server in background with nohup
nohup "$PROJECT_ROOT/.start_server.sh" > "$PROJECT_ROOT/server.log" 2>&1 &
SERVER_PID=$!

log "Server starting with PID: $SERVER_PID"

# Step 10: Wait for server to be ready
log "Waiting for server to become ready..."

MAX_WAIT=60
WAIT_COUNT=0
SERVER_READY=false

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if curl -s "http://localhost:$PORT/health" > /dev/null 2>&1; then
        SERVER_READY=true
        break
    fi
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
    
    # Show progress every 10 seconds
    if [ $((WAIT_COUNT % 10)) -eq 0 ]; then
        log "Still waiting... ($WAIT_COUNT seconds)"
    fi
done

if [ "$SERVER_READY" = true ]; then
    log "✓ Server is ready!"
else
    error "Server failed to start within $MAX_WAIT seconds. Check server.log for details."
fi

# Step 11: Verify endpoint
log "Verifying API endpoint..."

HEALTH_RESPONSE=$(curl -s "http://localhost:$PORT/health")
if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    log "✓ Health check passed"
else
    warn "Health check response: $HEALTH_RESPONSE"
fi

# Done!
echo ""
echo "============================================================================="
echo "  DEPLOYMENT COMPLETE"
echo "============================================================================="
echo ""
echo "  Server is running on: http://localhost:$PORT"
echo "  PID: $SERVER_PID"
echo ""
echo "  Endpoints:"
echo "    - POST /query     : Process natural language queries"
echo "    - GET  /health    : Health check"
echo "    - GET  /docs      : API documentation (Swagger UI)"
echo ""
echo "  Test with:"
echo "    curl -X POST http://localhost:$PORT/query \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"query\": \"What are my top pages?\", \"propertyId\": \"123456789\"}'"
echo ""
echo "  Logs:"
echo "    - Server log: $PROJECT_ROOT/server.log"
echo "    - Deploy log: $PROJECT_ROOT/deploy.log"
echo "    - API log: $PROJECT_ROOT/api.log"
echo ""
echo "============================================================================="

# Save PID for later reference
echo $SERVER_PID > "$PROJECT_ROOT/.server.pid"

log "Deployment completed successfully at $(date)"
