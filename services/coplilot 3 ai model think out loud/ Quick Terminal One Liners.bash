# Find all route definitions with their lines
grep -n "@app.route" . --include="*.py" -r

# Find all streaming endpoints
grep -n "text/event-stream" . --include="*.py" -r

# Find all generate functions
grep -n "def generate" . --include="*.py" -r -A 3

# Count how many times each streaming function is used
grep -r "stream_" . --include="*.py" | cut -d: -f2 | sort | uniq -c | sort -nr# Find all route definitions with their lines
grep -n "@app.route" . --include="*.py" -r

# Find all streaming endpoints
grep -n "text/event-stream" . --include="*.py" -r

# Find all generate functions
grep -n "def generate" . --include="*.py" -r -A 3

# Count how many times each streaming function is used
grep -r "stream_" . --include="*.py" | cut -d: -f2 | sort | uniq -c | sort -nr