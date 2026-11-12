#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Emre Yiğit Taşdelen
# Lists docling-serve API paths and the convert-file request schema (diagnostic).
cd /opt/aruba-bot
sudo docker compose exec -T rag-api python - <<'EOF'
import json, urllib.request
d = json.load(urllib.request.urlopen("http://docling:5001/openapi.json"))
print(d["info"].get("version"))
print([p for p in d["paths"]])
EOF
