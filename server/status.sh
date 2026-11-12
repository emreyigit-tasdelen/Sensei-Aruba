#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Emre Yiğit Taşdelen
# Prints rag-api indexing status and recent errors.
cd /opt/aruba-bot
sudo docker compose exec -T rag-api python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
sudo docker compose logs --tail 5 rag-api 2>&1 | grep -iE "error|traceback|exception" | cut -c1-200
