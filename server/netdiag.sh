#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Emre Yiğit Taşdelen
# Network diagnostic for the published Caddy ports.
cd /opt/aruba-bot
ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' aruba-bot-caddy-1)
echo "caddy ip: $ip"
curl -sk -o /dev/null -w "direct-container: %{http_code}\n" --max-time 5 "https://$ip/"
curl -s -o /dev/null -w "localhost:80 %{http_code}\n" --max-time 5 http://127.0.0.1/
curl -sk -o /dev/null -w "localhost:443 %{http_code}\n" --max-time 5 https://127.0.0.1/
docker compose logs --tail 5 caddy 2>&1 | cut -c1-220
sysctl net.ipv4.ip_forward
iptables -t nat -S DOCKER 2>/dev/null | grep -E '443|80' | head
