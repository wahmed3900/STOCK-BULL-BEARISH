#!/bin/bash

echo "================================================================="
echo "        SYSTEM DIAGNOSTIC: NETWORK & CONTAINER CONNECTION LOGS   "
echo "================================================================="

# 1. Check if Docker Daemon is accessible to the system
if ! command -v docker &> /dev/null; then
    echo "[-] ERROR: Docker CLI command not found. Using local network diagnostic fallbacks..."
else
    echo "[+] SUCCESS: Docker system detected. Analyzing cluster states..."
    echo "-----------------------------------------------------------------"
    docker compose ps
    echo "-----------------------------------------------------------------"
fi

# 2. Test Localhost Application Ports
echo "[*] Testing port allocations..."
for port in 5000 27017 6379; do
    (echo > /dev/dev/tcp/127.0.0.1/$port) &>/dev/null && \
    echo "[+] Active connection listening on Port: $port" || \
    echo "[-] Warning: Port $port is closed or unreachable"
done

# 3. Stream Application Standard Output Logs
if command -v docker &> /dev/null; then
    echo "-----------------------------------------------------------------"
    echo "[*] Fetching recent error tracking exceptions from Fin App logs:"
    docker compose logs --tail=20 app | grep -iE 'error|exception|failed|critical'
    
    echo "-----------------------------------------------------------------"
    echo "[*] Fetching Celery worker broker connection synchronization logs:"
    docker compose logs --tail=20 celery_worker
fi
echo "================================================================="
