# Sensei-Aruba — Installation and Usage Guide

[English](USAGE.md) · [Türkçe](tr/KULLANIM.md)

This document describes the **installation from scratch**, the **architecture**, the **reason for every setting**, the **daily use** and the **maintenance** of a fully local chatbot (no API, no tokens) that works on the Aruba VMC and Aruba CX 6200M CLI command indexes. Someone who knows nothing about it can follow it from start to finish and build the same system.

> The server password is **deliberately not included** in this document. Passwords must not be kept in plain-text files or documents.

---

## Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Hardware and virtual machine](#3-hardware-and-virtual-machine)
4. [Ubuntu Server installation](#4-ubuntu-server-installation)
5. [Windows PC side: SSH access](#5-windows-pc-side-ssh-access)
6. [Server preparation: disk, Docker, sudo](#6-server-preparation-disk-docker-sudo)
7. [Application files](#7-application-files)
8. [Starting the services and pulling the models](#8-starting-the-services-and-pulling-the-models)
9. [HTTPS (Caddy)](#9-https-caddy)
10. [Firewall](#10-firewall)
11. [rag-api: CLI index, search and judge](#11-rag-api-cli-index-search-and-judge)
12. [Automatic re-indexing](#12-automatic-re-indexing)
13. [First login and Open WebUI settings](#13-first-login-and-open-webui-settings)
14. [Daily use](#14-daily-use)
15. [Adding a new device or brand](#15-adding-a-new-device-or-brand)
16. [PDF and image documents](#16-pdf-and-image-documents)
17. [CPU, RAM and performance settings](#17-cpu-ram-and-performance-settings)
18. [Maintenance commands](#18-maintenance-commands)
19. [Troubleshooting (real problems met during setup)](#19-troubleshooting-real-problems-met-during-setup)
20. [Summary of changes made during setup](#20-summary-of-changes-made-during-setup)
21. [Security hardening](#21-security-hardening)
22. [Limits and next steps](#22-limits-and-next-steps)
23. [Memory and sleep management](#23-memory-and-sleep-management)

---

## 1. Overview

**Goal:** an assistant that answers users who ask about network-device CLI commands, based only on the real command index (no invention), in Turkish; that can read photos, search the internet when needed, and updates itself as new documents or indexes are added.

**Key decisions and their reasons:**

| Decision | Reason |
|---|---|
| The model was **not trained (no fine-tuning)**; **RAG** is used instead | No retraining is needed when a new document arrives; commands come verbatim from the index, which lowers the risk of invention. |
| Open models (Qwen), not Claude | Claude only runs through the Anthropic API/subscription; the local, token-free requirement needs open-weight models. |
| **Docker Compose** | Every component is isolated; start/stop with one command; the folder can be copied to another server; adding another brand later is easy. |
| **Ubuntu Server 26.04 LTS** (no GUI) | Most Docker/Ollama/Open WebUI documentation targets Ubuntu; a GUI wastes RAM and CPU. |
| **A separate model per device** | VMC and 6200M commands never mix; each model searches only its own index. |
| **Judge layer** | Every command in an answer is verified against the index, and a small LLM confirms whether the answer is supported by the context. |

**A note on fine-tuning:** no model was fine-tuned (fine-tuning / LoRA) in this project. Everything described as "tuning" is configuration: model choice, CPU/RAM limits, context length, search parameters, the system prompt, the synonym dictionary. All of them are described one by one below.

---

## 2. Architecture

```
 Browser (https://<VM-IP>)
        │  443 (HTTP 80 → automatic HTTPS redirect)
        ▼
 ┌─────────────┐
 │   caddy     │  TLS termination (self-signed certificate)
 └──────┬──────┘
        ▼
 ┌─────────────┐   OpenAI-compatible API ┌──────────────┐
 │ open-webui  │ ──────────────────────► │   rag-api    │  CLI index: SQLite FTS5 + vectors
 │ (UI)        │   models:               │  (FastAPI)   │  judge: command check + qwen3:1.7b
 │             │   aruba-vmc             └──────┬───────┘
 │             │   aruba-cx-6200m               │
 │             │                                ▼
 │             │ ───────────────────────► ┌──────────┐
 │             │   (raw models, embed)    │  ollama  │  qwen3:8b, qwen2.5vl:7b,
 └──────┬──────┘                          └──────────┘  qwen3:1.7b, bge-m3
        │ PDF/Word parsing
        ▼
 ┌─────────────┐
 │   docling   │
 └─────────────┘

 Server folder: /opt/aruba-bot
   compose.yaml, Caddyfile, rag-api/, sources/<device>/commands.jsonl
```

| Service | Image | Task | Port exposed |
|---|---|---|---|
| `ollama` | `ollama/ollama:latest` | Runs the models on CPU | None |
| `docling` | `quay.io/docling-project/docling-serve-cpu:latest` | Extracts text, tables and images from PDF/Word | None |
| `rag-api` | Local build (`./rag-api`) | CLI index, search, answer generation, judge | None |
| `open-webui` | `ghcr.io/open-webui/open-webui:main` (local build: name suffix removed, see 7.1) | Chat UI, users, image upload, web search, document RAG | None |
| `caddy` | `caddy:2` | HTTPS reverse proxy | 80, 443 |

The services reach each other over Docker's internal network by service name (`http://ollama:11434`, `http://rag-api:8000`, etc.). Only Caddy is exposed to the outside.

---

## 3. Hardware and virtual machine

### Current setup
| Resource | Value |
|---|---|
| Physical machine | Laptop, Intel i7-1255U (10 cores / 12 threads), 40 GB RAM, NVIDIA MX550 2 GB (not usable for LLMs) |
| VM | VMware Workstation, Ubuntu Server 26.04.1 LTS, 12 vCPU, **14 GB RAM** (24 GB at first install, see Section 23), 150 GB disk (LVM), no GPU |
| VM IP | `<VM-IP>`, user `<user>` |

**Measured performance (qwen3:8b, CPU):** prompt processing ~22 tokens/s, answer generation **~3 tokens/s**, model load ~25 s. An answer can take 1–3 minutes.

### Recommended sizes (for a new install)
| Scenario | vCPU | RAM | Disk | Model |
|---|---|---|---|---|
| No GPU (minimum) | 16 | 64 GB | 150 GB | qwen3:8b (slow) |
| 16 GB VRAM GPU (recommended) | 8 | 32 GB | 150–200 GB | qwen3:14b, qwen2.5vl:7b |
| 24 GB+ GPU | 8–12 | 48 GB | 200–300 GB | larger models |

**Disk:** 100 GB is enough but tight; 150 GB is comfortable. Disk usage should not exceed 80% (Docker and the databases can break on a full disk). Current usage: OS + Docker images ~20 GB, models ~14 GB, indexes ~1–2 GB.

---

## 4. Ubuntu Server installation

1. Download the Ubuntu Server 26.04 LTS ISO (the **Server** one, not Desktop).
2. Create the VM in the hypervisor (sizes above). The network adapter must be bridged or attached to the corporate network.
3. In the installer:
   - Installation type: **Ubuntu Server** (not minimized).
   - Disk: keep **"Use an entire disk" + "Set up this disk as an LVM group"** selected. LVM lets you grow the disk later without reinstalling.
   - User: `<user>` (or any name you like; this document writes it as `<user>`).
   - **Check "Install OpenSSH server".**
   - Do **not** select any of the suggested snap packages (including docker). We will install Docker with apt.
4. When the installation finishes, find the server's IP: `ip -4 addr` on the console.
5. If possible, fix the IP (DHCP reservation or netplan).

> By default the Ubuntu installer uses only part of the disk in LVM (here 73 GB of 150 GB). The remaining space is added in Section 6.

---

## 5. Windows PC side: SSH access

What is configured on the PC to connect to the server with a key instead of a password. All commands are run in **PowerShell 7**.

### 5.1 Creating a separate SSH key
Use a separate key for this server and **protect it with a passphrase**:

```powershell
ssh-keygen -t ed25519 -C aruba-bot -f "$HOME\.ssh\id_ed25519_aruba_bot"
```

To avoid typing the passphrase on every connection, use `ssh-agent`: `Start-Service ssh-agent; ssh-add "$HOME\.ssh\id_ed25519_aruba_bot"`.

### 5.2 SSH shortcut (`aruba-bot`)
Append to the end of `C:\Users\<user>\.ssh\config`:

```
Host aruba-bot
    HostName <VM-IP>
    User <user>
    IdentityFile ~/.ssh/id_ed25519_aruba_bot
    IdentitiesOnly yes
```

After that `ssh aruba-bot` and `scp file aruba-bot:/target/` work. `IdentitiesOnly yes` stops SSH from trying other keys.

### 5.3 Adding the key to the server (one time, with the password)
The key must be added to the server's `~/.ssh/authorized_keys`. This step asks for the server password:

```powershell
$k = Get-Content "$HOME\.ssh\id_ed25519_aruba_bot.pub"
ssh <user>@<VM-IP> "echo '$k' >> ~/.ssh/authorized_keys && echo KEY_OK"
```

Enter the password; you should see `KEY_OK`.

> **Why `type file.pub | ssh ...` was not used:** the PowerShell pipeline may transfer text with a different encoding and Windows line endings (CRLF); non-ASCII characters in the key comment can also cause trouble. Reading the key into a variable and writing it as a single line is safe.

### 5.4 Test
```powershell
ssh -o BatchMode=yes aruba-bot "echo LOGIN_OK"
```
`BatchMode=yes` forbids password prompts; if the key does not work it fails immediately.

---

## 6. Server preparation: disk, Docker, sudo

### 6.1 Sudo
Installation and maintenance commands run with `sudo`. Do not configure passwordless sudo (`NOPASSWD`); let `sudo` ask for the password.

### 6.2 Growing the disk (LVM)
```bash
sudo vgs                                              # the VFree column shows free space
sudo lvextend -r -l +100%FREE /dev/ubuntu-vg/ubuntu-lv
df -h /                                               # 73G → 146G
```
`-r` also grows the file system. If you enlarge the disk from the hypervisor, first run `sudo growpart /dev/sda 3` and `sudo pvresize /dev/sda3` (check disk/partition names with `lsblk`).

### 6.3 Installing Docker
From Ubuntu's own repository:
```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker <user>        # for docker without sudo (log in again)
sudo systemctl enable --now docker
docker --version                    # 29.1.3
docker compose version              # 2.40.3
```

### 6.4 Application folder
```bash
sudo mkdir -p /opt/aruba-bot
sudo chown <user>:<user> /opt/aruba-bot
mkdir -p /opt/aruba-bot/rag-api /opt/aruba-bot/sources
```

> **Warning (a mistake that happened):** if the `sources` folder does not exist and you run `docker compose up`, Docker creates it **owned by root**; then `<user>` cannot copy files into it (`Permission denied`). Fix: `sudo chown -R <user>:<user> /opt/aruba-bot/sources`.

---

## 7. Application files

Kept on the PC under `<repo>\server\` and copied to `/opt/aruba-bot/` on the server.

```
/opt/aruba-bot/
├── compose.yaml               # all services
├── Caddyfile                  # HTTPS setup
├── aruba-bot.service          # systemd: start/stop
├── aruba-bot-ingest.service   # systemd: re-indexing trigger
├── aruba-bot-ingest.timer     # systemd: trigger every 15 minutes
├── bench.sh                   # model speed test
├── status.sh                  # index status
├── rag-api/
│   ├── Dockerfile
│   └── app.py
├── idle.sh, wake.sh, ask.sh   # sleep/wake (Section 23), asking questions from the command line
└── sources/
    ├── aruba-vmc/commands.jsonl        # 73,039 lines
    ├── aruba-vmc/docs/                 # VMC PDF/Word/image documents (Section 16)
    ├── aruba-cx-6200m/commands.jsonl   # 160,201 lines
    └── aruba-cx-6200m/docs/
```

Copying (from the PC):
```powershell
scp <repo>\server\compose.yaml <repo>\server\Caddyfile <repo>\server\aruba-bot.service aruba-bot:/opt/aruba-bot/
scp <repo>\server\rag-api\app.py <repo>\server\rag-api\Dockerfile aruba-bot:/opt/aruba-bot/rag-api/
```

> **Windows line-ending warning:** `.sh` files and the `Caddyfile` written on Windows may contain CRLF line endings, which fail on Linux. After copying: `sed -i 's/\r$//' /opt/aruba-bot/status.sh` (for each shell/Caddy file).

### 7.1 compose.yaml — full content and explanations

```yaml
x-logging: &logging
  driver: json-file
  options: { max-size: "10m", max-file: "3" }
```
Each container's log is kept to at most 3 × 10 MB, which prevents the disk from filling up. The `&logging` YAML anchor is reused in every service with `logging: *logging`.

```yaml
  ollama:
    image: ollama/ollama:latest
    restart: unless-stopped
    environment:
      OLLAMA_MAX_LOADED_MODELS: "3"
      OLLAMA_NUM_PARALLEL: "1"
      OLLAMA_KEEP_ALIVE: "5m"
      OLLAMA_CONTEXT_LENGTH: "8192"
    cpus: "10"
    mem_limit: 10g
    volumes: [ "ollama:/root/.ollama" ]
```
| Setting | Value | Reason |
|---|---|---|
| `OLLAMA_MAX_LOADED_MODELS` | 3 | Chat (or vision) + judge + embedding can stay in memory together; no reload (~25 s) on every question. |
| `OLLAMA_NUM_PARALLEL` | 1 | One request at a time on CPU; parallel requests slow all of them down and multiply RAM use. |
| `OLLAMA_KEEP_ALIVE` | 5m | A model unused for 5 min is evicted from memory (to leave RAM free when idle; the first question waits ~25 s for the model to load). |
| `OLLAMA_CONTEXT_LENGTH` | 8192 | Context window; enough for RAG context + history, larger values increase RAM and time. |
| `cpus` | 10 | **CPU limit.** It may use 10 of the 12 vCPUs; 2 vCPUs stay free so SSH and the UI do not freeze while a model runs. |
| `mem_limit` | 10g | 10 GB of the VM's 14 GB RAM; qwen3:8b (~5.2 GB) + qwen3:1.7b (~1.4 GB) + context fit, the rest goes to the other services. |
| `restart: unless-stopped` | — | Starts automatically after a crash or when the server boots (unless stopped by hand). |

```yaml
  docling:
    image: quay.io/docling-project/docling-serve-cpu:latest
    environment:
      DOCLING_SERVE_ENABLE_UI: "false"
    cpus: "4"
```
The PDF/Word parser. CPU build (no GPU). Its own web UI is off; only Open WebUI uses it. **CPU limit 4**: so the model does not lose all the CPU while a large PDF is processed.

```yaml
  rag-api:
    build: ./rag-api
    cpus: "4"
    environment:
      OLLAMA_URL: http://ollama:11434
      CHAT_MODEL: qwen3:8b
      VISION_MODEL: qwen2.5vl:7b
      JUDGE_MODEL: qwen3:1.7b
    volumes:
      - ./sources:/sources:ro
      - ragdata:/data
```
The CLI index service (Section 11). **CPU limit 4**: so it does not lock up the machine during vector indexing. `sources` is mounted read-only (`:ro`); indexes are kept in the `ragdata` volume.

> **About the CPU limits:** 10 + 4 + 4 = 18, more than 12. That is normal: `cpus` is an **upper bound, not a reservation**. The services rarely run at full load at the same time, and none of them can lock the machine up alone.

```yaml
  open-webui:
    build: ./open-webui   # stock image, only the " (Open WebUI)" name suffix removed
    environment:
      OLLAMA_BASE_URL: http://ollama:11434
      ENABLE_PERSISTENT_CONFIG: "false"
      WEBUI_NAME: Sensei-Aruba
      DEFAULT_MODELS: aruba-vmc
      ENABLE_OPENAI_API: "true"
      OPENAI_API_BASE_URL: http://rag-api:8000/v1
      OPENAI_API_KEY: internal
      ENABLE_TITLE_GENERATION: "false"
      ENABLE_TAGS_GENERATION: "false"
      ENABLE_AUTOCOMPLETE_GENERATION: "false"
      ENABLE_FOLLOW_UP_GENERATION: "false"
      RAG_EMBEDDING_ENGINE: ollama
      RAG_EMBEDDING_MODEL: bge-m3
      ENABLE_RAG_HYBRID_SEARCH: "true"
      RAG_TOP_K: "8"
      CHUNK_SIZE: "1200"
      CHUNK_OVERLAP: "200"
      CONTENT_EXTRACTION_ENGINE: docling
      DOCLING_SERVER_URL: http://docling:5001
      ENABLE_WEB_SEARCH: "true"
      WEB_SEARCH_ENGINE: duckduckgo
    volumes: [ "webui:/app/backend/data" ]
```
| Setting | Explanation |
|---|---|
| `ENABLE_PERSISTENT_CONFIG: false` | Open WebUI normally writes its settings to the database on first start and then **ignores** env changes. With `false` the settings are read from this file on every start. Side effect: changes made in the Admin panel that conflict with these settings are reset on restart; make permanent changes in this file. |
| `DEFAULT_MODELS` | The model preselected in a new chat. |
| `build: ./open-webui` | Open WebUI forcibly appends " (Open WebUI)" to `WEBUI_NAME` in its code. `server/open-webui/Dockerfile` takes the stock image and removes that line with `sed`, so the UI shows only "Sensei-Aruba". **License:** Open WebUI's license allows this only for deployments with at most 50 users in 30 days (or with an enterprise license). If the user count exceeds 50, replace the `build:` line with `image: ghcr.io/open-webui/open-webui:main`. Update: `sudo docker compose build --pull open-webui && sudo docker compose up -d open-webui`. The check in the Dockerfile stops the build if the Open WebUI code changes and the line is not found. |
| `OPENAI_API_BASE_URL` | Adds rag-api as an "OpenAI-compatible" connection; the device models come from here. |
| `OPENAI_API_KEY: internal` | rag-api does not check keys; it is a placeholder because Open WebUI does not allow an empty value, not a secret. |
| `ENABLE_*_GENERATION: false` | After every message Open WebUI makes **extra LLM calls** for titles, tags, autocomplete and follow-up questions. On CPU each takes minutes; turned off. |
| `RAG_*`, `CHUNK_*` | For Open WebUI's own document RAG (PDF uploads): bge-m3 embedding, hybrid search, best 8 chunks, 1200-character chunks with 200 characters of overlap. |
| `CONTENT_EXTRACTION_ENGINE: docling` | Uploaded PDF/Word files are parsed with Docling (including tables and images). |
| `ENABLE_WEB_SEARCH`, `WEB_SEARCH_ENGINE` | Internet search through DuckDuckGo when "Web Search" is switched on in a chat. No outside request is made unless it is switched on. |

```yaml
  caddy:
    image: caddy:2
    ports: [ "80:80", "443:443" ]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy:/data
```
The only service exposed to the outside. The `caddy` volume stores the certificates.

```yaml
volumes:
  caddy:     # certificates
  ragdata:   # CLI indexes (index.db, vec_*.npy, embedding model)
  ollama:    # downloaded models
  webui:     # users, chats, uploaded documents
```

### 7.2 aruba-bot.service — start/stop service
```ini
[Unit]
Description=Sensei-Aruba chatbot (docker compose)
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/aruba-bot
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```
Installation:
```bash
sudo cp /opt/aruba-bot/aruba-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aruba-bot
```
`enable` starts it automatically at server boot. `docker compose down` removes the containers but **keeps the volumes (models, indexes, users)**.

---

## 8. Starting the services and pulling the models

```bash
cd /opt/aruba-bot
sudo docker compose pull                  # download the images
sudo docker compose up -d --build         # build rag-api, start everything
sudo docker compose ps                    # all should be "running"
```

Models (inside the Ollama container):
```bash
sudo docker compose exec ollama ollama pull bge-m3          # 1.2 GB  embedding (document RAG)
sudo docker compose exec ollama ollama pull qwen3:8b        # 5.2 GB  main chat model
sudo docker compose exec ollama ollama pull qwen2.5vl:7b    # 6.0 GB  image reading
sudo docker compose exec ollama ollama pull qwen3:1.7b      # 1.4 GB  judge
sudo docker compose exec ollama ollama list
```

| Model | Task | Why this model |
|---|---|---|
| `qwen3:8b` | Answer generation | Good Turkish, strong instruction following; the largest reasonable size that runs on CPU. |
| `qwen2.5vl:7b` | Reading photos/screenshots | OCR + commentary on images such as CLI output or topology screens. |
| `qwen3:1.7b` | Judge | Enough for a short APPROVE/REJECT verdict, and fast. |
| `bge-m3` | Open WebUI document embedding | Multilingual (Turkish + English). |

**Speed test** (`bench.sh`):
```sh
#!/bin/sh
cd /opt/aruba-bot
sudo docker compose exec -T ollama ollama run qwen3:8b --verbose "Merhaba, tek cümleyle kendini tanıt. /no_think" 2>&1 | grep -E "load duration|eval rate"
```
`eval rate` is the generation speed (tokens/s). `/no_think` turns off qwen3's "thinking" mode.

---

## 9. HTTPS (Caddy)

`Caddyfile`:
```
https:// {
	tls internal {
		on_demand
	}
	reverse_proxy open-webui:8080
}
```
Caddy is on the same Compose network as the other services and proxies to Open WebUI by service name (`open-webui:8080`); only Caddy's 80/443 ports are published. **Do not use** `127.0.0.1:8080`: Caddy runs in its own container, so that address is Caddy itself and returns 502 (see [Troubleshooting](troubleshooting.md)).
- `tls internal`: with no domain name and no validation from the internet, Caddy creates a certificate with **its own local certificate authority**. Traffic is encrypted; the browser shows a "not secure" warning on first visit → "Advanced → Proceed".
- HTTP (80) requests are redirected to HTTPS automatically (308).
- `on_demand`: the certificate is created on the first request for the name or IP the client connected to; there is no fixed IP in the Caddyfile.
- `curl -k https://localhost/` and `curl -k https://127.0.0.1/` work.

**Removing the warning completely (optional):** add Caddy's root certificate to the PCs as trusted:
```bash
sudo docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
```
Copy the file to the PC and import it into Windows "Trusted Root Certification Authorities". If you have a company domain and a corporate certificate, you can use those certificate files instead of `tls internal`.

---

## 10. Firewall

```bash
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP → HTTPS redirect
sudo ufw allow 443/tcp     # HTTPS
sudo ufw --force enable
sudo ufw status
```
Ollama (11434), rag-api (8000), Docling (5001) and Open WebUI (8080) are **never published**; they are reachable only on Docker's internal network.

> Note: Docker bypasses ufw rules for ports published with `ports:`. That is why only Caddy's ports are published in compose; do not add `ports:` to other services.

---

## 11. rag-api: CLI index, search and judge

Source: `server/rag-api/app.py`. Python 3.12, FastAPI, fastembed, NumPy, SQLite.

### 11.1 Why a separate service?
VMC (73k) + 6200M (160k) = **233k command lines**. Uploading them to Open WebUI as files would be slow and inaccurate. In CLI commands **exact word matching** is also critical, which generic document RAG does not provide. rag-api is brand-agnostic and keeps a separate index per device.

### 11.2 Source file format (`commands.jsonl`)
Each line is a JSON object:
```json
{"device": "aruba-cx-6200m", "mode": "config", "command": "aaa authentication port-access dot1x authenticator", "description": "Configure 802.1X authenticator"}
```
| Field | Required | Description |
|---|---|---|
| `command` | Yes | The full command, including argument placeholders (`<IFNAME>`, `WORD`, `A.B.C.D`). |
| `description` | No | Command description (used in search). |
| `mode` | No | `config`, `enable`, `exec`, etc. |
| `device` | No | Informational; the real device name comes from the **folder name**. |

These files were produced by crawling the CLI tree (`?` help) from a live device with `aruba_crawl.py`. The same crawl also produces `.md` tree files; rag-api uses not the `.md` but **`commands.jsonl`** (same content, line-based and suitable for indexing).

### 11.3 Indexing (two stages)
At startup and on every `/ingest` call:

1. For every folder under `/sources` the SHA-256 of `commands.jsonl` is computed. If it is unchanged the device is skipped (only loaded into memory).
2. **Stage 1 — keyword index (all devices, within minutes):**
   - Lines ending with `<cr>`, `|`, `>`, `>>` are dropped (they are "Enter" and output-redirect repeats).
   - Duplicate commands are dropped.
   - An SQLite table `cmds` and an **FTS5** full-text index (BM25 ranking) are built.
   - The device becomes usable immediately: state `keyword-only (vectors queued)`.
3. **Stage 2 — vector index (device by device, takes long):**
   - Embedding model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (fastembed/ONNX, multilingual, 384 dimensions, fast on CPU). It can match a Turkish question with an English description.
   - Text: `"<command> — <description>"`, in batches of 256.
   - Normalized vectors are saved as `/data/vec_<device>.npy`.
   - When done, the state becomes the record count (e.g. `"aruba-vmc": 61234`) and the overall state `ready`.

Why two stages: with a single stage every device waited until the vectors were finished; the first device (6200M) had to finish before VMC appeared at all.

> **Important:** if the rag-api container restarts, **partial vector indexing starts over** (finished devices are kept). Apply code changes after indexing finishes.

### 11.4 Search (hybrid + query expansion)
1. **Query expansion (`SYNONYMS`):** user phrases are translated into CLI terms:

   | The user writes | Added to the search |
   |---|---|
   | `802.1x`, `8021x` | `dot1x port-access authenticator` |
   | `mab`, `mac auth` | `mac-auth port-access` |
   | `radius` | `radius-server radius aaa` |
   | `vlan` | `vlan access trunk` |
   | `ge 1 1 1`, `port 1/1/1`, `int 1 1 1` | `interface 1/1/1` |
   | `trunk` | `vlan trunk allowed native` |
   | `lacp`, `port-channel` | `lag lacp` |

2. **Stop words (`STOP`)** are removed from the search: bana, için, yaz, nasıl, ver, config, komut, etc. Bare numbers are removed too.
3. **BM25 (FTS5):** words are searched with `OR`, best 50 results.
4. **Vector:** cosine similarity between the query vector and all of the device's vectors, best 50.
5. **Merging — Reciprocal Rank Fusion:** the scores `1 / (60 + rank)` are summed per result; the best **15** (`TOP_K`) commands are given to the model as context.
6. **Device isolation:** search is done only over the records of the selected model (device).

### 11.5 Answer generation
The message sent to the model contains:
- **System prompt:** rely only on the commands in the CONTEXT, do not invent; give commands in backticks and verbatim; explain the `<...>` fields; state the mode; when a configuration is requested, combine the commands in order (global first, then under `interface ...`) in a code block; if it is not in the context say "Bu komut dizinde bulunamadı" (this command was not found in the index); answer in Turkish.
- The last 6 chat messages (history).
- `BAĞLAM: [device | mode] command — description` lines + `SORU` (question).
- `think: false` → qwen3's thinking output is off (on CPU it doubled the time).

**If there is a photo:** when the message contains an image, the request goes automatically to `qwen2.5vl:7b` (the image is passed as base64).

### 11.6 Judge (two layers)
Appended to the end of the answer:

1. **Deterministic verification (always):** the `backticked` commands and the lines of ```code blocks``` in the answer are extracted. Each is looked up in the device's command tree: same first word + same number of words + each word either identical or a placeholder in the tree (`<...>`, UPPERCASE, `A.B.C.D`, `[...]`). Result: `✅ N commands exist in the index · ⚠️ not in the index: ...` (in the actual output: `✅ N komut dizinde var · ⚠️ dizinde yok: ...`)
2. **Judge LLM (`qwen3:1.7b`):** reads the context and the answer and gives a single line: `ONAY: ...` (approve) or `RED: ...` (reject). It does not run if the context is empty. To turn it off, set `JUDGE_MODEL: ""` in compose.

> The ⚠️ mark does not always mean an error: commands in submodes the crawler did not visit (e.g. some under `interface`) may not be in the index. Check a ⚠️ command on the device with `?`.

### 11.7 API endpoints
| Endpoint | Description |
|---|---|
| `GET /v1/models` | Device list = model list (Open WebUI reads this). |
| `POST /v1/chat/completions` | OpenAI-compatible chat; supports streaming. |
| `GET /health` | `{"status": "...", "devices": {...}}` index status. |
| `POST /ingest` | Starts re-indexing; does not start if indexing is already running. |

`status.sh`:
```sh
#!/bin/sh
cd /opt/aruba-bot
sudo docker compose exec -T rag-api python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
sudo docker compose logs --tail 5 rag-api 2>&1 | grep -iE "error|traceback|exception" | cut -c1-200
```

### 11.8 Dockerfile
```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx numpy fastembed
COPY app.py .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```
The embedding model is downloaded on first run and cached under `/data/models`.

### 11.9 Configurable environment variables
| Variable | Default | Description |
|---|---|---|
| `CHAT_MODEL` | `qwen3:8b` | Answer model |
| `VISION_MODEL` | `qwen2.5vl:7b` | Vision model |
| `JUDGE_MODEL` | `""` (`qwen3:1.7b` in compose) | If empty the judge LLM is off |
| `EMB_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Vector model (if you change it, delete the whole index and rebuild) |
| `TOP_K` | 15 | Number of commands given to the model |
| `DOC_TOP_K` | 4 | Number of document chunks given to the model |
| `DOCLING_URL` | `http://docling:5001` | Document converter |
| `OLLAMA_URL` | `http://ollama:11434` | |

---

## 12. Automatic re-indexing

`aruba-bot-ingest.service`:
```ini
[Unit]
Description=Re-index changed device sources in rag-api

[Service]
Type=oneshot
WorkingDirectory=/opt/aruba-bot
ExecStart=/usr/bin/docker compose exec -T rag-api python -c "import urllib.request as u; print(u.urlopen(u.Request('http://localhost:8000/ingest', method='POST')).read().decode())"
```

`aruba-bot-ingest.timer`:
```ini
[Unit]
Description=Check /opt/aruba-bot/sources for new or changed devices every 15 minutes

[Timer]
OnBootSec=10min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
```

Installation:
```bash
sudo cp /opt/aruba-bot/aruba-bot-ingest.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aruba-bot-ingest.timer
systemctl list-timers | grep aruba     # next run time
```
rag-api re-indexes only the **changed** files (SHA-256 comparison), so running every 15 minutes is cheap. Triggers that arrive while indexing is running are ignored.

> **Installation state:** the timer is active (every 15 minutes). First full index: aruba-cx-6200m 102,032, aruba-vmc 57,741 commands (after filtering). 6200M vectors took ~1.5 h, VMC ~1 h.

---

## 13. First login and Open WebUI settings

1. Open `https://<VM-IP>` in a browser → pass the certificate warning.
2. **The first user to register becomes admin.** Create your own account right away.
3. Recommended admin settings:
   - **Admin → Settings → Models:** hide the raw models `qwen3:8b`, `qwen2.5vl:7b`, `qwen3:1.7b`, `bge-m3` from normal users. Users should only see `aruba-vmc` and `aruba-cx-6200m`.
   - **Admin → Settings → General:** set new sign-ups to "pending" (so unauthorized people cannot open an account and use the bot).
   - **Admin → Users:** add the team members.

---

## 14. Daily use

- **Choosing the device:** from the model menu above the chat, `aruba-vmc` or `aruba-cx-6200m`. Each model knows only its own device's commands; devices never mix.
- **Example questions:**
  - `802.1x config yaz bana port ge 1 1 1 için` (write me an 802.1x config for port ge 1/1/1)
  - `show komutlarıyla aaa ayarlarını nasıl görürüm?` (how do I see the AAA settings with show commands?)
  - `vlan 10 oluşturup 1/1/5 portuna access olarak ata` (create VLAN 10 and assign it to port 1/1/5 as access)
- **End of the answer:** `Doğrulama` (are the commands in the index) and `Hakem` (ONAY/RED) lines. If you see ⚠️ or RED, treat the answer with caution.
- **Photo:** `+` → upload an image (CLI output, error screen). The vision model is used automatically.
- **Internet search:** switch it on for that message with the "Web Search" button in the chat box.
- **Wait time:** on CPU an answer takes 1–3 minutes; the first question takes longer because it loads the model.
- **While the index is being prepared:** a note "Vektör indeksi hazırlanıyor, şimdilik anahtar kelime araması" (vector index being prepared, keyword search for now) appears at the start of the answer; answers still work.

---

## 15. Adding a new device or brand

**Rule:** `sources/<device-name>/commands.jsonl`. **Folder name = model name in the WebUI.** Use lowercase and hyphens (e.g. `aruba-cx-6300`, `cisco-c9300`).

### Steps (from the PC, PowerShell)
```powershell
ssh aruba-bot "mkdir -p /opt/aruba-bot/sources/aruba-cx-6300"
scp <repo>\crawler\aruba-cx-6300\commands.jsonl aruba-bot:/opt/aruba-bot/sources/aruba-cx-6300/
```
Then either wait 15 minutes (the timer) or trigger it right away:
```powershell
ssh aruba-bot "sudo systemctl start aruba-bot-ingest"
```
Follow the status:
```powershell
ssh aruba-bot "sh /opt/aruba-bot/status.sh"
```
Refresh the page in the WebUI (F5) → the new model is in the list. Keyword search is ready in a few minutes, and the vectors finish in the background.

### Updating an existing device
Copy the new `commands.jsonl` to the same path. Because the file changed, only that device is re-indexed.

### Removing a device
```bash
rm -r /opt/aruba-bot/sources/<device>
sudo docker compose restart rag-api
```
(Note: old records stay in SQLite but do not appear in the model list; for a full cleanup delete `index.db` in the `ragdata` volume and re-index.)

### A different brand
- The format is the same (Section 11.2). rag-api is brand-agnostic.
- `aruba_crawl.py` is specific to the Aruba CLI. For Cisco/Juniper etc. you need a crawler that produces the same format, or a converter from the official command reference.
- For brand terms you can add mappings to the `SYNONYMS` dictionary in `app.py` (e.g. for Cisco `gi1/0/1 → interface GigabitEthernet1/0/1`). Rebuild rag-api after changing it.

---

## 16. PDF and image documents

### 16.1 Per-device documents (recommended)
Each device's documents are placed next to that device's command index and used **in the same model**. The `aruba-vmc` model searches both the VMC command index and the VMC documents in a question; it never sees the 6200M documents.

```
/opt/aruba-bot/sources/<device>/docs/      ← put the files here (subfolders allowed)
```

| Supported | Processed by |
|---|---|
| `.pdf .docx .pptx .xlsx .html .htm` | Docling (text, tables, heading structure; **OCR is on** → text in scanned PDFs and screenshots is read) |
| `.png .jpg .jpeg .tif .tiff .bmp` | Docling OCR |
| `.md .txt` | Read directly |

**Adding (from the PC):**
```powershell
scp "<file>.pdf" aruba-bot:/opt/aruba-bot/sources/aruba-vmc/docs/
ssh aruba-bot "sudo systemctl start aruba-bot-ingest"     # process right away (otherwise automatically within 15 min)
ssh aruba-bot "sh /opt/aruba-bot/status.sh"               # "docs": {"aruba-vmc": {"files": 1, "chunks": N}}
```
- **Updating:** overwrite with the same name → only that file is re-processed (SHA-256).
- **Deleting:** delete the file → its chunks are deleted at the next indexing.
- While processing, the state shows `converting <file>` / `embedding`. If there is an error, it appears under `errors` in the `/health` output with the file name; the other files keep being processed.

**How it works:**
1. The file is converted to **Markdown** through Docling's asynchronous API (`/v1/convert/file/async`) (images as placeholders, OCR on).
2. The Markdown is split by headings, and each section into chunks of ~1000 characters (150 characters of overlap); each chunk carries its heading.
3. The chunks are indexed in SQLite FTS5 (`docs_fts`) and as vectors (`/data/dvec_<device>.npy`); the same multilingual embedding model is used.
4. When the conversion finishes, Docling's models in memory are unloaded (`/v1/clear/converters`) → saves RAM.
5. When a question arrives, in addition to the command search the best **4** document chunks (`DOC_TOP_K`) are added to the context under a `DÖKÜMAN:` heading.
6. The model writes the source of what it took from the documents as **`[file › heading]`**. The judge LLM also sees the document chunks as context.

> **About images:** OCR reads the **text** in images (CLI screenshot, table image). It does not interpret the meaning of diagrams (such as a topology drawing); for that, upload the image directly into the chat (the vision model `qwen2.5vl:7b` is used).

> **Performance:** large PDFs can take minutes on CPU (Docling is limited to 4 CPUs). Document text added to the context lengthens the answer time by ~30–60 s.

### 16.1.1 Very large PDFs (thousands of pages)
Docling takes hours or days for thousands of pages on CPU. Convert large PDFs that have a text layer to Markdown on the PC with `server\tools\pdf_to_md.py` and upload them as `.md`:
```powershell
python -m venv venv; .\venv\Scripts\pip install pymupdf
.\venv\Scripts\python server\tools\pdf_to_md.py "ArubaOS-8.x-CLI-Reference-Guide.pdf" ArubaOS-8.x-CLI-Reference-Guide.md
scp ArubaOS-8.x-CLI-Reference-Guide.md aruba-bot:/opt/aruba-bot/sources/aruba-vmc/docs/
```
- The PDF's bookmarks (table of contents) become headings → source citations look like `[file › command › section]`.
- Word spacing is preserved (tools such as markitdown ran the words together in this PDF: `FollowingliststheupdatestotheAOSCLI`).
- Page headers/footers are discarded. It does no OCR; use Docling for image-heavy PDFs.

### 16.1.2 Installed documents (2026-10-31)
| Device | File | Method |
|---|---|---|
| aruba-vmc | ArubaOS-8.x-CLI-Reference-Guide.md (4111 pages, 9,840 headings) | pdf_to_md.py |
| aruba-vmc | AP-630_Install_Guide_EN.pdf | Docling |
| aruba-vmc | Aruba ISE.pdf (images only, 9 pp.) | Docling OCR |
| aruba-vmc | 1791201570899.pdf (EntraID EAP-TLS technote) | Docling |
| aruba-vmc | Wi-Fi design and deployment … .pdf | Docling |
| aruba-cx-6200m | — (no PDF specific to the 6200M; the CX 6000 datasheet was not added because it is a different series) | |

### 16.2 Open WebUI Knowledge (alternative, general documents)
For general documents not tied to a device you can also use Open WebUI's own RAG: **Workspace → Knowledge → +** → upload files → in a chat pick the collection with `#` and ask with the raw `qwen3:8b` model. This route does not work together with the device models (verification/judge).

---

## 17. CPU, RAM and performance settings

This section lists all the "fine settings" in one place. None of them is model training.

| Where | Setting | Value | Effect |
|---|---|---|---|
| compose / ollama | `cpus` | 10 | The model may use 10 of the 12 vCPUs; SSH and the UI do not freeze. **Why it was added:** without a limit the server did not answer SSH for minutes while a model ran. |
| compose / ollama | `mem_limit` | 10g | Prevents RAM overflow. |
| compose / ollama | `OLLAMA_NUM_PARALLEL` | 1 | One request; most efficient on CPU. |
| compose / ollama | `OLLAMA_MAX_LOADED_MODELS` | 3 | Fewer model reloads. |
| compose / ollama | `OLLAMA_KEEP_ALIVE` | 5m | How long a model stays in memory. |
| VMware | `memsize` | 14336 (14 GB) | RAM given to the VM (Section 23). |
| compose / ollama | `OLLAMA_CONTEXT_LENGTH` | 8192 | Context size. |
| compose / docling | `cpus` | 4 | PDF processing limit. |
| compose / rag-api | `cpus` | 4 | Vector indexing limit. |
| compose / open-webui | `ENABLE_*_GENERATION` | false | Unneeded background LLM calls are off. |
| compose / all | log `max-size`/`max-file` | 10m × 3 | Disk protection. |
| rag-api | `think: false` | — | qwen3 thinking output is off; answer time drops to about half. |
| rag-api | `TOP_K` | 15 | Less context = faster; more = more thorough. |
| rag-api | Filter | `<cr>`, `\|` etc. | Unneeded lines dropped; the index got smaller. |

### Ways to speed it up
| Option | Gain | Cost |
|---|---|---|
| `CHAT_MODEL: qwen3:4b` | ~2× faster | Answer quality drops |
| `JUDGE_MODEL: ""` | ~20–60 s per answer | No judge LLM (deterministic verification continues) |
| `OLLAMA_CONTEXT_LENGTH: 4096` | Less RAM, a little speed | History is shorter in long chats |
| GPU server | 10–20× | Hardware |

After a change: `sudo docker compose up -d` (with `--build` if the rag-api code changed).

---

## 18. Maintenance commands

All on the server, inside `/opt/aruba-bot` (they can also be run from the PC by prefixing `ssh aruba-bot "..."`).

| Task | Command |
|---|---|
| Stop the system | `sudo systemctl stop aruba-bot` |
| Start the system | `sudo systemctl start aruba-bot` |
| Status | `sudo docker compose ps` |
| Resource usage | `sudo docker stats --no-stream` |
| Logs | `sudo docker compose logs --tail 50 rag-api` (the service name can be changed) |
| Index status | `sh status.sh` |
| Re-index by hand | `sudo systemctl start aruba-bot-ingest` |
| Model speed test | `sh bench.sh` |
| Update images | `sudo docker compose pull && sudo docker compose up -d` |
| Update rag-api code | copy `app.py` with `scp` → `sudo docker compose up -d --build rag-api` |
| Add/remove a model | `sudo docker compose exec ollama ollama pull <model>` / `ollama rm <model>` |
| Disk | `df -h /` |
| Docker cleanup | `sudo docker system prune` (unused images/containers) |
| Backup (volume) | `sudo docker run --rm -v aruba-bot_webui:/v -v /root:/b alpine tar czf /b/webui.tgz -C /v .` |

**What to back up:** the `/opt/aruba-bot` folder (code + sources) and the `aruba-bot_webui` volume (users, chats, documents). Models and indexes can be regenerated. The easiest way is a VM snapshot in the hypervisor.

**Moving to another server:** Sections 4–6 on the new server → copy the `/opt/aruba-bot` folder → Section 8 (pull the models) → 7.2 and 12 (systemd) → optionally restore the webui volume backup.

---

## 19. Troubleshooting (real problems met during setup)

| Symptom | Cause | Fix |
|---|---|---|
| `ssh: connect ... Connection timed out` while a model runs | The model takes all the CPU (the VM shares the CPU with the laptop) | Ollama `cpus: 10`; run long commands on the server with `nohup ... &` and read the result from a file |
| `scp: dest open ... No such file or directory / Failure` | Docker created the `sources` folder owned by root | `sudo chown -R <user>:<user> /opt/aruba-bot/sources` |
| Answer: "İndeks hazırlanıyor ... Bu komut dizinde bulunamadı" + Judge RED | The answer was generated with empty context before the index was ready | Two-stage indexing; the judge does not run when the context is empty |
| The VMC model is not in the list | Indexing was sequential, VMC waited for 6200M | Two-stage indexing (Section 11.3) |
| A "802.1x" question finds nothing | The user's term ≠ the CLI term (`dot1x`) | The `SYNONYMS` dictionary |
| An Open WebUI setting in compose is not applied | Persistent config was written to the DB on first start | `ENABLE_PERSISTENT_CONFIG: "false"` |
| `curl https://localhost` error 35 | The certificate was created for the IP | `curl -k https://<VM-IP>/` |
| `.sh` file "not found" / strange error | Windows CRLF line endings | `sed -i 's/\r$//' file` |
| First model test took 29 minutes | The SSH connection dropped and the request never reached the model + slow CPU | Measured again with `bench.sh`: ~3 tokens/s |

**General diagnostics:**
```bash
sudo docker compose ps
sudo docker compose logs --tail 50 <service>
sh status.sh
uptime; free -h; df -h /
```

---

## 20. Summary of changes made during setup

### Windows PC
| Change | Where |
|---|---|
| SSH key (for this server only) | `%USERPROFILE%\.ssh\id_ed25519_aruba_bot` (+ `.pub`) |
| SSH shortcut `aruba-bot` | appended to `%USERPROFILE%\.ssh\config` |
| Server host key | `%USERPROFILE%\.ssh\known_hosts` |
| `server\` | compose.yaml, Caddyfile, systemd files, scripts, rag-api\ (app.py, Dockerfile), tools\pdf_to_md.py |
| `crawler\` | CLI crawler (`aruba_crawl.py`); the outputs (`commands.jsonl`) are generated from the device |
| `vm-control\` | VM suspend/resume scripts (Section 23) and the desktop shortcuts **"AI Başlat"** (AI Start), **"AI Uyut"** (AI Sleep) |
| VMware `.vmx` | `memsize` 24836 → 14336; backup: `*.vmx.bak-24g` |

No system settings are changed on the PC beyond these.

### Server (VM)
| Change | Detail |
|---|---|
| SSH | The key is added to `~/.ssh/authorized_keys`; `~` permissions `go-w`, `~/.ssh` 700, `authorized_keys` 600 |
| Disk | LVM root partition 73 GB → 146 GB |
| Packages | `docker.io`, `docker-compose-v2`; the user is added to the `docker` group |
| Application | `/opt/aruba-bot` |
| systemd | `aruba-bot.service`, `aruba-bot-ingest.service` + `.timer`, `aruba-bot-idle.service` + `.timer` (all enabled) |
| Scripts | `idle.sh`, `wake.sh`, `netdiag.sh` (network diagnostics), `docling-api.sh` (Docling API list) |
| Firewall | ufw active: 22, 80, 443 |
| Docker volumes | `aruba-bot_ollama`, `aruba-bot_webui`, `aruba-bot_ragdata`, `aruba-bot_caddy` |

---

## 21. Security hardening

Only Caddy (80/443) is exposed to the outside. For live use, apply the following.

**Access**
- Use a strong, unique password for the admin account and keep it in a password manager. Do not keep the password in plain text in documents, the repo, chats or scripts.
- Use keys for SSH and protect the key with a passphrase. After you have verified that key login works, turn off password login: `PasswordAuthentication no` under `/etc/ssh/sshd_config.d/`, then `sudo systemctl restart ssh`.
- Do not configure passwordless sudo (`NOPASSWD`).
- Remove unused keys from `~/.ssh/authorized_keys`.

**Network**
- ufw should allow only 22, 80 and 443; restrict SSH to the management network (`sudo ufw allow from <management-network> to any port 22`).
- Do not add `ports:` to any service other than Caddy in compose (Section 10).
- A corporate certificate can be used instead of the self-signed one (Section 9).

**Application**
- In Open WebUI create the first account (admin) yourself, set new sign-ups to "pending", and hide the raw models from users (Section 13).
- While web search is on, queries go to DuckDuckGo; do not use it for questions that contain sensitive information. To turn it off completely, set `ENABLE_WEB_SEARCH: "false"` in compose.
- The crawler asks for the device password once per run and does not write it to disk. Password and key files are in `.gitignore`.

**Maintenance**
- Operating system: `sudo apt-get update && sudo apt-get upgrade` (`unattended-upgrades` for automatic security updates). Images: `sudo docker compose pull && sudo docker compose up -d`.
- Backup: Section 18.

---

## 22. Limits and next steps

**Known limits**
- Slow on CPU: ~3 tokens/s, an answer takes 1–3 min. The server shares the CPU with the laptop.
- Commands in submodes the crawler did not visit are not in the index; verification may show ⚠️ for them.
- The certificate is self-signed (browser warning).
- Diagrams inside documents are not interpreted, only the text is read with OCR.
- While the VM is suspended, the bot cannot be reached from other computers; waking takes ~30 s – 3 min.

**Recommended next steps**
1. A GPU server (16 GB+ VRAM) → `qwen3:14b`, 10× speed. The architecture carries over unchanged.
2. Crawlers for other brands.
3. Regular quality measurement with a 30–50 question test set.
4. Adding approved correct answers back to the index as "approved Q&A".
5. If the answer style or command format causes problems, as a last resort a small LoRA fine-tune.

---

## 23. Memory and sleep management

### 23.1 The problem
The VM runs on the laptop under VMware Workstation. VMware **does not give back memory the VM has used once** to Windows, even if it is freed inside the VM. At first install the VM had 24 GB; together with another VM running next to it, free RAM in Windows fell to **1.1 GB**. Inside the VM the applications used only ~3.5 GB; the rest was Linux file cache of the model files.

### 23.2 A four-layer solution

| Layer | What it does | Where |
|---|---|---|
| 1. Model unloading | Ollama evicts models from memory after 5 min of non-use | `compose.yaml` → `OLLAMA_KEEP_ALIVE: "5m"` |
| 2. In-VM cache dropping | When idle (no model loaded, no indexing), drops the Linux file cache | Server: `idle.sh` + `aruba-bot-idle.timer` (every 5 min) |
| 3. Shrinking the VM memory | RAM given to the VM 24 GB → 14 GB | VMware `.vmx` → `memsize = "14336"` |
| 4. VM sleep | **Manual**: the desktop shortcut "AI Uyut" (AI Sleep) suspends the VM. The automatic sleep (scheduled task) was removed; nothing runs in the background on the PC | PC: `<repo>\vm-control\` |

**Measured result:** free RAM in Windows: 1.1 GB → **15.5 GB** with the VM running, **18.8 GB** with the VM suspended.

### 23.3 Changing the VM memory (how it was done)
```powershell
$vr  = "C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"
$vmx = "C:\VMs\Sensei-Aruba\Sensei-Aruba.vmx"
Copy-Item $vmx "$vmx.bak-24g"                      # backup
& $vr -T ws stop $vmx soft                         # clean shutdown
(Get-Content $vmx -Raw) -replace 'memsize = "\d+"','memsize = "14336"' | Set-Content $vmx -NoNewline -Encoding utf8NoBOM
& $vr -T ws start $vmx nogui                       # start without a window
```
It can also be done from the VMware UI: VM → Settings → Memory. The Ollama limit inside the VM was lowered to 10 GB accordingly. To roll back, use the `.vmx.bak-24g` backup file.

### 23.4 Server-side files

**`/opt/aruba-bot/idle.sh`**
- `idle.sh status` → prints `idle` or `active`. `idle` = no model loaded in Ollama **and** rag-api is not indexing.
- `idle.sh` (no argument, from the timer) → if idle and the cache is larger than 1 GB, `sync; echo 1 > /proc/sys/vm/drop_caches` (file cache only; no data loss).

**`aruba-bot-idle.service` / `.timer`** → runs `idle.sh` every 5 minutes.
```bash
sudo cp /opt/aruba-bot/aruba-bot-idle.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aruba-bot-idle.timer
sudo journalctl -u aruba-bot-idle -n 5     # "idle: dropped N MB page cache"
```

**`/opt/aruba-bot/wake.sh`** → after the VM boots/resumes, waits until HTTPS answers, repairing if needed:
1. If HTTPS already returns 200, exit.
2. Restart the `open-webui` and `caddy` containers (connections that went stale after sleep).
3. If it still does not answer: `systemctl daemon-reload` + **restart the Docker service** + `docker compose up -d`.

> **Why step 3 exists:** in tests, after every resume (and once after a boot), Docker's internal network did not forward data: the TCP connection was made but the TLS handshake got no answer; restarting the containers was not enough, restarting the Docker service fixed it. That is why waking can take ~3 minutes.

### 23.5 PC-side files (`<repo>\vm-control\`)

| File | Task |
|---|---|
| `ai-common.ps1` | Shared settings: `vmrun.exe` path, `.vmx` path, log function, `Get-VmIp` (asks VMware for the VM's IP; no fixed IP) |
| `ai-start.ps1` | **AI Start**: starts the VM if it is off/suspended (`vmrun start ... nogui`, 2-minute timeout), finds the VM's IP, runs `wake.sh` over SSH and opens the UI in the browser when ready |
| `ai-sleep.ps1` | **AI Sleep**: suspends the VM immediately (`vmrun suspend ... soft`) |
| `install.ps1` | One-time setup: desktop shortcuts (no scheduled task) |
| `ai-vm.log` | Suspend/resume records (when it exceeds 1 MB the last 500 lines are kept) |

**Installation:**
```powershell
& <repo>\vm-control\install.ps1
```
This command:
- Puts the **"AI Başlat"** and **"AI Uyut"** shortcuts on the desktop (with the VMware icon).

**Checking / removing:**
```powershell
Get-Content <repo>\vm-control\ai-vm.log -Tail 20
```

### 23.6 Use
- **Before using the bot:** double-click **AI Başlat** on the desktop. If the VM is suspended it wakes (~6 s), and when the UI is ready (~30 s – 3 min) it opens in the browser.
- **When you are done:** the VM stays on; the model unloads itself from memory after 5 minutes and loads again automatically when a new request arrives. If you want the VM's RAM back for Windows, use **AI Uyut**.
- **While suspended** the UI cannot be opened from other computers. Automatic wake-up on a network request is not possible; waking is done only from this PC.
- **If the IP changes:** the scripts get the IP from VMware and Caddy uses no fixed IP. If you use `ssh aruba-bot` by hand, update the `HostName` value in `~/.ssh/config`.
- **Important:** when this PC is off or asleep, the VM does not run either.
