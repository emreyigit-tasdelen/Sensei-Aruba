#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Emre Yiğit Taşdelen
# Quick speed test of the chat model inside the ollama container.
cd /opt/aruba-bot
sudo docker compose exec -T ollama ollama run qwen3:8b --verbose "Merhaba, tek cümleyle kendini tanıt. /no_think" 2>&1 | grep -E "load duration|eval rate"
