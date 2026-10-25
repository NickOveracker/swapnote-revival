#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Start a throwaway server with tests/test.toml, run the flow test, stop the server.
set -e
cd "$(dirname "$0")"
DATA=$(mktemp -d)
sed "s#DATA_DIR#$DATA#" test.toml > "$DATA/test.toml"
python3 -I ../hpp_server.py "$DATA/test.toml" > "$DATA/server.log" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null; rm -rf "$DATA"' EXIT
sleep 1
python3 -I flow_test.py http://127.0.0.1:18080
python3 -I retention_test.py
