#!/bin/bash

echo "================================================================="
echo "        SYSTEM DIAGNOSTIC: NETWORK & CONTAINER CONNECTION LOGS   "
echo "================================================================="

# 1. Check if Docker Daemon is accessible
if ! command -v docker &> /dev/null; then
    echo "[-] ERROR: Docker CLI command not found. Using local network diagnostic fallbacks..."
else
    echo "[+] SUCCESS: Docker system detected. Analyzing cluster states..."
    echo "-----------------------------------------------------------------"
    
    # Check if docker-compose.yml exists
    if [ -f "docker-compose.yml" ]; then
        docker compose ps
        echo "-----------------------------------------------------------------"
    else
        echo "[-] WARNING: docker-compose.yml not found in current directory"
        echo "[-] Current directory: $(pwd)"
    fi
fi

# 2. Test Localhost Application Ports
echo "[*] Testing port allocations..."
echo "Port 5000 (Web App): $( (echo > /dev/tcp/127.0.0.1/5000) &>/dev/null && echo '✅ OPEN' || echo '❌ CLOSED')"
echo "Port 27017 (MongoDB): $( (echo > /dev/tcp/127.0.0.1/27017) &>/dev/null && echo '✅ OPEN' || echo '❌ CLOSED')"

# 3. Fetch Application Logs (if Docker is running)
if command -v docker &> /dev/null && [ -f "docker-compose.yml" ]; then
    echo "-----------------------------------------------------------------"
    echo "[*] Fetching recent error logs from Web container:"
    docker compose logs --tail=20 web 2>/dev/null | grep -iE 'error|exception|failed|critical' || echo "No errors found"
    
    echo "-----------------------------------------------------------------"
    echo "[*] Fetching recent logs from MongoDB container:"
    docker compose logs --tail=20 mongo 2>/dev/null | grep -iE 'error|exception|failed|critical' || echo "No errors found"
fi

echo "================================================================="
