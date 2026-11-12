#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Emre Yiğit Taşdelen
# Idle check. "idle" = no model loaded in Ollama (unloaded after 5 idle minutes) and rag-api not indexing.
#   idle.sh          (systemd timer, every 5 min) drops the page cache when idle
#   idle.sh status   prints "idle" or "active" (used by the Windows sleep task)
cd /opt/aruba-bot || exit 0
status=active
loaded=$(docker compose exec -T ollama ollama ps 2>/dev/null | tail -n +2 | grep -c .)
if [ "$loaded" -eq 0 ] && docker compose exec -T rag-api python -c "import urllib.request,sys;sys.exit('indexing' in urllib.request.urlopen('http://localhost:8000/health').read().decode())" 2>/dev/null; then
  status=idle
fi
if [ "$1" = "status" ]; then echo "$status"; exit 0; fi
[ "$status" = idle ] || exit 0
cache=$(awk '/^Cached:/ {print int($2/1024)}' /proc/meminfo)
[ "$cache" -lt 1024 ] && exit 0
sync
echo 1 > /proc/sys/vm/drop_caches
echo "idle: dropped ${cache} MB page cache"
