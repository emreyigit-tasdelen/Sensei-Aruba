# Sensei-Aruba — Problems and Solutions

[English](troubleshooting.md) · [Türkçe](tr/sorunlar-ve-cozumler.md)

| Problem | Cause (root cause) | Fix | Prevention |
|---|---|---|---|
| SSH drops while a model runs | Ollama takes all the CPU, the VM shares the CPU with the laptop | Ollama `cpus: 10`, docling/rag-api `cpus: 4` | A CPU limit on every service |
| `scp` → Permission denied | Docker created the `sources` folder owned by root | `sudo chown -R $USER:$USER sources` | Create the folders before running compose |
| "Not found" + Judge RED while the index is not ready | The answer was generated with empty context | Two-stage indexing (keywords first); the judge does not run on empty context | — |
| The VMC model is not in the list | Indexing was sequential, VMC waited for 6200M | Keyword indexes of all devices first, then the vectors | — |
| "802.1x" finds nothing | The user's term ≠ the CLI term (`dot1x`) | Synonym dictionary (`SYNONYMS`) | Extend the dictionary for a new brand |
| An Open WebUI setting in Compose is not applied | The settings are written to the database on first start | `ENABLE_PERSISTENT_CONFIG: false` | — |
| Free RAM in Windows is 1.1 GB | VMware does not give back the memory the VM used; the VM had 24 GB | VM 14 GB, the model unloads after 5 min, idle cache is dropped, AI Sleep | Give the VM only as much RAM as you need |
| The web UI does not open after sleep | Docker's internal network does not forward data after sleep (TCP works, TLS gets no answer) | `wake.sh`: containers first, then the Docker service is restarted if needed | AI Start does this automatically (~3 min) |
| A 4111-page PDF never finishes in Docling | OCR/layout analysis on CPU takes seconds per page | `pdf_to_md.py` (PyMuPDF + bookmarks → headings) | Use this tool for large text PDFs |
| Words run together in markitdown output | The PDF text layer has no space characters | PyMuPDF rebuilds the spaces from positions | Check a sample page after conversion |
| Verification says file/parameter names are "not in the index" | Every backticked expression was taken for a command | Only expressions that start with the device's command root are checked | — |
| Web UI 502 (Caddy up, Open WebUI healthy) | The Caddyfile on the server had been changed to `reverse_proxy 127.0.0.1:8080`; because Caddy runs in its own container, 127.0.0.1 is itself | The Caddyfile from the repo (`open-webui:8080`) was sent and caddy was restarted | Do not edit files on the server by hand; change them in the repo and then copy. If you see `dial tcp 127.0.0.1:8080` in the Caddy log, this is it |
| `ssh aruba-bot` is not resolved from Bash | Git Bash's ssh does not read the Windows `~/.ssh/config` | `C:\Windows\System32\OpenSSH\ssh.exe` | — |
| A key is corrupted after being added to the server | PowerShell pipeline encoding / CRLF | Read the key into a variable and write it as one line ([USAGE.md §5.3](USAGE.md#53-adding-the-key-to-the-server-one-time-with-the-password)) | — |
| A `.sh` file says "not found" / strange error | Windows CRLF line endings | `sed -i 's/\r$//' file` | Keep `.sh` files LF (`.gitattributes`) |

## Crawler lessons (CLI tree crawling)

| Problem | Cause (root cause) | Fix | Prevention |
|---|---|---|---|
| The crawl does not finish after 45k steps (`show ap database ...`) | Filter/sort options (`usb`, `indoor`, `status`...) can be typed in any order one after another; the DFS walks every permutation separately | If the same last word + the same set of sub-options was already seen, do not descend (`seen`); in algorithm lists (`ssh key-exchange-algorithms`) a branch that descends to a 3rd choice from the same pool is skipped (`pooled`) | On a new brand crawl wide first with `--depth 5`; if the queue does not shrink, there is a permutation branch |
| The 6200M refused SSH login for a while (`Error reading SSH protocol banner`) | After ~14k `?` queries the device blocked temporarily (the exact cause was not verified); ping worked | The script retried every 20–30 s and resumed from the state when the block lifted | Keep the speed reasonable with `--wait`; run it with retries |
| The crawl prompt was not recognized on AOS-CX | The VMC prompt is `(host) [node] #`, the CX prompt is `host#`; CX has no `enable`, paging is turned off with `no page` | A `PROMPT` regex, `no page` and the mode name `exec` in the CX copy | New device = first try the prompt regex and the paging command by hand |
| Parallel crawling | A single session took hours | A separate session per branch with `--root mode:command` (3 in parallel), overlaps avoided with `--skip` | Mind the device's session limit |

> The crawler runs no command; it only types and presses `?`, then clears the line. The password is not kept in the code.
