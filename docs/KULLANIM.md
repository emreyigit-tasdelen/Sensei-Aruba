# Sensei-Aruba — Kurulum ve Kullanım Kılavuzu

Bu doküman, Aruba VMC ve Aruba CX 6200M CLI komut dizinleri üzerinde çalışan, tamamen lokal (API/token kullanmayan) chatbot sisteminin **sıfırdan kurulumunu**, **mimarisini**, **her ayarın nedenini**, **günlük kullanımını** ve **bakımını** anlatır. Hiç bilmeyen biri baştan sona uygulayarak aynı sistemi kurabilir.

> Sunucu parolası bu dokümanda **bilerek yer almaz**. Parolalar düz metin dosyalarda veya dokümanlarda tutulmamalıdır.

---

## İçindekiler

1. [Genel bakış](#1-genel-bakış)
2. [Mimari](#2-mimari)
3. [Donanım ve sanal makine](#3-donanım-ve-sanal-makine)
4. [Ubuntu Server kurulumu](#4-ubuntu-server-kurulumu)
5. [Windows PC tarafı: SSH erişimi](#5-windows-pc-tarafı-ssh-erişimi)
6. [Sunucu hazırlığı: disk, Docker, sudo](#6-sunucu-hazırlığı-disk-docker-sudo)
7. [Uygulama dosyaları](#7-uygulama-dosyaları)
8. [Servisleri başlatma ve modelleri indirme](#8-servisleri-başlatma-ve-modelleri-indirme)
9. [HTTPS (Caddy)](#9-https-caddy)
10. [Firewall](#10-firewall)
11. [rag-api: CLI dizini, arama ve hakem](#11-rag-api-cli-dizini-arama-ve-hakem)
12. [Otomatik yeniden indeksleme](#12-otomatik-yeniden-indeksleme)
13. [İlk giriş ve Open WebUI ayarları](#13-ilk-giriş-ve-open-webui-ayarları)
14. [Günlük kullanım](#14-günlük-kullanım)
15. [Yeni cihaz / yeni marka ekleme](#15-yeni-cihaz--yeni-marka-ekleme)
16. [PDF ve görsel dökümanlar](#16-pdf-ve-görsel-dökümanlar)
17. [CPU, RAM ve performans ayarları](#17-cpu-ram-ve-performans-ayarları)
18. [Bakım komutları](#18-bakım-komutları)
19. [Sorun giderme (kurulumda yaşanan gerçek sorunlar)](#19-sorun-giderme-kurulumda-yaşanan-gerçek-sorunlar)
20. [Kurulumda yapılan değişikliklerin özeti](#20-kurulumda-yapılan-değişikliklerin-özeti)
21. [Güvenlik sertleştirme](#21-güvenlik-sertleştirme)
22. [Sınırlar ve sonraki adımlar](#22-sınırlar-ve-sonraki-adımlar)
23. [Bellek ve uyku yönetimi](#23-bellek-ve-uyku-yönetimi)

---

## 1. Genel bakış

**Amaç:** Ağ cihazlarının CLI komutlarını soran kullanıcıya, yalnızca gerçek komut dizinine dayanarak (uydurmadan) Türkçe cevap veren, fotoğraf okuyabilen, gerektiğinde internette arama yapabilen, yeni döküman/dizin eklendikçe kendini güncelleyen bir asistan.

**Temel kararlar ve nedenleri:**

| Karar | Neden |
|---|---|
| Model **eğitilmedi (fine-tuning yok)**, bunun yerine **RAG** kullanıldı | Yeni döküman geldikçe yeniden eğitim gerekmez; komutlar dizinden birebir gelir, uydurma riski düşer. |
| Claude değil, **açık modeller** (Qwen) | Claude yalnızca Anthropic API/abonelik üzerinden çalışır; lokal ve token'sız çalışma şartı için açık ağırlıklı modeller gerekir. |
| **Docker Compose** | Her bileşen izole; tek komutla aç/kapa; başka sunucuya klasör kopyalayarak taşınır; ileride farklı marka eklemek kolay. |
| **Ubuntu Server 26.04 LTS** (GUI'siz) | Docker/Ollama/Open WebUI dokümantasyonunun çoğu Ubuntu'ya göre; GUI RAM ve CPU yer, gereksiz. |
| **Cihaz başına ayrı model** | VMC ve 6200M komutları asla karışmaz; her model yalnızca kendi dizininde arar. |
| **Hakem katmanı** | Cevaptaki her komut dizinde doğrulanır, küçük bir LLM cevabın bağlamla desteklenip desteklenmediğini onaylar. |

**Fine-tuning hakkında not:** Bu projede hiçbir modele ince ayar (fine-tuning / LoRA) **yapılmadı**. "Ayar" olarak yapılan her şey konfigürasyondur: model seçimi, CPU/RAM sınırları, bağlam uzunluğu, arama parametreleri, sistem talimatı (prompt), eşanlamlı sözlüğü. Bunların hepsi aşağıda tek tek anlatılmıştır.

---

## 2. Mimari

```
 Tarayıcı (https://<VM-IP>)
        │  443 (HTTP 80 → otomatik HTTPS yönlendirme)
        ▼
 ┌─────────────┐
 │   caddy     │  TLS sonlandırma (kendi imzalı sertifika)
 └──────┬──────┘
        ▼
 ┌─────────────┐   OpenAI uyumlu API    ┌──────────────┐
 │ open-webui  │ ─────────────────────► │   rag-api    │  CLI dizini: SQLite FTS5 + vektör
 │ (arayüz)    │   modeller:            │  (FastAPI)   │  hakem: komut doğrulama + qwen3:1.7b
 │             │   aruba-vmc            └──────┬───────┘
 │             │   aruba-cx-6200m              │
 │             │                               ▼
 │             │ ───────────────────────► ┌──────────┐
 │             │   (ham modeller, embed)  │  ollama  │  qwen3:8b, qwen2.5vl:7b,
 └──────┬──────┘                          └──────────┘  qwen3:1.7b, bge-m3
        │ PDF/Word ayrıştırma
        ▼
 ┌─────────────┐
 │   docling   │
 └─────────────┘

 Sunucu klasörü: /opt/aruba-bot
   compose.yaml, Caddyfile, rag-api/, sources/<cihaz>/commands.jsonl
```

| Servis | İmaj | Görev | Dışarı açık port |
|---|---|---|---|
| `ollama` | `ollama/ollama:latest` | Modelleri CPU'da çalıştırır | Yok |
| `docling` | `quay.io/docling-project/docling-serve-cpu:latest` | PDF/Word'den metin, tablo, görsel çıkarır | Yok |
| `rag-api` | Lokal build (`./rag-api`) | CLI dizini, arama, cevap üretimi, hakem | Yok |
| `open-webui` | `ghcr.io/open-webui/open-webui:main` (lokal build: ad eki kaldırılmış, bkz. 7.1) | Chat arayüzü, kullanıcılar, görsel yükleme, web arama, döküman RAG | Yok |
| `caddy` | `caddy:2` | HTTPS reverse proxy | 80, 443 |

Servisler birbirine Docker'ın iç ağı üzerinden servis adıyla erişir (`http://ollama:11434`, `http://rag-api:8000` vb.). Dışarıya yalnızca Caddy açıktır.

---

## 3. Donanım ve sanal makine

### Mevcut kurulum
| Kaynak | Değer |
|---|---|
| Fiziksel makine | Dizüstü, Intel i7-1255U (10 çekirdek / 12 thread), 40 GB RAM, NVIDIA MX550 2 GB (LLM için kullanılamaz) |
| VM | VMware Workstation, Ubuntu Server 26.04.1 LTS, 12 vCPU, **14 GB RAM** (ilk kurulumda 24 GB'tı, bkz. Bölüm 23), disk 150 GB (LVM), GPU yok |
| VM IP | `<VM-IP>`, kullanıcı `<kullanici>` |

**Ölçülen performans (qwen3:8b, CPU):** prompt işleme ~22 token/sn, cevap üretme **~3 token/sn**, model yükleme ~25 sn. Bir cevap 1–3 dakika sürebilir.

### Önerilen boyutlar (yeni kurulum yapacaksanız)
| Senaryo | vCPU | RAM | Disk | Model |
|---|---|---|---|---|
| GPU yok (minimum) | 16 | 64 GB | 150 GB | qwen3:8b (yavaş) |
| GPU 16 GB VRAM (önerilen) | 8 | 32 GB | 150–200 GB | qwen3:14b, qwen2.5vl:7b |
| GPU 24 GB+ | 8–12 | 48 GB | 200–300 GB | daha büyük modeller |

**Disk:** 100 GB yeterli ama sıkışık; 150 GB rahat. Disk %80'i geçmemeli (Docker ve veritabanları dolu diskte bozulabilir). Mevcut kullanım: işletim sistemi + Docker imajları ~20 GB, modeller ~14 GB, indeksler ~1–2 GB.

---

## 4. Ubuntu Server kurulumu

1. Ubuntu Server 26.04 LTS ISO'sunu indirin (Desktop değil, **Server**).
2. Hypervisor'da VM oluşturun (yukarıdaki boyutlar). Ağ kartı köprü (bridged) veya şirket ağına bağlı olmalı.
3. Kurulum sihirbazında:
   - Kurulum tipi: **Ubuntu Server** (minimized değil).
   - Disk: **"Use an entire disk" + "Set up this disk as an LVM group"** seçili kalsın. LVM, diski sonradan büyütmeyi yeniden kurulumsuz yapmayı sağlar.
   - Kullanıcı: `<kullanici>` (veya istediğiniz ad; bu dokümanda `<kullanici>` olarak yazılır).
   - **Install OpenSSH server: işaretleyin.**
   - Önerilen snap paketlerinin (docker dahil) **hiçbirini seçmeyin**. Docker'ı apt ile kuracağız.
4. Kurulum bitince sunucunun IP'sini öğrenin: konsolda `ip -4 addr`.
5. Mümkünse IP'yi sabitleyin (DHCP rezervasyonu veya netplan).

> Ubuntu kurulumu varsayılan olarak LVM'de diskin yalnızca bir kısmını kullanır (burada 150 GB'ın 73 GB'ı). Bölüm 6'da kalan alan eklenir.

---

## 5. Windows PC tarafı: SSH erişimi

Sunucuya parolasız, anahtarla bağlanmak için PC'de yapılanlar. Tüm komutlar **PowerShell 7**'de çalıştırılır.

### 5.1 Ayrı bir SSH anahtarı oluşturma
Bu sunucu için ayrı bir anahtar kullanın ve **passphrase ile koruyun**:

```powershell
ssh-keygen -t ed25519 -C aruba-bot -f "$HOME\.ssh\id_ed25519_aruba_bot"
```

Passphrase'i her bağlantıda yazmamak için `ssh-agent` kullanın: `Start-Service ssh-agent; ssh-add "$HOME\.ssh\id_ed25519_aruba_bot"`.

### 5.2 SSH kısayolu (`aruba-bot`)
`C:\Users\<kullanıcı>\.ssh\config` dosyasının sonuna eklenir:

```
Host aruba-bot
    HostName <VM-IP>
    User <kullanici>
    IdentityFile ~/.ssh/id_ed25519_aruba_bot
    IdentitiesOnly yes
```

Bundan sonra `ssh aruba-bot` ve `scp dosya aruba-bot:/hedef/` komutları çalışır. `IdentitiesOnly yes`, SSH'ın başka anahtarları denemesini engeller.

### 5.3 Anahtarı sunucuya ekleme (bir kerelik, parolayla)
Anahtarın sunucudaki `~/.ssh/authorized_keys` dosyasına eklenmesi gerekir. Bu adım sunucu parolasını ister:

```powershell
$k = Get-Content "$HOME\.ssh\id_ed25519_aruba_bot.pub"
ssh <kullanici>@<VM-IP> "echo '$k' >> ~/.ssh/authorized_keys && echo KEY_OK"
```

Parolayı girin; `KEY_OK` görmelisiniz.

> **Neden `type dosya.pub | ssh ...` kullanılmadı:** PowerShell boru hattı metni farklı kodlamayla ve Windows satır sonuyla (CRLF) aktarabilir; ayrıca anahtar açıklamasındaki Türkçe karakterler (ğ, ş) sorun çıkarabilir. Değişkene okuyup tek satır olarak yazmak güvenlidir.

### 5.4 Test
```powershell
ssh -o BatchMode=yes aruba-bot "echo LOGIN_OK"
```
`BatchMode=yes` parola sormayı yasaklar; anahtar çalışmıyorsa hemen hata verir.

---

## 6. Sunucu hazırlığı: disk, Docker, sudo

### 6.1 Sudo
Kurulum ve bakım komutları `sudo` ile çalışır. Parolasız sudo (`NOPASSWD`) tanımlamayın, `sudo` parola sorsun.

### 6.2 Diski büyütme (LVM)
```bash
sudo vgs                                              # VFree sütunu boş alanı gösterir
sudo lvextend -r -l +100%FREE /dev/ubuntu-vg/ubuntu-lv
df -h /                                               # 73G → 146G oldu
```
`-r` dosya sistemini de aynı anda büyütür. Hypervisor'dan diski büyütürseniz önce `sudo growpart /dev/sda 3` ve `sudo pvresize /dev/sda3` gerekir (disk/bölüm adları `lsblk` ile kontrol edilir).

### 6.3 Docker kurulumu
Ubuntu'nun kendi deposundan:
```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker <kullanici>        # sudo'suz docker için (yeniden giriş gerekir)
sudo systemctl enable --now docker
docker --version                    # 29.1.3
docker compose version              # 2.40.3
```

### 6.4 Uygulama klasörü
```bash
sudo mkdir -p /opt/aruba-bot
sudo chown <kullanici>:<kullanici> /opt/aruba-bot
mkdir -p /opt/aruba-bot/rag-api /opt/aruba-bot/sources
```

> **Dikkat (yaşanan hata):** `sources` klasörü yoksa ve `docker compose up` çalıştırılırsa Docker onu **root sahipliğinde** oluşturur; sonra `<kullanici>` kullanıcısı içine dosya kopyalayamaz (`Permission denied`). Çözüm: `sudo chown -R <kullanici>:<kullanici> /opt/aruba-bot/sources`.

---

## 7. Uygulama dosyaları

PC'de `<repo>\server\` altında tutulur, sunucuda `/opt/aruba-bot/` altına kopyalanır.

```
/opt/aruba-bot/
├── compose.yaml               # tüm servisler
├── Caddyfile                  # HTTPS ayarı
├── aruba-bot.service          # systemd: aç/kapa
├── aruba-bot-ingest.service   # systemd: yeniden indeksleme tetikleyici
├── aruba-bot-ingest.timer     # systemd: 15 dakikada bir tetikle
├── bench.sh                   # model hız testi
├── status.sh                  # indeks durumu
├── rag-api/
│   ├── Dockerfile
│   └── app.py
├── idle.sh, wake.sh, ask.sh   # uyku/uyanma (Bölüm 23), komut satırından soru sorma
└── sources/
    ├── aruba-vmc/commands.jsonl        # 73.039 satır
    ├── aruba-vmc/docs/                 # VMC PDF/Word/görsel dökümanları (Bölüm 16)
    ├── aruba-cx-6200m/commands.jsonl   # 160.201 satır
    └── aruba-cx-6200m/docs/
```

Kopyalama (PC'den):
```powershell
scp <repo>\server\compose.yaml <repo>\server\Caddyfile <repo>\server\aruba-bot.service aruba-bot:/opt/aruba-bot/
scp <repo>\server\rag-api\app.py <repo>\server\rag-api\Dockerfile aruba-bot:/opt/aruba-bot/rag-api/
```

> **Windows satır sonu uyarısı:** Windows'ta yazılan `.sh` dosyaları ve `Caddyfile` CRLF satır sonu içerebilir; Linux'ta hata verir. Kopyaladıktan sonra: `sed -i 's/\r$//' /opt/aruba-bot/status.sh` (her shell/Caddy dosyası için).

### 7.1 compose.yaml — tam içerik ve açıklamalar

```yaml
x-logging: &logging
  driver: json-file
  options: { max-size: "10m", max-file: "3" }
```
Her konteynerin logu en fazla 3 × 10 MB tutulur; disk dolmasını önler. `&logging` YAML anchor'ı, her serviste `logging: *logging` ile tekrar kullanılır.

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
| Ayar | Değer | Neden |
|---|---|---|
| `OLLAMA_MAX_LOADED_MODELS` | 3 | Chat (veya vision) + hakem + embedding aynı anda bellekte kalabilsin; her soruda yeniden yükleme (~25 sn) olmasın. |
| `OLLAMA_NUM_PARALLEL` | 1 | CPU'da aynı anda tek istek; paralel istekler hepsini yavaşlatır ve RAM'i katlar. |
| `OLLAMA_KEEP_ALIVE` | 5m | Model 5 dk kullanılmazsa bellekten atılır (boşta RAM bırakmak için; ilk soru ~25 sn model yükleme bekler). |
| `OLLAMA_CONTEXT_LENGTH` | 8192 | Bağlam penceresi; RAG bağlamı + geçmiş için yeterli, daha büyüğü RAM ve süre artırır. |
| `cpus` | 10 | **CPU sınırı.** 12 vCPU'nun 10'unu kullanabilir; model çalışırken SSH ve arayüz kilitlenmesin diye 2 vCPU boş bırakılır. |
| `mem_limit` | 10g | 14 GB VM RAM'inin 10 GB'ı; qwen3:8b (~5,2 GB) + qwen3:1.7b (~1,4 GB) + bağlam sığar, kalan diğer servislere. |
| `restart: unless-stopped` | — | Çökerse veya sunucu açılırsa otomatik başlar (elle durdurulmadıkça). |

```yaml
  docling:
    image: quay.io/docling-project/docling-serve-cpu:latest
    environment:
      DOCLING_SERVE_ENABLE_UI: "false"
    cpus: "4"
```
PDF/Word ayrıştırıcı. CPU sürümü (GPU'suz). Kendi web arayüzü kapalı; sadece Open WebUI kullanır. **CPU sınırı 4**: büyük PDF işlerken modelin tüm CPU'yu kaybetmemesi için.

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
CLI dizini servisi (Bölüm 11). **CPU sınırı 4**: vektör indekslemesi sırasında makineyi kilitlemesin. `sources` salt okunur (`:ro`) bağlanır; indeksler `ragdata` volume'ünde tutulur.

> **CPU sınırları hakkında:** 10 + 4 + 4 = 18, 12'den fazla. Bu normal: `cpus` bir **üst sınırdır, rezervasyon değildir**. Servisler aynı anda nadiren tam yük çalışır; her biri tek başına makineyi kilitleyemez.

```yaml
  open-webui:
    build: ./open-webui   # standart imaj, yalnız " (Open WebUI)" ad eki kaldırılmış
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
| Ayar | Açıklama |
|---|---|
| `ENABLE_PERSISTENT_CONFIG: false` | Open WebUI normalde ayarları ilk açılışta veritabanına yazar ve sonra env değişikliklerini **yok sayar**. `false` ile ayarlar her başlangıçta bu dosyadan okunur. Yan etkisi: Admin panelinden yapılan bu ayarlarla çakışan değişiklikler yeniden başlatmada sıfırlanır; kalıcı değişikliği bu dosyada yapın. |
| `DEFAULT_MODELS` | Yeni sohbette seçili gelen model. |
| `build: ./open-webui` | Open WebUI, `WEBUI_NAME`'in sonuna kodda zorla " (Open WebUI)" ekler. `server/open-webui/Dockerfile` standart imajı alıp bu satırı `sed` ile kaldırır; böylece arayüzde yalnız "Sensei-Aruba" görünür. **Lisans:** Open WebUI lisansı bunu yalnız 30 günde en fazla 50 kullanıcılı kurulumlarda (veya kurumsal lisansla) izin verir. Kullanıcı sayısı 50'yi geçerse `build:` satırını `image: ghcr.io/open-webui/open-webui:main` ile değiştirin. Güncelleme: `sudo docker compose build --pull open-webui && sudo docker compose up -d open-webui`. Dockerfile'daki kontrol, Open WebUI kodu değişip satır bulunamazsa build'i durdurur. |
| `OPENAI_API_BASE_URL` | rag-api'yi "OpenAI uyumlu" bağlantı olarak ekler; cihaz modelleri buradan gelir. |
| `OPENAI_API_KEY: internal` | rag-api anahtar kontrol etmez; Open WebUI boş bırakılmasına izin vermediği için yer tutucu değerdir, gizli değildir. |
| `ENABLE_*_GENERATION: false` | Open WebUI her mesajdan sonra başlık, etiket, otomatik tamamlama ve takip sorusu için **ek LLM çağrıları** yapar. CPU'da her biri dakikalar sürer; kapatıldı. |
| `RAG_*`, `CHUNK_*` | Open WebUI'ın kendi döküman RAG'ı (PDF yüklemeleri) için: bge-m3 embedding, hibrit arama, en iyi 8 parça, 1200 karakterlik parçalar ve 200 karakter örtüşme. |
| `CONTENT_EXTRACTION_ENGINE: docling` | Yüklenen PDF/Word dosyaları Docling ile ayrıştırılır (tablolar ve görseller dahil). |
| `ENABLE_WEB_SEARCH`, `WEB_SEARCH_ENGINE` | Sohbette "Web Search" açıldığında DuckDuckGo ile internet araması. Açılmadıkça dışarı istek gitmez. |

```yaml
  caddy:
    image: caddy:2
    ports: [ "80:80", "443:443" ]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy:/data
```
Dışarıya açık tek servis. `caddy` volume'ü sertifikaları saklar.

```yaml
volumes:
  caddy:     # sertifikalar
  ragdata:   # CLI indeksleri (index.db, vec_*.npy, embedding modeli)
  ollama:    # indirilen modeller
  webui:     # kullanıcılar, sohbetler, yüklenen dökümanlar
```

### 7.2 aruba-bot.service — aç/kapa servisi
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
Kurulum:
```bash
sudo cp /opt/aruba-bot/aruba-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aruba-bot
```
`enable` sunucu açılışında otomatik başlatır. `docker compose down` konteynerleri siler ama **volume'ler (modeller, indeksler, kullanıcılar) korunur**.

---

## 8. Servisleri başlatma ve modelleri indirme

```bash
cd /opt/aruba-bot
sudo docker compose pull                  # imajları indir
sudo docker compose up -d --build         # rag-api'yi build et, hepsini başlat
sudo docker compose ps                    # hepsi "running" olmalı
```

Modeller (Ollama konteyneri içinde):
```bash
sudo docker compose exec ollama ollama pull bge-m3          # 1.2 GB  embedding (döküman RAG)
sudo docker compose exec ollama ollama pull qwen3:8b        # 5.2 GB  ana sohbet modeli
sudo docker compose exec ollama ollama pull qwen2.5vl:7b    # 6.0 GB  görsel okuma
sudo docker compose exec ollama ollama pull qwen3:1.7b      # 1.4 GB  hakem
sudo docker compose exec ollama ollama list
```

| Model | Görev | Neden bu model |
|---|---|---|
| `qwen3:8b` | Cevap üretimi | Türkçe iyi, talimata uyumu güçlü; CPU'da çalışabilecek en büyük makul boyut. |
| `qwen2.5vl:7b` | Fotoğraf/ekran görüntüsü okuma | CLI çıktısı, topoloji ekranı gibi görsellerde OCR + yorum. |
| `qwen3:1.7b` | Hakem | Kısa ONAY/RED kararı için yeterli, hızlı. |
| `bge-m3` | Open WebUI döküman embedding'i | Çok dilli (Türkçe + İngilizce). |

**Hız testi** (`bench.sh`):
```sh
#!/bin/sh
cd /opt/aruba-bot
sudo docker compose exec -T ollama ollama run qwen3:8b --verbose "Merhaba, tek cümleyle kendini tanıt. /no_think" 2>&1 | grep -E "load duration|eval rate"
```
`eval rate` cevap üretim hızıdır (token/sn). `/no_think` qwen3'ün "düşünme" modunu kapatır.

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
Caddy, diğer servislerle aynı Compose ağındadır ve Open WebUI'a servis adıyla (`open-webui:8080`) proxy yapar; dışarıya yalnız Caddy'nin 80/443 portları yayınlanır. `127.0.0.1:8080` **kullanmayın**: Caddy kendi konteynerinde çalıştığı için bu adres Caddy'nin kendisidir ve 502 verir (bkz. [Sorunlar ve Çözümler](sorunlar-ve-cozumler.md)).
- `tls internal`: Alan adı ve internetten doğrulama olmadığı için Caddy **kendi yerel sertifika otoritesiyle** sertifika üretir. Trafik şifrelidir; tarayıcı ilk girişte "güvenli değil" uyarısı verir → "Gelişmiş → Devam et".
- HTTP (80) istekleri otomatik olarak HTTPS'e yönlendirilir (308).
- `on_demand`: Sertifika, istemcinin bağlandığı ad veya IP için ilk istekte üretilir; Caddyfile'da sabit IP yoktur.
- `curl -k https://localhost/` ve `curl -k https://127.0.0.1/` çalışır.

**Uyarıyı tamamen kaldırmak (opsiyonel):** Caddy'nin kök sertifikasını PC'lere güvenilir olarak ekleyin:
```bash
sudo docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
```
Dosyayı PC'ye alıp Windows'ta "Güvenilen Kök Sertifika Yetkilileri"ne yükleyin. Şirket alan adı ve kurumsal sertifika varsa `tls internal` yerine o sertifika dosyaları kullanılabilir.

---

## 10. Firewall

```bash
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP → HTTPS yönlendirme
sudo ufw allow 443/tcp     # HTTPS
sudo ufw --force enable
sudo ufw status
```
Ollama (11434), rag-api (8000), Docling (5001) ve Open WebUI (8080) **dışarı hiç yayınlanmaz**; yalnızca Docker iç ağında erişilebilir.

> Not: Docker, `ports:` ile yayınlanan portlar için ufw kurallarını atlar. Bu yüzden compose'da yalnızca Caddy'nin portları yayınlanır; diğer servislere `ports:` eklemeyin.

---

## 11. rag-api: CLI dizini, arama ve hakem

Kaynak: `server/rag-api/app.py`. Python 3.12, FastAPI, fastembed, NumPy, SQLite.

### 11.1 Neden ayrı bir servis?
VMC (73 bin) + 6200M (160 bin) = **233 bin komut satırı**. Bunları Open WebUI'a dosya olarak yüklemek yavaş ve isabetsiz olurdu. Ayrıca CLI komutlarında **birebir kelime eşleşmesi** kritik; genel amaçlı döküman RAG'ı bunun için uygun değil. rag-api, markadan bağımsız, cihaz başına ayrı dizin tutar.

### 11.2 Kaynak dosya formatı (`commands.jsonl`)
Her satır bir JSON nesnesi:
```json
{"device": "aruba-cx-6200m", "mode": "config", "command": "aaa authentication port-access dot1x authenticator", "description": "Configure 802.1X authenticator"}
```
| Alan | Zorunlu | Açıklama |
|---|---|---|
| `command` | Evet | Tam komut, argüman yer tutucuları dahil (`<IFNAME>`, `WORD`, `A.B.C.D`). |
| `description` | Hayır | Komut açıklaması (aramada kullanılır). |
| `mode` | Hayır | `config`, `enable`, `exec` vb. |
| `device` | Hayır | Bilgi amaçlı; asıl cihaz adı **klasör adından** gelir. |

Bu dosyalar `aruba_crawl.py` ile canlı cihazdan CLI ağacı (`?` yardımı) taranarak üretildi. Aynı taramadan `.md` ağaç dosyaları da üretilir; rag-api `.md`'yi değil **`commands.jsonl`**'ı kullanır (aynı içerik, satır bazlı ve indekslemeye uygun).

### 11.3 İndeksleme (iki aşamalı)
Başlangıçta ve her `/ingest` çağrısında:

1. `/sources` altındaki her klasör için `commands.jsonl`'ın SHA-256 özeti hesaplanır. Özet değişmediyse cihaz atlanır (yalnızca belleğe yüklenir).
2. **Aşama 1 — anahtar kelime indeksi (tüm cihazlar, dakikalar içinde):**
   - `<cr>`, `|`, `>`, `>>` ile biten satırlar elenir (bunlar "Enter" ve çıktı yönlendirme tekrarlarıdır).
   - Tekrar eden komutlar elenir.
   - SQLite tablosu `cmds` + **FTS5** tam metin indeksi (BM25 sıralaması) oluşturulur.
   - Cihaz hemen kullanılabilir olur: durum `keyword-only (vectors queued)`.
3. **Aşama 2 — vektör indeksi (cihaz cihaz, uzun sürer):**
   - Embedding modeli: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (fastembed/ONNX, çok dilli, 384 boyut, CPU'da hızlı). Türkçe soruyla İngilizce açıklamayı eşleştirebilir.
   - Metin: `"<komut> — <açıklama>"`, 256'lık gruplar halinde.
   - Normalize edilmiş vektörler `/data/vec_<cihaz>.npy` olarak kaydedilir.
   - Bitince durum: kayıt sayısı (ör. `"aruba-vmc": 61234`), genel durum `ready`.

Neden iki aşama: Tek aşamada her cihaz vektörleri bitene kadar bekliyordu; ilk cihaz (6200M) bitmeden VMC hiç görünmüyordu.

> **Önemli:** rag-api konteyneri yeniden başlatılırsa **yarım kalan vektör indekslemesi baştan başlar** (tamamlanan cihazlar korunur). Kod değişikliklerini indeksleme bitince uygulayın.

### 11.4 Arama (hibrit + sorgu genişletme)
1. **Sorgu genişletme (`SYNONYMS`):** Kullanıcı ifadeleri CLI terimlerine çevrilir:

   | Kullanıcı yazar | Aramaya eklenir |
   |---|---|
   | `802.1x`, `8021x` | `dot1x port-access authenticator` |
   | `mab`, `mac auth` | `mac-auth port-access` |
   | `radius` | `radius-server radius aaa` |
   | `vlan` | `vlan access trunk` |
   | `ge 1 1 1`, `port 1/1/1`, `int 1 1 1` | `interface 1/1/1` |
   | `trunk` | `vlan trunk allowed native` |
   | `lacp`, `port-channel` | `lag lacp` |

2. **Durak kelimeler (`STOP`)** aramadan çıkarılır: bana, için, yaz, nasıl, ver, config, komut vb. Tek başına sayılar da çıkarılır.
3. **BM25 (FTS5):** Kelimeler `OR` ile aranır, en iyi 50 sonuç.
4. **Vektör:** Sorgu vektörü ile cihazın tüm vektörlerinin kosinüs benzerliği, en iyi 50.
5. **Birleştirme — Reciprocal Rank Fusion:** Her sonuç için `1 / (60 + sıra)` puanları toplanır; en iyi **15** (`TOP_K`) komut bağlam olarak modele verilir.
6. **Cihaz izolasyonu:** Arama yalnızca seçili modelin (cihazın) kayıtlarında yapılır.

### 11.5 Cevap üretimi
Modele giden mesaj:
- **Sistem talimatı:** Yalnızca BAĞLAM'daki komutlara dayan, uydurma; komutları ters tırnakla ve aynen ver; `<...>` alanlarını açıkla; modu belirt; konfigürasyon istenirse komutları sırayla (önce global, sonra `interface ...` altında) kod bloğunda birleştir; bağlamda yoksa "Bu komut dizinde bulunamadı" de; Türkçe cevap ver.
- Son 6 sohbet mesajı (geçmiş).
- `BAĞLAM: [cihaz | mod] komut — açıklama` satırları + `SORU`.
- `think: false` → qwen3'ün düşünme çıktısı kapalı (CPU'da süreyi ikiye katlıyordu).

**Fotoğraf varsa:** Mesajda görsel bulunursa istek otomatik olarak `qwen2.5vl:7b` modeline gider (görsel base64 olarak iletilir).

### 11.6 Hakem (iki katman)
Cevabın sonuna eklenir:

1. **Deterministik doğrulama (her zaman):** Cevaptaki `ters tırnaklı` komutlar ve ```kod bloğu``` satırları çıkarılır. Her biri cihazın komut ağacında aranır: aynı ilk kelime + aynı kelime sayısı + her kelime ya birebir aynı ya da ağaçtaki karşılığı yer tutucu (`<...>`, BÜYÜK HARF, `A.B.C.D`, `[...]`). Sonuç: `✅ N komut dizinde var · ⚠️ dizinde yok: ...`
2. **Hakem LLM (`qwen3:1.7b`):** Bağlam ve cevabı okuyup tek satır verir: `ONAY: ...` veya `RED: ...`. Bağlam boşsa çalışmaz. Kapatmak için compose'da `JUDGE_MODEL: ""`.

> ⚠️ işareti her zaman hata demek değildir: crawler'ın taramadığı alt modlardaki (ör. bazı `interface` altı) komutlar dizinde olmayabilir. ⚠️ olan komutu cihazda `?` ile kontrol edin.

### 11.7 API uç noktaları
| Uç nokta | Açıklama |
|---|---|
| `GET /v1/models` | Cihaz listesi = model listesi (Open WebUI bunu okur). |
| `POST /v1/chat/completions` | OpenAI uyumlu sohbet; akış (stream) destekli. |
| `GET /health` | `{"status": "...", "devices": {...}}` indeks durumu. |
| `POST /ingest` | Yeniden indeksleme başlatır; zaten indeksleme varsa başlatmaz. |

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
Embedding modeli ilk çalıştırmada indirilir ve `/data/models` altına önbelleklenir.

### 11.9 Ayarlanabilir ortam değişkenleri
| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `CHAT_MODEL` | `qwen3:8b` | Cevap modeli |
| `VISION_MODEL` | `qwen2.5vl:7b` | Görsel modeli |
| `JUDGE_MODEL` | `""` (compose'da `qwen3:1.7b`) | Boşsa hakem LLM kapalı |
| `EMB_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Vektör modeli (değiştirirseniz tüm indeksi silip yeniden oluşturun) |
| `TOP_K` | 15 | Modele verilen komut sayısı |
| `DOC_TOP_K` | 4 | Modele verilen döküman parçası sayısı |
| `DOCLING_URL` | `http://docling:5001` | Döküman dönüştürücü |
| `OLLAMA_URL` | `http://ollama:11434` | |

---

## 12. Otomatik yeniden indeksleme

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

Kurulum:
```bash
sudo cp /opt/aruba-bot/aruba-bot-ingest.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aruba-bot-ingest.timer
systemctl list-timers | grep aruba     # sonraki çalışma zamanı
```
rag-api yalnızca **değişen** dosyaları yeniden indeksler (SHA-256 karşılaştırması), bu yüzden 15 dakikada bir çalışması ucuzdur. İndeksleme sürerken gelen tetikleme yok sayılır.

> **Kurulum durumu:** Zamanlayıcı aktif (15 dakikada bir). İlk tam indeks: aruba-cx-6200m 102.032, aruba-vmc 57.741 komut (filtreleme sonrası). 6200M vektörleri ~1,5 saat, VMC ~1 saat sürdü.

---

## 13. İlk giriş ve Open WebUI ayarları

1. Tarayıcıda `https://<VM-IP>` → sertifika uyarısını geçin.
2. **İlk kayıt olan kullanıcı admin olur.** Hemen kendi hesabınızı oluşturun.
3. Önerilen admin ayarları:
   - **Admin → Settings → Models:** `qwen3:8b`, `qwen2.5vl:7b`, `qwen3:1.7b`, `bge-m3` ham modellerini normal kullanıcılardan gizleyin. Kullanıcılar yalnızca `aruba-vmc` ve `aruba-cx-6200m` görsün.
   - **Admin → Settings → General:** Yeni kayıtları "pending" yapın (yetkisiz kişi hesap açıp kullanamasın).
   - **Admin → Users:** Ekip üyelerini ekleyin.

---

## 14. Günlük kullanım

- **Cihaz seçimi:** Sohbetin üstündeki model menüsünden `aruba-vmc` veya `aruba-cx-6200m`. Her model yalnızca kendi cihazının komutlarını bilir; cihazlar asla karışmaz.
- **Soru örnekleri:**
  - `802.1x config yaz bana port ge 1 1 1 için`
  - `show komutlarıyla aaa ayarlarını nasıl görürüm?`
  - `vlan 10 oluşturup 1/1/5 portuna access olarak ata`
- **Cevabın sonu:** `Doğrulama` (komutlar dizinde var mı) ve `Hakem` (ONAY/RED) satırları. ⚠️ veya RED görürseniz cevaba temkinli yaklaşın.
- **Fotoğraf:** `+` → görsel yükleyin (CLI çıktısı, hata ekranı). Otomatik olarak görsel modeli kullanılır.
- **İnternet araması:** Sohbet kutusundaki "Web Search" düğmesiyle o mesaj için açılır.
- **Bekleme süresi:** CPU'da cevap 1–3 dakika; ilk soru modeli yüklediği için daha uzun.
- **İndeks hazırlanırken:** Cevabın başında "Vektör indeksi hazırlanıyor, şimdilik anahtar kelime araması" notu görünür; cevaplar yine çalışır.

---

## 15. Yeni cihaz / yeni marka ekleme

**Kural:** `sources/<cihaz-adı>/commands.jsonl`. **Klasör adı = WebUI'daki model adı.** Küçük harf, tire kullanın (ör. `aruba-cx-6300`, `cisco-c9300`).

### Adımlar (PC'den, PowerShell)
```powershell
ssh aruba-bot "mkdir -p /opt/aruba-bot/sources/aruba-cx-6300"
scp <repo>\crawler\aruba-cx-6300\commands.jsonl aruba-bot:/opt/aruba-bot/sources/aruba-cx-6300/
```
Sonra ya 15 dakika bekleyin (zamanlayıcı) ya da hemen tetikleyin:
```powershell
ssh aruba-bot "sudo systemctl start aruba-bot-ingest"
```
Durumu izleyin:
```powershell
ssh aruba-bot "sh /opt/aruba-bot/status.sh"
```
WebUI'da sayfayı yenileyin (F5) → yeni model listede. Anahtar kelime araması birkaç dakikada hazır olur, vektörler arkadan tamamlanır.

### Mevcut cihazı güncelleme
Aynı yola yeni `commands.jsonl` kopyalayın. Dosya değiştiği için yalnızca o cihaz yeniden indekslenir.

### Cihazı kaldırma
```bash
rm -r /opt/aruba-bot/sources/<cihaz>
sudo docker compose restart rag-api
```
(Not: Eski kayıtlar SQLite'ta kalır ama model listesinde görünmez; tam temizlik için `ragdata` volume'ündeki `index.db` silinip yeniden indekslenebilir.)

### Farklı marka
- Format aynıdır (Bölüm 11.2). Rag-api markadan bağımsızdır.
- `aruba_crawl.py` Aruba CLI'ına özeldir. Cisco/Juniper vb. için aynı formatta çıktı üreten bir tarayıcı (crawler) veya resmi komut referansından dönüştürücü gerekir.
- Marka terimleri için `app.py` içindeki `SYNONYMS` sözlüğüne eşlemeler eklenebilir (ör. Cisco için `gi1/0/1 → interface GigabitEthernet1/0/1`). Değiştirdikten sonra rag-api'yi yeniden build edin.

---

## 16. PDF ve görsel dökümanlar

### 16.1 Cihaz bazlı dökümanlar (önerilen)
Her cihazın dökümanları, o cihazın komut dizininin yanına konur ve **aynı modelde** kullanılır. `aruba-vmc` modeli bir soruda hem VMC komut dizinini hem VMC dökümanlarını arar; 6200M dökümanlarını asla görmez.

```
/opt/aruba-bot/sources/<cihaz>/docs/      ← dosyaları buraya (alt klasör serbest)
```

| Desteklenen | İşleyen |
|---|---|
| `.pdf .docx .pptx .xlsx .html .htm` | Docling (metin, tablo, başlık yapısı; **OCR açık** → taranmış PDF ve ekran görüntüsündeki yazılar okunur) |
| `.png .jpg .jpeg .tif .tiff .bmp` | Docling OCR |
| `.md .txt` | Doğrudan okunur |

**Ekleme (PC'den):**
```powershell
scp "<dosya>.pdf" aruba-bot:/opt/aruba-bot/sources/aruba-vmc/docs/
ssh aruba-bot "sudo systemctl start aruba-bot-ingest"     # hemen işle (yoksa 15 dk içinde otomatik)
ssh aruba-bot "sh /opt/aruba-bot/status.sh"               # "docs": {"aruba-vmc": {"files": 1, "chunks": N}}
```
- **Güncelleme:** aynı adla üzerine yaz → yalnızca o dosya yeniden işlenir (SHA-256).
- **Silme:** dosyayı sil → bir sonraki indekslemede parçaları da silinir.
- İşlenirken durum `converting <dosya>` / `embedding` görünür. Hata olursa `/health` çıktısında `errors` altında dosya adıyla yazar; diğer dosyalar işlenmeye devam eder.

**Nasıl çalışır:**
1. Docling asenkron API'si (`/v1/convert/file/async`) ile dosya **Markdown**'a çevrilir (görseller yer tutucu, OCR açık).
2. Markdown başlıklara göre bölünür, her bölüm ~1000 karakterlik parçalara (150 karakter örtüşme) ayrılır; her parça başlığını taşır.
3. Parçalar SQLite FTS5 (`docs_fts`) ve vektör (`/data/dvec_<cihaz>.npy`) olarak indekslenir; aynı çok dilli embedding modeli kullanılır.
4. Dönüştürme bitince Docling'in bellekteki modelleri boşaltılır (`/v1/clear/converters`) → RAM tasarrufu.
5. Soru geldiğinde komut aramasına ek olarak en iyi **4** döküman parçası (`DOC_TOP_K`) bağlama `DÖKÜMAN:` başlığıyla eklenir.
6. Model, dökümandan aldığı bilginin kaynağını **`[dosya › başlık]`** olarak yazar. Hakem LLM, döküman parçalarını da bağlam olarak görür.

> **Görseller hakkında:** OCR, görsellerdeki **yazıyı** okur (CLI ekran görüntüsü, tablo görseli). Diyagramların anlamını (topoloji çizimi gibi) yorumlamaz; bunun için sohbete görseli doğrudan yükleyin (görsel modeli `qwen2.5vl:7b` kullanılır).

> **Performans:** Büyük PDF'ler CPU'da dakikalarca sürebilir (Docling 4 CPU ile sınırlı). Bağlama eklenen döküman metni cevap süresini ~30–60 sn uzatır.

### 16.1.1 Çok büyük PDF'ler (binlerce sayfa)
Docling CPU'da binlerce sayfayı saatlerce/günlerce işler. Metin katmanı olan büyük PDF'leri PC'de `server\tools\pdf_to_md.py` ile Markdown'a çevirip `.md` olarak yükleyin:
```powershell
python -m venv venv; .\venv\Scripts\pip install pymupdf
.\venv\Scripts\python server\tools\pdf_to_md.py "ArubaOS-8.x-CLI-Reference-Guide.pdf" ArubaOS-8.x-CLI-Reference-Guide.md
scp ArubaOS-8.x-CLI-Reference-Guide.md aruba-bot:/opt/aruba-bot/sources/aruba-vmc/docs/
```
- PDF'in yer imleri (içindekiler) başlığa dönüşür → kaynak gösterimi `[dosya › komut › bölüm]` olur.
- Kelime boşlukları korunur (markitdown gibi araçlar bu PDF'te kelimeleri bitiştiriyordu: `FollowingliststheupdatestotheAOSCLI`).
- Sayfa üst/alt bilgileri atılır. OCR yapmaz; görsel ağırlıklı PDF'ler için Docling kullanın.

### 16.1.2 Yüklü dökümanlar (2026-10-31)
| Cihaz | Dosya | Yöntem |
|---|---|---|
| aruba-vmc | ArubaOS-8.x-CLI-Reference-Guide.md (4111 sayfa, 9.840 başlık) | pdf_to_md.py |
| aruba-vmc | AP-630_Install_Guide_EN.pdf | Docling |
| aruba-vmc | Aruba ISE.pdf (yalnız görsel, 9 s.) | Docling OCR |
| aruba-vmc | 1791201570899.pdf (EntraID EAP-TLS technote) | Docling |
| aruba-vmc | Wi-Fi design and deployment … .pdf | Docling |
| aruba-cx-6200m | — (6200M'e özel PDF yok; CX 6000 datasheet'i farklı seri olduğu için eklenmedi) | |


### 16.2 Open WebUI Knowledge (alternatif, genel dökümanlar)
Cihaza bağlı olmayan genel dökümanlar için Open WebUI'ın kendi RAG'ı da kullanılabilir: **Workspace → Knowledge → +** → dosya yükle → sohbette `#` ile koleksiyonu seçip ham `qwen3:8b` modeliyle sor. Bu yol cihaz modelleriyle (doğrulama/hakem) birlikte çalışmaz.

---

## 17. CPU, RAM ve performans ayarları

Bu bölüm tüm "ince ayarları" bir arada listeler. Hiçbiri model eğitimi değildir.

| Nerede | Ayar | Değer | Etkisi |
|---|---|---|---|
| compose / ollama | `cpus` | 10 | Model 12 vCPU'nun 10'unu kullanabilir; SSH ve arayüz kilitlenmez. **Eklenme nedeni:** Sınır yokken model çalışırken sunucu SSH'a dakikalarca cevap vermedi. |
| compose / ollama | `mem_limit` | 10g | RAM taşmasını önler. |
| compose / ollama | `OLLAMA_NUM_PARALLEL` | 1 | Tek istek; CPU'da en verimli. |
| compose / ollama | `OLLAMA_MAX_LOADED_MODELS` | 3 | Model yeniden yüklemelerini azaltır. |
| compose / ollama | `OLLAMA_KEEP_ALIVE` | 5m | Model bellekte kalma süresi. |
| VMware | `memsize` | 14336 (14 GB) | VM'e ayrılan RAM (Bölüm 23). |
| compose / ollama | `OLLAMA_CONTEXT_LENGTH` | 8192 | Bağlam boyutu. |
| compose / docling | `cpus` | 4 | PDF işleme sınırı. |
| compose / rag-api | `cpus` | 4 | Vektör indeksleme sınırı. |
| compose / open-webui | `ENABLE_*_GENERATION` | false | Gereksiz arka plan LLM çağrıları kapalı. |
| compose / tümü | log `max-size`/`max-file` | 10m × 3 | Disk koruması. |
| rag-api | `think: false` | — | qwen3 düşünme çıktısı kapalı; cevap süresi yaklaşık yarıya iner. |
| rag-api | `TOP_K` | 15 | Daha az bağlam = daha hızlı; daha fazla = daha kapsamlı. |
| rag-api | Filtre | `<cr>`, `\|` vb. | Gereksiz satırlar elendi; indeks küçüldü. |

### Hızlandırma seçenekleri
| Seçenek | Kazanç | Bedel |
|---|---|---|
| `CHAT_MODEL: qwen3:4b` | ~2× hızlı | Cevap kalitesi düşer |
| `JUDGE_MODEL: ""` | Her cevapta ~20–60 sn | Hakem LLM yok (deterministik doğrulama sürer) |
| `OLLAMA_CONTEXT_LENGTH: 4096` | Daha az RAM, biraz hız | Uzun sohbetlerde geçmiş kısalır |
| GPU'lu sunucu | 10–20× | Donanım |

Değişiklik sonrası: `sudo docker compose up -d` (rag-api kodu değiştiyse `--build`).

---

## 18. Bakım komutları

Hepsi sunucuda, `/opt/aruba-bot` içinde (PC'den başına `ssh aruba-bot "..."` ekleyerek de çalışır).

| İş | Komut |
|---|---|
| Sistemi durdur | `sudo systemctl stop aruba-bot` |
| Sistemi başlat | `sudo systemctl start aruba-bot` |
| Durum | `sudo docker compose ps` |
| Kaynak kullanımı | `sudo docker stats --no-stream` |
| Loglar | `sudo docker compose logs --tail 50 rag-api` (servis adı değiştirilebilir) |
| İndeks durumu | `sh status.sh` |
| Elle yeniden indeksle | `sudo systemctl start aruba-bot-ingest` |
| Model hız testi | `sh bench.sh` |
| İmajları güncelle | `sudo docker compose pull && sudo docker compose up -d` |
| rag-api kodunu güncelle | `scp` ile `app.py` kopyala → `sudo docker compose up -d --build rag-api` |
| Model ekle/sil | `sudo docker compose exec ollama ollama pull <model>` / `ollama rm <model>` |
| Disk | `df -h /` |
| Docker temizliği | `sudo docker system prune` (kullanılmayan imaj/konteyner) |
| Yedek (volume) | `sudo docker run --rm -v aruba-bot_webui:/v -v /root:/b alpine tar czf /b/webui.tgz -C /v .` |

**Yedeklenmesi gerekenler:** `/opt/aruba-bot` klasörü (kod + kaynaklar) ve `aruba-bot_webui` volume'ü (kullanıcılar, sohbetler, dökümanlar). Modeller ve indeksler yeniden üretilebilir. En kolay yol hypervisor'da VM snapshot'ı.

**Başka sunucuya taşıma:** Yeni sunucuda Bölüm 4–6 → `/opt/aruba-bot` klasörünü kopyala → Bölüm 8 (modelleri indir) → 7.2 ve 12 (systemd) → isterseniz webui volume yedeğini geri yükleyin.

---

## 19. Sorun giderme (kurulumda yaşanan gerçek sorunlar)

| Belirti | Neden | Çözüm |
|---|---|---|
| Anahtar sunucuya eklenince bozuk | PowerShell boru hattı kodlama/CRLF | Bölüm 5.3'teki değişken yöntemi |
| `ssh: connect ... Connection timed out` model çalışırken | Model tüm CPU'yu alıyor (VM, dizüstüyle CPU paylaşıyor) | Ollama `cpus: 10`; uzun komutları sunucuda `nohup ... &` ile çalıştırıp sonucu dosyadan okuyun |
| `scp: dest open ... No such file or directory / Failure` | `sources` klasörünü Docker root sahipliğinde oluşturdu | `sudo chown -R <kullanici>:<kullanici> /opt/aruba-bot/sources` |
| Cevap: "İndeks hazırlanıyor ... Bu komut dizinde bulunamadı" + Hakem RED | İndeks hazır olmadan boş bağlamla cevap üretildi | İki aşamalı indeksleme; bağlam boşken hakem çalışmaz |
| VMC modeli listede yok | İndeksleme sıralıydı, VMC 6200M'i bekliyordu | İki aşamalı indeksleme (Bölüm 11.3) |
| "802.1x" sorusu bulunamıyor | Kullanıcı terimi ≠ CLI terimi (`dot1x`) | `SYNONYMS` sözlüğü |
| Compose'daki Open WebUI ayarı uygulanmıyor | Persistent config ilk açılışta DB'ye yazıldı | `ENABLE_PERSISTENT_CONFIG: "false"` |
| `curl https://localhost` hata 35 | Sertifika IP için üretildi | `curl -k https://<VM-IP>/` |
| `.sh` dosyası "not found" / garip hata | Windows CRLF satır sonu | `sed -i 's/\r$//' dosya` |
| İlk model testi 29 dakika | SSH bağlantısı kopup istek modele ulaşmamıştı + CPU yavaş | `bench.sh` ile tekrar ölçüldü: ~3 token/sn |

**Genel teşhis:**
```bash
sudo docker compose ps
sudo docker compose logs --tail 50 <servis>
sh status.sh
uptime; free -h; df -h /
```

---

## 20. Kurulumda yapılan değişikliklerin özeti

### Windows PC
| Değişiklik | Yer |
|---|---|
| SSH anahtarı (yalnız bu sunucu için) | `%USERPROFILE%\.ssh\id_ed25519_aruba_bot` (+ `.pub`) |
| SSH kısayolu `aruba-bot` | `%USERPROFILE%\.ssh\config` sonuna eklenir |
| Sunucu host anahtarı | `%USERPROFILE%\.ssh\known_hosts` |
| `server\` | compose.yaml, Caddyfile, systemd dosyaları, script'ler, rag-api\ (app.py, Dockerfile), tools\pdf_to_md.py |
| `crawler\` | CLI tarayıcı (`aruba_crawl.py`); çıktılar (`commands.jsonl`) cihazdan üretilir |
| `vm-control\` | VM uyut/uyandır script'leri (Bölüm 23) ve masaüstü kısayolları **"AI Başlat"**, **"AI Uyut"** |
| VMware `.vmx` | `memsize` 24836 → 14336; yedek: `*.vmx.bak-24g` |

PC'de bunların dışında sistem ayarı değiştirilmez.

### Sunucu (VM)
| Değişiklik | Ayrıntı |
|---|---|
| SSH | Anahtar `~/.ssh/authorized_keys`'e eklenir; `~` izinleri `go-w`, `~/.ssh` 700, `authorized_keys` 600 |
| Disk | LVM kök bölümü 73 GB → 146 GB |
| Paketler | `docker.io`, `docker-compose-v2`; kullanıcı `docker` grubuna eklenir |
| Uygulama | `/opt/aruba-bot` |
| systemd | `aruba-bot.service`, `aruba-bot-ingest.service` + `.timer`, `aruba-bot-idle.service` + `.timer` (hepsi enabled) |
| Script'ler | `idle.sh`, `wake.sh`, `netdiag.sh` (ağ teşhisi), `docling-api.sh` (Docling API listesi) |
| Firewall | ufw aktif: 22, 80, 443 |
| Docker volume'leri | `aruba-bot_ollama`, `aruba-bot_webui`, `aruba-bot_ragdata`, `aruba-bot_caddy` |

---

## 21. Güvenlik sertleştirme

Dışarıya yalnız Caddy (80/443) açıktır. Canlı kullanımda şunları uygulayın.

**Erişim**
- Yönetici hesabı için güçlü ve benzersiz bir parola kullanın, parola yöneticisinde saklayın. Parolayı doküman, repo, sohbet veya betik içinde düz metin tutmayın.
- SSH'ta anahtar kullanın ve anahtarı passphrase ile koruyun. Anahtarla girişin çalıştığını doğruladıktan sonra parola girişini kapatın: `/etc/ssh/sshd_config.d/` altında `PasswordAuthentication no`, ardından `sudo systemctl restart ssh`.
- Parolasız sudo (`NOPASSWD`) tanımlamayın.
- Kullanılmayan anahtarları `~/.ssh/authorized_keys` dosyasından silin.

**Ağ**
- ufw yalnız 22, 80 ve 443'e izin versin; SSH'ı yönetim ağıyla sınırlayın (`sudo ufw allow from <yönetim-ağı> to any port 22`).
- compose'da Caddy dışındaki servislere `ports:` eklemeyin (Bölüm 10).
- Kendi imzalı sertifika yerine kuruma ait sertifika kullanılabilir (Bölüm 9).

**Uygulama**
- Open WebUI'da ilk hesabı (admin) kendiniz oluşturun, yeni kayıtları "pending" yapın, ham modelleri kullanıcılardan gizleyin (Bölüm 13).
- Web araması açıkken sorgular DuckDuckGo'ya gider; hassas bilgi içeren sorularda kullanmayın. Tamamen kapatmak için compose'da `ENABLE_WEB_SEARCH: "false"`.
- Crawler cihaz parolasını her çalıştırmada bir kez sorar ve diske yazmaz. Parola ve anahtar dosyaları `.gitignore`'dadır.

**Bakım**
- İşletim sistemi: `sudo apt-get update && sudo apt-get upgrade` (otomatik güvenlik güncellemesi için `unattended-upgrades`). İmajlar: `sudo docker compose pull && sudo docker compose up -d`.
- Yedek: Bölüm 18.

---

## 22. Sınırlar ve sonraki adımlar

**Bilinen sınırlar**
- CPU'da yavaş: ~3 token/sn, cevap 1–3 dk. Sunucu dizüstü bilgisayarla CPU paylaşıyor.
- Crawler'ın taramadığı alt modlardaki komutlar dizinde yok; doğrulama bunlarda ⚠️ verebilir.
- Sertifika kendi imzalı (tarayıcı uyarısı).
- Döküman içindeki diyagramlar yorumlanmaz, yalnızca OCR ile yazıları okunur.
- VM uyurken bota başka bilgisayarlardan erişilemez; uyanma ~30 sn – 3 dk.

**Önerilen sonraki adımlar**
1. GPU'lu sunucu (16 GB+ VRAM) → `qwen3:14b`, 10× hız. Mimari aynen taşınır.
2. Diğer markalar için crawler'lar.
3. 30–50 soruluk test seti ile düzenli kalite ölçümü.
4. Onaylanmış doğru cevapları "onaylı Q&A" olarak dizine geri eklemek.
5. Cevap üslubu veya komut formatı sorun çıkarırsa, en son seçenek olarak küçük bir LoRA fine-tune.

---

## 23. Bellek ve uyku yönetimi

### 23.1 Sorun
VM, dizüstü bilgisayarın üzerinde VMware Workstation ile çalışır. VMware, VM'in **bir kez kullandığı belleği** (VM içinde boşalsa bile) Windows'a geri vermez. İlk kurulumda VM'e 24 GB ayrılmıştı; yanında çalışan başka bir VM ile birlikte Windows'ta boş RAM **1,1 GB**'a düştü. VM içinde ise uygulamalar yalnızca ~3,5 GB kullanıyordu; geri kalanı model dosyalarının Linux dosya önbelleğiydi.

### 23.2 Dört katmanlı çözüm

| Katman | Ne yapar | Nerede |
|---|---|---|
| 1. Model boşaltma | Ollama modelleri 5 dk kullanılmazsa bellekten atar | `compose.yaml` → `OLLAMA_KEEP_ALIVE: "5m"` |
| 2. VM içi önbellek bırakma | Boştayken (model yüklü değil, indeksleme yok) Linux dosya önbelleğini boşaltır | Sunucu: `idle.sh` + `aruba-bot-idle.timer` (5 dk'da bir) |
| 3. VM belleğini küçültme | VM'e ayrılan RAM 24 GB → 14 GB | VMware `.vmx` → `memsize = "14336"` |
| 4. VM uykusu | **Elle**: masaüstündeki "AI Uyut" VM'i askıya alır. Otomatik uyku (zamanlanmış görev) kaldırıldı; PC'de arka planda hiçbir şey çalışmaz | PC: `<repo>\vm-control\` |

**Ölçülen sonuç:** Windows boş RAM: 1,1 GB → VM açıkken **15,5 GB**, VM uyurken **18,8 GB**.

### 23.3 VM belleğini değiştirme (nasıl yapıldı)
```powershell
$vr  = "C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"
$vmx = "C:\VMs\Sensei-Aruba\Sensei-Aruba.vmx"
Copy-Item $vmx "$vmx.bak-24g"                      # yedek
& $vr -T ws stop $vmx soft                         # düzgün kapatma
(Get-Content $vmx -Raw) -replace 'memsize = "\d+"','memsize = "14336"' | Set-Content $vmx -NoNewline -Encoding utf8NoBOM
& $vr -T ws start $vmx nogui                       # arayüzsüz başlat
```
VMware arayüzünden de yapılabilir: VM → Settings → Memory. VM içindeki Ollama sınırı da buna göre 10 GB'a çekildi. Geri almak için yedek `.vmx.bak-24g` dosyası kullanılabilir.

### 23.4 Sunucu tarafı dosyaları

**`/opt/aruba-bot/idle.sh`**
- `idle.sh status` → `idle` veya `active` yazar. `idle` = Ollama'da yüklü model yok **ve** rag-api indeksleme yapmıyor.
- `idle.sh` (argümansız, zamanlayıcıdan) → boştaysa ve önbellek 1 GB'tan büyükse `sync; echo 1 > /proc/sys/vm/drop_caches` (yalnızca dosya önbelleği; veri kaybı olmaz).

**`aruba-bot-idle.service` / `.timer`** → `idle.sh`'ı 5 dakikada bir çalıştırır.
```bash
sudo cp /opt/aruba-bot/aruba-bot-idle.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aruba-bot-idle.timer
sudo journalctl -u aruba-bot-idle -n 5     # "idle: dropped N MB page cache"
```

**`/opt/aruba-bot/wake.sh`** → VM açıldıktan / uyandıktan sonra HTTPS cevap verene kadar bekler, gerekirse onarır:
1. HTTPS zaten 200 ise çık.
2. `open-webui` ve `caddy` konteynerlerini yeniden başlat (uykudan sonra bayat kalan bağlantılar).
3. Hâlâ yoksa `systemctl daemon-reload` + **Docker servisini yeniden başlat** + `docker compose up -d`.

> **Neden 3. adım var:** Testlerde her uyanıştan (ve bir açılışta) sonra Docker iç ağı veri iletmedi: TCP bağlantısı kuruluyor ama TLS el sıkışması cevapsız kalıyordu; konteyner yeniden başlatma yetmedi, Docker servisini yeniden başlatmak düzeltti. Bu yüzden uyanma ~3 dakika sürebilir.

### 23.5 PC tarafı dosyaları (`<repo>\vm-control\`)

| Dosya | Görev |
|---|---|
| `ai-common.ps1` | Ortak ayarlar: `vmrun.exe` yolu, `.vmx` yolu, log fonksiyonu, `Get-VmIp` (VM'in IP'sini VMware'den sorar; sabit IP yok) |
| `ai-start.ps1` | **AI Başlat**: VM kapalı/uykudaysa başlatır (`vmrun start ... nogui`, 2 dk zaman aşımlı), VM'in IP'sini bulup SSH ile `wake.sh` çalıştırır, hazır olunca tarayıcıda arayüzü açar |
| `ai-sleep.ps1` | **AI Uyut**: VM'i hemen askıya alır (`vmrun suspend ... soft`) |
| `install.ps1` | Bir kerelik kurulum: masaüstü kısayolları (zamanlanmış görev yok) |
| `ai-vm.log` | Uyutma/uyandırma kayıtları (1 MB'ı geçince son 500 satır tutulur) |

**Kurulum:**
```powershell
& <repo>\vm-control\install.ps1
```
Bu komut:
- Masaüstüne **"AI Başlat"** ve **"AI Uyut"** kısayollarını koyar (VMware simgesiyle).

**Kontrol / kaldırma:**
```powershell
Get-Content <repo>\vm-control\ai-vm.log -Tail 20
```

### 23.6 Kullanım
- **Botu kullanmadan önce:** Masaüstündeki **AI Başlat**'a çift tıklayın. VM uykudaysa uyanır (~6 sn), arayüz hazır olunca (~30 sn – 3 dk) tarayıcıda açılır.
- **İşiniz bitince:** VM açık kalır; model 5 dk sonra kendini bellekten boşaltır, yeni istek gelince otomatik yüklenir. VM'in RAM'ini Windows'a geri istiyorsanız **AI Uyut**.
- **Uyku sırasında** başka bilgisayarlardan arayüz açılmaz. Ağ isteğiyle otomatik uyanma mümkün değildir; uyandırma yalnızca bu PC'den yapılır.
- **IP değişirse:** Betikler IP'yi VMware'den alır, Caddy sabit IP kullanmaz. Elle `ssh aruba-bot` kullanıyorsanız `~/.ssh/config` içindeki `HostName` değerini güncelleyin.
- **Önemli:** Bu PC kapalıyken veya uykudayken VM de çalışmaz.
