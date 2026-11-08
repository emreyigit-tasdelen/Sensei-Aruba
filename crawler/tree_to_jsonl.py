# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Emre Yiğit Taşdelen
"""aruba_cli_tree_*.md dosyalarını rag-api'nin okuduğu commands.jsonl'a çevirir.

Kullanim: python tree_to_jsonl.py --device aruba-vmc aruba_cli_tree_*.md -o commands.jsonl
Her satir: {"device","mode","command","description","text"}. Ayni (mod, komut) bir kez yazilir.
"""
import argparse
import json
import re

MODE = re.compile(r"^## Mod: (\S+)")
CMD = re.compile(r"^\s*- `(.*?)`(?: — (.*))?$")
FILE = re.compile(r"aruba_cli_tree_([A-Za-z0-9]+)_")
PLACEHOLDER = "(ayri taranir)"  # crawler bu dali ayri oturumda tarar


def convert(paths, device):
    seen = set()
    for path in paths:
        # --root ile taranan dosyalarda "## Mod:" basligi olmayabilir: mod dosya adindan (aruba_cli_tree_<mod>_<kok>.md)
        m0 = FILE.search(path.replace("\\", "/"))
        mode = m0.group(1) if m0 else ""
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                m = MODE.match(line)
                if m:
                    mode = m.group(1)
                    continue
                m = CMD.match(line)
                if not m or not mode:
                    continue
                cmd, desc = m.group(1), (m.group(2) or "")
                if desc == PLACEHOLDER:
                    desc = ""
                if (mode, cmd) in seen:
                    continue
                seen.add((mode, cmd))
                text = f"[{device} | {mode}] {cmd}" + (f" — {desc}" if desc else "")
                yield {"device": device, "mode": mode, "command": cmd, "description": desc, "text": text}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trees", nargs="+", help="aruba_cli_tree_*.md dosyalari")
    ap.add_argument("--device", required=True, help="cihaz adi (klasor/model adi ile ayni)")
    ap.add_argument("-o", "--out", default="commands.jsonl")
    a = ap.parse_args()
    n = 0
    with open(a.out, "w", encoding="utf-8") as out:
        for rec in convert(a.trees, a.device):
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"{n} komut yazildi: {a.out}")


if __name__ == "__main__":
    main()
