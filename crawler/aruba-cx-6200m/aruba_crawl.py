# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Emre Yiğit Taşdelen
"""Aruba CX 6200M CLI crawler: walks the command tree depth-first with '?' and writes every finding to the document immediately.
It runs no command (Enter is pressed only for: no paging, enable, configure terminal, exit).
If interrupted, run it again; it resumes from the state file.
Usage: python aruba_crawl.py --host <cihaz-ip> [--depth 8]
Credentials: ARUBA_USER / ARUBA_PASS / ARUBA_ENABLE environment variables, or asked in the terminal.
"""
import argparse, getpass, json, os, re, time
import paramiko

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = STATE = None
WAIT = 0.5
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[=>]")
PROMPT = re.compile(r"^\S+(\([^)]*\))?[#>] ")
LINE = re.compile(r"^\s{0,10}(\S+)(?:\s{2,}(.*))?$")


class Cli:
    def __init__(self, a, user, pw, en):
        self.a, self.user, self.pw, self.en = a, user, pw, en
        self.mode = None
        self.connect()

    def connect(self):
        self.c = paramiko.SSHClient()
        self.c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.c.connect(self.a.host, username=self.user, password=self.pw,
                       look_for_keys=False, allow_agent=False, timeout=15)
        self.sh = self.c.invoke_shell(width=250, height=1000)
        banner = self.read_quiet(3)
        self.line("no page")
        self.mode = "exec"

    def read_quiet(self, quiet=0.8, end=None, maxt=20):
        buf, last, t0 = "", time.time(), time.time()
        while time.time() - t0 < maxt:
            if self.sh.recv_ready():
                d = self.sh.recv(65535).decode("utf-8", "ignore")
                buf += d
                last = time.time()
                if "--More--" in d or "-- More --" in d:
                    self.sh.send(" ")
                continue
            tail = ANSI.sub("", buf).replace("\r", "").rstrip("\n").split("\n")[-1]
            if end is not None and tail.endswith(end) and PROMPT.search(tail[: len(tail) - len(end)].rstrip() + " ") is not None:
                if time.time() - last > 0.15:
                    break
            elif time.time() - last > quiet and (end is None or time.time() - last > 3):
                break
            time.sleep(0.05)
        return ANSI.sub("", buf).replace("\r", "")

    def line(self, s):
        self.sh.send(s + "\n")
        return self.read_quiet(1.0)

    def set_mode(self, m):
        if m == self.mode:
            return
        if m == "config":
            self.line("configure terminal")
        else:
            self.line("end")
        self.mode = m

    def ask(self, cmd):
        typed = (cmd + " ") if cmd else ""
        self.sh.send(typed + "?")
        out = self.read_quiet(WAIT, end=typed)
        self.sh.send("\b" * (len(typed) + 4) + "\x15")
        self.read_quiet(0.4)
        return out


def parse(out, cmd):
    lines = out.split("\n")
    res = []
    for ln in lines[1:]:
        if PROMPT.search(ln.rstrip() + " ") and ln.rstrip().endswith(cmd.strip()) or not ln.strip():
            continue
        if ln.lstrip().startswith(("%", "Invalid", "Error", "^")):
            continue
        m = LINE.match(ln)
        if m:
            res.append((m.group(1), (m.group(2) or "").strip()))
    seen, uniq = set(), []
    for k, d in res:
        if k not in seen:
            seen.add(k)
            uniq.append((k, d))
    return uniq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--depth", type=int, default=8)
    ap.add_argument("--modes", default="exec,config")
    ap.add_argument("--root", default="", help="mode:command, e.g. exec:show (empty = whole tree)")
    ap.add_argument("--skip", default="", help="mode:command prefix; do not descend into this branch")
    ap.add_argument("--wait", type=float, default=0.5)
    a = ap.parse_args()
    global DOC, STATE, WAIT
    WAIT = a.wait
    tag = re.sub(r"\W+", "_", a.root) if a.root else "all"
    DOC = os.path.join(HERE, f"aruba_cli_tree_{tag}.md")
    STATE = os.path.join(HERE, f"state_{tag}.json")
    user = os.environ.get("ARUBA_USER") or input("User: ")
    pw = os.environ.get("ARUBA_PASS") or getpass.getpass("Password: ")
    en = os.environ.get("ARUBA_ENABLE") or pw

    if os.path.exists(STATE):
        st = json.load(open(STATE, encoding="utf-8"))
    else:
        if a.root:
            m, c = a.root.split(":", 1)
            st = {"stack": [[m, c, len(c.split())]], "done": 0}
        else:
            st = {"stack": [[m, "", 0] for m in reversed(a.modes.split(","))], "done": 0}
        open(DOC, "w", encoding="utf-8").write(f"# Aruba CX 6200M CLI Tree ({a.host})\n\n")
    cli = Cli(a, user, pw, en)
    doc = open(DOC, "a", encoding="utf-8")

    keys = {}
    for ln in open(DOC, encoding="utf-8"):
        m = re.match(r"\s*- `([^`]+)`", ln)
        if m:
            t = m.group(1).split()
            keys.setdefault(" ".join(t[:-1]), set()).add(t[-1])

    for _m, c, _d in st["stack"]:
        t = c.split()
        if t:
            keys.setdefault(" ".join(t[:-1]), set()).add(t[-1])

    def pooled(c):
        t = c.split()
        for j in range(2, len(t) - 2):
            P = keys.get(" ".join(t[:j]), ())
            if t[j] in P and t[j + 1] in P and t[j + 2] in P:
                return True
        return False

    while st["stack"]:
        mode, cmd, depth = st["stack"][-1]
        if pooled(cmd):
            st["stack"].pop()
            continue
        try:
            cli.set_mode(mode)
            out = cli.ask(cmd)
        except Exception as e:
            print("Connection error, reconnecting:", e)
            time.sleep(5)
            try:
                cli.connect()
            except Exception as e2:
                print("Retry failed:", e2)
                time.sleep(20)
            continue
        st["stack"].pop()
        items = parse(out, cmd)
        desc = st.get("desc", {}).pop(f"{mode}|{cmd}", "")
        if not cmd:
            doc.write(f"\n## Mode: {mode}\n\n")
        else:
            doc.write(f"{'  ' * (depth - 1)}- `{cmd}`" + (f" — {desc}" if desc else "") + "\n")
        children = []
        sig = (cmd.split()[-1] if cmd else "") + "|" + ",".join(sorted(k for k, _ in items))
        seen = st.setdefault("seen", {})
        repeat = bool(cmd) and sig in seen
        seen[sig] = 1
        for k, d in items:
            full = f"{cmd} {k}".strip()
            keys.setdefault(cmd, set()).add(k)
            if repeat:
                doc.write(f"{'  ' * depth}- `{full}`" + (f" — {d}" if d else "") + "\n")
            elif a.skip and f"{mode}:{full}" == a.skip:
                doc.write(f"{'  ' * depth}- `{full}` — (crawled separately)\n")
            elif not k.startswith(("<", "|")) and depth + 1 <= a.depth and not re.match(r"^[A-Z]", k):
                children.append([mode, full, depth + 1])
                st.setdefault("desc", {})[f"{mode}|{full}"] = d
            else:
                doc.write(f"{'  ' * depth}- `{full}`" + (f" — {d}" if d else "") + "\n")
        st["stack"].extend(reversed(children))
        st["done"] += 1
        doc.flush()
        json.dump(st, open(STATE, "w", encoding="utf-8"))
        print(f"[{st['done']}] {mode}: {cmd or '(root)'} -> {len(items)} | queue {len(st['stack'])}")
    doc.write("\n_Completed._\n")
    doc.close()
    print("Done:", DOC)


if __name__ == "__main__":
    main()
