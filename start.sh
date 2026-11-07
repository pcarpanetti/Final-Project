#!/bin/sh
# Start RiskWatch on Mac or Linux. Run with: sh start.sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  exec python3 launch.py "$@"
elif command -v python >/dev/null 2>&1; then
  exec python launch.py "$@"
fi
echo "Python was not found. Install it from https://www.python.org/downloads/ and try again."
exit 1
