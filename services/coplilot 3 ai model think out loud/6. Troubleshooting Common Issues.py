# Check if Flask is running
ps aux | grep flask

# Check correct port
netstat -an | grep 5000

# Verify route is registered
flask routes