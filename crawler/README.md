# Crawler

`aruba_crawl.py` connects to a device over SSH and walks its CLI help tree with `?` (depth-first). It never runs a command: it only sends Enter, `no paging`, `enable`, `configure terminal` and `exit`. If interrupted, rerun it and it resumes from `state_*.json`.

```powershell
pip install paramiko
python aruba-vmc\aruba_crawl.py --host <device-ip>          # asks for the password once, never writes it to disk
.\aruba-vmc\run_crawl.ps1                                     # same, but restarts after a crash
```

Output (git-ignored, generated per device):

| File | Content |
|---|---|
| `aruba_cli_tree_<mode>.md` | readable command tree |
| `state_<mode>.json` | resume state |
| `commands.jsonl` | one JSON per line (`device`, `mode`, `command`, `description`, `text`), read by rag-api |

`commands.sample.jsonl` is a 300-line excerpt showing the format. The full command text is vendor documentation (HPE/Aruba), so it is not shipped here: produce it from your own device and licence.
