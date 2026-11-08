# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Emre Yiğit Taşdelen
"""Sensei-Aruba rag-api: vendor-agnostic CLI RAG API (OpenAI-compatible) with a judge layer.

Sources: /sources/<device>/commands.jsonl  (one {"device","mode","command","description"} per line)
         /sources/<device>/docs/*            (PDF/DOCX/PPTX/HTML/images via Docling; .md/.txt read directly)
Dropping a new device folder and calling POST /ingest (or restarting) indexes it.
"""
import hashlib, json, os, re, sqlite3, threading, time, uuid

import httpx
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastembed import TextEmbedding

DATA = os.getenv("DATA_DIR", "/data")
SRC = os.getenv("SOURCES_DIR", "/sources")
OLLAMA = os.getenv("OLLAMA_URL", "http://ollama:11434")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen3:8b")
VISION_MODEL = os.getenv("VISION_MODEL", "qwen2.5vl:7b")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "")
EMB_MODEL = os.getenv("EMB_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
TOP_K = int(os.getenv("TOP_K", "15"))
DOC_TOP_K = int(os.getenv("DOC_TOP_K", "4"))
DOCLING = os.getenv("DOCLING_URL", "http://docling:5001")
DOCLING_EXT = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
TEXT_EXT = {".md", ".txt"}
CHUNK, OVERLAP = 1000, 150
DB = os.path.join(DATA, "index.db")

SYSTEM = """Sen ağ cihazları için bir CLI komut asistanısın. Kurallar:
- Yalnızca BAĞLAM'daki komutlara dayan; komut uydurma.
- Komutları `ters tırnak` içinde, bağlamdaki yazımıyla ver. <...> alanlarını açıkla.
- Komutun hangi modda (config/enable/exec) çalıştığını belirt.
- Konfigürasyon istenirse bağlamdaki komutları doğru sırayla (önce global, sonra `interface ...` altında) bir ```kod bloğu``` içinde birleştir.
- DÖKÜMAN bölümü varsa açıklama, kavram ve adımlar için onu kullan; kullandığın her bilginin kaynağını [dosya › başlık] olarak yaz.
- Döküman bir komut gösteriyorsa ama komut dizininde yoksa bunu belirt.
- Bağlamda hiç ilgili bilgi yoksa açıkça "Bu bilgi dizinde ve dökümanlarda bulunamadı" de.
- Cevabı Türkçe ver."""

app = FastAPI()
state = {"status": "starting", "devices": {}, "docs": {}}
vecs, ids, tree = {}, {}, {}  # per device: embedding matrix, row ids, (first_token, len) -> token tuples
roots = {}                    # per device: set of first tokens of known commands
dvecs, dids = {}, {}          # per device: document chunk vectors and row ids
lock = threading.Lock()
embedder = None


def db():
    con = sqlite3.connect(DB, check_same_thread=False)
    con.execute("CREATE TABLE IF NOT EXISTS cmds(id INTEGER PRIMARY KEY, device TEXT, mode TEXT, command TEXT, description TEXT)")
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(command, description, device UNINDEXED, content='cmds', content_rowid='id')")
    con.execute("CREATE TABLE IF NOT EXISTS meta(device TEXT PRIMARY KEY, sha TEXT, count INTEGER)")
    con.execute("CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY, device TEXT, file TEXT, heading TEXT, text TEXT)")
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(text, heading, file, device UNINDEXED, content='docs', content_rowid='id')")
    con.execute("CREATE TABLE IF NOT EXISTS docs_meta(device TEXT, file TEXT, sha TEXT, chunks INTEGER, PRIMARY KEY(device, file))")
    return con


def convert(path):
    """File -> Markdown. Docling (async API, OCR on) for binary formats, direct read for text."""
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXT:
        return open(path, encoding="utf-8", errors="replace").read()
    with httpx.Client(timeout=120) as c:
        with open(path, "rb") as fh:
            r = c.post(f"{DOCLING}/v1/convert/file/async", files={"files": (os.path.basename(path), fh)},
                       data={"to_formats": "md", "image_export_mode": "placeholder", "do_ocr": "true"})
        r.raise_for_status()
        tid = r.json()["task_id"]
        while True:
            s = c.get(f"{DOCLING}/v1/status/poll/{tid}", params={"wait": 10}).json()
            if s.get("task_status") in ("success", "partial_success", "failure"):
                break
            time.sleep(2)
        if s["task_status"] == "failure":
            raise RuntimeError(f"docling failed: {s}")
        return c.get(f"{DOCLING}/v1/result/{tid}").json()["document"]["md_content"] or ""


def chunk_md(md):
    """Split Markdown by headings, then into ~CHUNK-char pieces with OVERLAP; returns (heading, text)."""
    out, heading, buf = [], "", ""

    def flush():
        nonlocal buf
        t = buf.strip()
        while len(t) > CHUNK:
            cut = t.rfind("\n", 0, CHUNK)
            cut = cut if cut > CHUNK // 2 else CHUNK
            out.append((heading, t[:cut].strip()))
            t = t[max(cut - OVERLAP, 1):]
        if len(t) > 40:
            out.append((heading, t))
        buf = ""

    for line in md.splitlines():
        m = re.match(r"^#{1,6}\s+(.*)", line)
        if m:
            flush()
            heading = m.group(1).strip()[:200]
        else:
            buf += line + "\n"
    flush()
    return out


def load_docs(con, dev):
    rows = con.execute("SELECT id FROM docs WHERE device=? ORDER BY id", (dev,)).fetchall()
    path = os.path.join(DATA, f"dvec_{dev}.npy")
    with lock:
        dids[dev] = np.array([r[0] for r in rows])
        dvecs[dev] = np.load(path) if rows and os.path.exists(path) else None
    state["docs"][dev] = {"files": con.execute("SELECT COUNT(*) FROM docs_meta WHERE device=?", (dev,)).fetchone()[0],
                          "chunks": len(rows)}


def ingest_docs(con, dev):
    folder = os.path.join(SRC, dev, "docs")
    files = {}
    if os.path.isdir(folder):
        for root, _, names in os.walk(folder):
            for n in names:
                if os.path.splitext(n)[1].lower() in DOCLING_EXT | TEXT_EXT:
                    p = os.path.join(root, n)
                    files[os.path.relpath(p, folder)] = p
    known = dict(con.execute("SELECT file, sha FROM docs_meta WHERE device=?", (dev,)).fetchall())
    changed = False
    for rel in set(known) - set(files):  # deleted files
        drop_doc(con, dev, rel)
        changed = True
    for rel, p in sorted(files.items()):
        sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
        if known.get(rel) == sha:
            continue
        state["docs"][dev] = f"converting {rel}"
        drop_doc(con, dev, rel)
        try:
            pieces = chunk_md(convert(p))
        except Exception as e:  # keep going with other files
            state.setdefault("errors", {})[f"{dev}/{rel}"] = str(e)[:300]
            continue
        con.executemany("INSERT INTO docs(device, file, heading, text) VALUES (?,?,?,?)", [(dev, rel, h, t) for h, t in pieces])
        con.execute("INSERT INTO docs_fts(rowid, text, heading, file, device) SELECT id, text, heading, file, device FROM docs WHERE device=? AND file=?", (dev, rel))
        con.execute("INSERT OR REPLACE INTO docs_meta VALUES (?,?,?,?)", (dev, rel, sha, len(pieces)))
        con.commit()
        changed = True
    vpath = os.path.join(DATA, f"dvec_{dev}.npy")
    if changed or (files and not os.path.exists(vpath)):
        state["docs"][dev] = "embedding"
        rows = con.execute("SELECT heading, text FROM docs WHERE device=? ORDER BY id", (dev,)).fetchall()
        if rows:
            v = np.array(list(embedder.embed([f"{h}\n{t}" for h, t in rows], batch_size=64)), dtype=np.float32)
            v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
            np.save(vpath, v)
        elif os.path.exists(vpath):
            os.remove(vpath)
        try:  # free Docling's in-memory models after a conversion batch
            httpx.post(f"{DOCLING}/v1/clear/converters", timeout=30)
        except Exception:
            pass
    load_docs(con, dev)


def drop_doc(con, dev, rel):
    con.execute("INSERT INTO docs_fts(docs_fts, rowid, text, heading, file, device) SELECT 'delete', id, text, heading, file, device FROM docs WHERE device=? AND file=?", (dev, rel))
    con.execute("DELETE FROM docs WHERE device=? AND file=?", (dev, rel))
    con.execute("DELETE FROM docs_meta WHERE device=? AND file=?", (dev, rel))
    con.commit()


def keep(cmd):
    return not (cmd.endswith(" <cr>") or cmd.endswith(" |") or cmd.endswith(" >") or cmd.endswith(" >>"))


def load_device(con, dev):
    rows = con.execute("SELECT id, command FROM cmds WHERE device=? ORDER BY id", (dev,)).fetchall()
    t = {}
    for _, c in rows:
        toks = tuple(c.split())
        if toks:
            t.setdefault((toks[0], len(toks)), []).append(toks)
    path = os.path.join(DATA, f"vec_{dev}.npy")
    with lock:
        ids[dev] = np.array([r[0] for r in rows])
        vecs[dev] = np.load(path) if os.path.exists(path) else None
        tree[dev] = t
        roots[dev] = {k[0] for k in t}


def ingest():
    global embedder
    state["status"] = "indexing"
    embedder = embedder or TextEmbedding(EMB_MODEL, cache_dir=os.path.join(DATA, "models"))
    con = db()
    devs = [d for d in sorted(os.listdir(SRC)) if os.path.isfile(os.path.join(SRC, d, "commands.jsonl"))]
    pending = []
    # Phase 1: keyword index for every device (fast), so all devices are usable within minutes
    for dev in devs:
        f = os.path.join(SRC, dev, "commands.jsonl")
        sha = hashlib.sha256(open(f, "rb").read()).hexdigest()
        old = con.execute("SELECT sha FROM meta WHERE device=?", (dev,)).fetchone()
        if not old or old[0] != sha:
            state["devices"][dev] = "indexing"
            con.execute("INSERT INTO fts(fts, rowid, command, description, device) SELECT 'delete', id, command, description, device FROM cmds WHERE device=?", (dev,))
            con.execute("DELETE FROM cmds WHERE device=?", (dev,))
            recs, seen = [], set()
            for line in open(f, encoding="utf-8"):
                r = json.loads(line)
                c = r["command"].strip()
                if keep(c) and c not in seen:
                    seen.add(c)
                    recs.append((dev, r.get("mode", ""), c, r.get("description", "")))
            con.executemany("INSERT INTO cmds(device, mode, command, description) VALUES (?,?,?,?)", recs)
            con.execute("INSERT INTO fts(rowid, command, description, device) SELECT id, command, description, device FROM cmds WHERE device=?", (dev,))
            con.commit()
            load_device(con, dev)  # keyword search usable while embeddings are computed
            state["devices"][dev] = "keyword-only (vectors queued)"
            pending.append((dev, sha))
        else:
            load_device(con, dev)
            state["devices"][dev] = con.execute("SELECT count FROM meta WHERE device=?", (dev,)).fetchone()[0]
    # Phase 2: dense vectors, one device at a time
    for dev, sha in pending:
        state["devices"][dev] = "keyword-only (vectors indexing)"
        rows = con.execute("SELECT command, description FROM cmds WHERE device=? ORDER BY id", (dev,)).fetchall()
        v = np.array(list(embedder.embed([f"{c} — {d}" for c, d in rows], batch_size=256)), dtype=np.float32)
        v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
        np.save(os.path.join(DATA, f"vec_{dev}.npy"), v)
        con.execute("INSERT OR REPLACE INTO meta VALUES (?,?,?)", (dev, sha, len(rows)))
        con.commit()
        load_device(con, dev)
        state["devices"][dev] = len(rows)
    # Phase 3: documents (sources/<device>/docs)
    for dev in devs:
        ingest_docs(con, dev)
    state["status"] = "ready"


@app.on_event("startup")
def startup():
    os.makedirs(DATA, exist_ok=True)
    threading.Thread(target=ingest, daemon=True).start()


SYNONYMS = {  # user wording -> CLI vocabulary (extend per vendor as needed)
    r"802\.?1x": "dot1x port-access authenticator",
    r"\bmab\b|mac[- ]?auth": "mac-auth port-access",
    r"\bradius\b": "radius-server radius aaa",
    r"\bvlan\b": "vlan access trunk",
    r"\b(ge|gi|port|interface|int)\s*(\d+)[ /](\d+)[ /](\d+)": r"interface \2/\3/\4",
    r"\btrunk\b": "vlan trunk allowed native",
    r"\blacp\b|port[- ]?channel": "lag lacp",
}
STOP = {"bana", "için", "icin", "yaz", "nasıl", "nasil", "ver", "olan", "bir", "ile", "config", "konfigürasyon", "komut", "the", "for"}


def expand(q):
    extra = []
    for pat, rep in SYNONYMS.items():
        for m in re.finditer(pat, q, re.I):
            extra.append(m.expand(rep) if "\\" in rep else rep)
    return q + " " + " ".join(extra)


def search(devs, q):
    con = db()
    score = {}
    q = expand(q)
    terms = [t for t in re.findall(r"[\w\-]+", q.lower()) if len(t) > 1 and t not in STOP and not t.isdigit()]
    if terms:
        marks = ",".join("?" * len(devs))
        rows = con.execute(f"SELECT rowid FROM fts WHERE fts MATCH ? AND device IN ({marks}) ORDER BY bm25(fts) LIMIT 50",
                           [" OR ".join(f'"{t}"' for t in terms), *devs]).fetchall()
        for rank, (i,) in enumerate(rows):
            score[i] = score.get(i, 0) + 1 / (60 + rank)
    vec_devs = [d for d in devs if vecs.get(d) is not None]
    if vec_devs:
        qv = np.array(next(iter(embedder.embed([q]))), dtype=np.float32)
        qv /= np.linalg.norm(qv) + 1e-9
    for d in vec_devs:
        s = vecs[d] @ qv
        for rank, j in enumerate(np.argsort(-s)[:50]):
            i = int(ids[d][j])
            score[i] = score.get(i, 0) + 1 / (60 + rank)
    best = sorted(score, key=score.get, reverse=True)[:TOP_K]
    if not best:
        return []
    rows = con.execute(f"SELECT id, device, mode, command, description FROM cmds WHERE id IN ({','.join(map(str, best))})").fetchall()
    order = {i: n for n, i in enumerate(best)}
    return sorted(rows, key=lambda r: order[r[0]])


def search_docs(dev, q):
    """Hybrid (BM25 + vector) search over the device's document chunks."""
    if not len(dids.get(dev, [])):
        return []
    con = db()
    q = expand(q)
    terms = [t for t in re.findall(r"[\w\-\.]+", q.lower()) if len(t) > 1 and t not in STOP and not t.isdigit()]
    score = {}
    if terms:
        rows = con.execute("SELECT rowid FROM docs_fts WHERE docs_fts MATCH ? AND device=? ORDER BY bm25(docs_fts) LIMIT 30",
                           [" OR ".join(f'"{t}"' for t in terms), dev]).fetchall()
        for rank, (i,) in enumerate(rows):
            score[i] = score.get(i, 0) + 1 / (60 + rank)
    if dvecs.get(dev) is not None:
        qv = np.array(next(iter(embedder.embed([q]))), dtype=np.float32)
        qv /= np.linalg.norm(qv) + 1e-9
        s = dvecs[dev] @ qv
        for rank, j in enumerate(np.argsort(-s)[:30]):
            i = int(dids[dev][j])
            score[i] = score.get(i, 0) + 1 / (60 + rank)
    best = sorted(score, key=score.get, reverse=True)[:DOC_TOP_K]
    if not best:
        return []
    rows = con.execute(f"SELECT id, file, heading, text FROM docs WHERE id IN ({','.join(map(str, best))})").fetchall()
    order = {i: n for n, i in enumerate(best)}
    return sorted(rows, key=lambda r: order[r[0]])


def placeholder(tok):
    return tok.startswith("<") or tok.isupper() or "A.B.C.D" in tok or tok.startswith("[")


def verify(devs, answer):
    """Deterministic judge: every `command` in the answer must exist in the device tree."""
    ok, bad = [], []
    blocks = re.findall(r"```[^\n]*\n(.*?)```", answer, re.S)
    inline = re.findall(r"`([^`\n]{2,})`", re.sub(r"```.*?```", "", answer, flags=re.S))
    lines = [l for b in blocks for l in b.splitlines() if l.strip() and not l.strip().startswith(("!", "#"))]
    for raw in dict.fromkeys(inline + lines):
        c = re.sub(r"^\S*[#>]\s*", "", raw.strip())
        toks = tuple(c.split())
        # only judge things that look like commands of this device (skip file names, parameter names, prose)
        if not toks or not re.match(r"^[a-z]", toks[0]) or not any(toks[0] in roots.get(d, ()) for d in devs):
            continue
        hit = any(all(a == b or placeholder(b) for a, b in zip(toks, known))
                  for d in devs for known in tree.get(d, {}).get((toks[0], len(toks)), []))
        (ok if hit else bad).append(c)
    return ok, bad


def text_of(content):
    if isinstance(content, str):
        return content, []
    txt = " ".join(p.get("text", "") for p in content if p.get("type") == "text")
    imgs = [p["image_url"]["url"].split(",", 1)[1] for p in content
            if p.get("type") == "image_url" and p["image_url"]["url"].startswith("data:")]
    return txt, imgs


async def ollama_chat(model, messages, stream):
    body = {"model": model, "messages": messages, "stream": stream, "think": False}
    async with httpx.AsyncClient(timeout=None) as c:
        if not stream:
            r = await c.post(f"{OLLAMA}/api/chat", json=body)
            yield r.json()["message"]["content"]
            return
        async with c.stream("POST", f"{OLLAMA}/api/chat", json=body) as r:
            async for line in r.aiter_lines():
                if line:
                    yield json.loads(line).get("message", {}).get("content", "")


async def judge(context, answer):
    if not JUDGE_MODEL or not context:
        return ""
    prompt = (f"BAĞLAM:\n{context}\n\nCEVAP:\n{answer}\n\n"
              "Cevaptaki komutlar ve iddialar BAĞLAM ile destekleniyor mu? Tek satırla yanıt ver: "
              "'ONAY: <kısa gerekçe>' veya 'RED: <hangi kısım desteklenmiyor>'.")
    out = ""
    async for t in ollama_chat(JUDGE_MODEL, [{"role": "user", "content": prompt}], False):
        out += t
    return out.strip().splitlines()[0] if out.strip() else ""


def devices_for(model):
    return [model]


@app.get("/health")
def health():
    return state


@app.post("/ingest")
def reindex():
    if state["status"] in ("starting", "indexing"):
        return {"started": False, "reason": state["status"]}
    threading.Thread(target=ingest, daemon=True).start()
    return {"started": True}


@app.get("/v1/models")
def models():
    names = list(state["devices"])  # one model per device; devices are never mixed
    return {"object": "list", "data": [{"id": n, "object": "model", "owned_by": "rag-api"} for n in names]}


@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    model, stream = body.get("model", ""), body.get("stream", False)
    devs = devices_for(model)
    msgs = body.get("messages", [])
    question, images = text_of(msgs[-1]["content"])

    devs = [d for d in devs if d in tree]
    if not devs:
        msg = f"İndeks henüz hazır değil, birkaç dakika sonra tekrar deneyin. Durum: {state['devices']}"
        if stream:
            return StreamingResponse(iter([
                "data: " + json.dumps({"id": "x", "object": "chat.completion.chunk", "model": model,
                                       "choices": [{"index": 0, "delta": {"content": msg}, "finish_reason": "stop"}]}) + "\n\n",
                "data: [DONE]\n\n"]), media_type="text/event-stream")
        return JSONResponse({"id": "x", "object": "chat.completion", "model": model,
                             "choices": [{"index": 0, "message": {"role": "assistant", "content": msg}, "finish_reason": "stop"}]})
    hits = search(devs, question) if question.strip() else []
    prefix = "" if all(vecs.get(d) is not None for d in devs) else "_(Vektör indeksi hazırlanıyor, şimdilik anahtar kelime araması)_\n\n"
    context = "\n".join(f"[{d} | {m}] {c} — {desc}" for _, d, m, c, desc in hits)
    doc_hits = search_docs(devs[0], question) if question.strip() else []
    if doc_hits:
        context += "\n\nDÖKÜMAN:\n" + "\n\n".join(f"[{f} › {h or '-'}]\n{t}" for _, f, h, t in doc_hits)

    history = [{"role": m["role"], "content": text_of(m["content"])[0]} for m in msgs[:-1][-6:] if m["role"] in ("user", "assistant")]
    user = {"role": "user", "content": f"BAĞLAM:\n{context or '(boş)'}\n\nSORU: {question}"}
    if images:
        user["images"] = images
    llm_msgs = [{"role": "system", "content": SYSTEM}, *history, user]
    llm = VISION_MODEL if images else CHAT_MODEL
    cid = f"chatcmpl-{uuid.uuid4().hex}"

    async def footer(answer):
        ok, bad = verify(devs, answer)
        lines = ["\n\n---"]
        if ok or bad:
            lines.append(f"**Doğrulama:** ✅ {len(ok)} komut dizinde var" + (f" · ⚠️ dizinde yok: {', '.join(f'`{b}`' for b in bad)}" if bad else ""))
        verdict = await judge(context, answer)
        if verdict:
            lines.append(f"**Hakem:** {verdict}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def chunk(text, finish=None):
        return "data: " + json.dumps({"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
                                      "choices": [{"index": 0, "delta": {"content": text} if text else {}, "finish_reason": finish}]}) + "\n\n"

    if stream:
        async def gen():
            answer = ""
            if prefix:
                yield chunk(prefix)
            async for t in ollama_chat(llm, llm_msgs, True):
                answer += t
                yield chunk(t)
            yield chunk(await footer(answer))
            yield chunk("", "stop")
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    answer = ""
    async for t in ollama_chat(llm, llm_msgs, False):
        answer += t
    full = prefix + answer + await footer(answer)
    return JSONResponse({"id": cid, "object": "chat.completion", "created": int(time.time()), "model": model,
                         "choices": [{"index": 0, "message": {"role": "assistant", "content": full}, "finish_reason": "stop"}]})
