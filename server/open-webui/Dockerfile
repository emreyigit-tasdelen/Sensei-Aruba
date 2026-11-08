# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Emre Yiğit Taşdelen
# Open WebUI with the " (Open WebUI)" name suffix removed, so the UI shows only WEBUI_NAME ("Sensei-Aruba").
# Allowed by the Open WebUI license only while this deployment has 50 or fewer users in any 30-day period
# (https://docs.openwebui.com/license). Above that, delete this build and use the stock image again.
FROM ghcr.io/open-webui/open-webui:main
RUN sed -i "s/^    WEBUI_NAME += ' (Open WebUI)'$/    pass  # suffix removed (<=50 users, see Dockerfile)/" /app/backend/open_webui/env.py \
 && ! grep -q "WEBUI_NAME += ' (Open WebUI)'" /app/backend/open_webui/env.py
