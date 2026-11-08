# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Emre Yiğit Taşdelen
"""Converts aruba_cli_tree_*.md files into the commands.jsonl that rag-api reads.

Usage: python tree_to_jsonl.py --device aruba-vmc aruba_cli_tree_*.md -o commands.jsonl
One line per record: {"device","mode","command","description","text"}. Each (mode, command) pair is written once.
"""
import argparse
import json
import re

MODE = re.compile(r"^## Mod(?:e)?: (\S+)")  # "## Mod:" in trees written by older crawls
CMD = re.compile(r"^\s*- `(.*?)`(?: — (.*))?$")
FILE = re.compile(r"aruba_cli_tree_([A-Za-z0-9]+)_")
PLACEHOLDERS = ("(crawled separately)", "(ayri taranir)")  # the crawler visits this branch in another session (second form: older crawls)


def convert(paths, device):
    seen = set()
    for path in paths:
        # Files crawled with --root may have no "## Mode:" heading: take the mode from the file name (aruba_cli_tree_<mode>_<root>.md)
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
                if desc in PLACEHOLDERS:
                    desc = ""
                if (mode, cmd) in seen:
                    continue
                seen.add((mode, cmd))
                text = f"[{device} | {mode}] {cmd}" + (f" — {desc}" if desc else "")
                yield {"device": device, "mode": mode, "command": cmd, "description": desc, "text": text}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trees", nargs="+", help="aruba_cli_tree_*.md files")
    ap.add_argument("--device", required=True, help="device name (same as the folder / model name)")
    ap.add_argument("-o", "--out", default="commands.jsonl")
    a = ap.parse_args()
    n = 0
    with open(a.out, "w", encoding="utf-8") as out:
        for rec in convert(a.trees, a.device):
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"{n} commands written: {a.out}")


if __name__ == "__main__":
    main()
