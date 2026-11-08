#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Emre Yiğit Taşdelen
# Ask rag-api a question from the command line: sh ask.sh <model> "<question>"
cd /opt/aruba-bot
docker compose exec -T rag-api python - "$1" "$2" <<'EOF'
import json, sys, urllib.request
body = json.dumps({"model": sys.argv[1], "stream": False, "messages": [{"role": "user", "content": sys.argv[2]}]}).encode()
req = urllib.request.Request("http://localhost:8000/v1/chat/completions", body, {"Content-Type": "application/json"})
print(json.load(urllib.request.urlopen(req, timeout=900))["choices"][0]["message"]["content"])
EOF
