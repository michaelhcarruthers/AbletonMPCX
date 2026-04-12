#!/bin/bash
# AMCPX — start MCP server + ngrok tunnel

set -e

cd /Users/rnikec/Projects/AMCPX

echo "Starting AMCPX server on port 8080..."
source venv/bin/activate
python app.py &
SERVER_PID=$!

echo "Waiting for server..."
for i in $(seq 1 30); do
  if curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/mcp | grep -qE '(200|405|400)'; then
    echo "Server ready."
    break
  fi
  sleep 0.5
done

echo "Starting ngrok tunnel..."
ngrok http 8080 &
NGROK_PID=$!

sleep 2

NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "import sys,json; tunnels=json.load(sys.stdin)['tunnels']; print(next(t['public_url'] for t in tunnels if t['public_url'].startswith('https')))") 2>/dev/null || echo "(check http://localhost:4040)"
echo ""
echo "====================================="
echo "  MCP endpoint (local):  http://localhost:8080/mcp"
echo "  MCP endpoint (public): $NGROK_URL/mcp"
echo "====================================="
echo ""
echo "Connect ChatGPT Desktop to: $NGROK_URL/mcp"
echo ""
echo "Press Ctrl+C to stop both."

trap "echo 'Stopping...'; kill $SERVER_PID $NGROK_PID 2>/dev/null" EXIT
wait
