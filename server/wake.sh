#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Emre Yiğit Taşdelen
# Run after the VM boots or resumes ("AI Başlat" calls it). Waits until HTTPS answers.
# Recovery ladder: restart open-webui + caddy (stale connections after resume),
# then restart the Docker daemon (broken container networking, seen after a boot-time docker update).
cd /opt/aruba-bot

wait_https() {
  i=0
  while [ $i -lt "$1" ]; do
    c=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 5 https://127.0.0.1/)
    [ "$c" = 200 ] && return 0
    i=$((i + 1)); sleep 3
  done
  return 1
}

wait_https 5 && { echo "https 200 (already up)"; exit 0; }
docker compose restart open-webui caddy >/dev/null 2>&1
wait_https 5 && { echo "https 200 after container restart"; exit 0; }
systemctl daemon-reload
systemctl restart docker
sleep 15
docker compose up -d >/dev/null 2>&1
wait_https 30 && { echo "https 200 after docker restart"; exit 0; }
echo "https still down: $c"
exit 1
