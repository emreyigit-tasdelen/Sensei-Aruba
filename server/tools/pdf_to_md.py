# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Emre Yiğit Taşdelen
"""Fast PDF -> Markdown for very large, text-based PDFs (e.g. 4000-page CLI reference guides).

Docling on CPU is too slow for thousands of pages, so this uses PyMuPDF:
- keeps correct word spacing (plain text extractors often glue words together),
- turns the PDF bookmarks (table of contents) into headings, so rag-api can cite
  "[file › command › section]",
- drops running page headers/footers.

Usage:  pip install pymupdf
        python pdf_to_md.py <input.pdf> <output.md>
The .md is then copied to sources/<device>/docs/ (rag-api reads .md directly).
"""
import re
import sys
from collections import Counter, defaultdict

import pymupdf


def main(src, dst):
    doc = pymupdf.open(src)
    marks = defaultdict(list)  # page index -> [(level, title)]
    for level, title, page in doc.get_toc():
        if page >= 1:
            marks[page - 1].append((level, " ".join(title.split())))

    pages = [doc[i].get_text("text").splitlines() for i in range(len(doc))]
    # lines repeated on many pages are headers/footers ("AOS-8 | Reference Guide", "91 | aaa profile")
    common = Counter(l.strip() for p in pages for l in set(p[:3] + p[-3:]) if l.strip())
    noise = {l for l, n in common.items() if n > len(doc) * 0.2}
    page_no = re.compile(r"^\d+\s*\|\s*.+$|^.+\|\s*\d+$|^\d+$")

    out, path = [], []
    for i, lines in enumerate(pages):
        for level, title in marks.get(i, []):
            path = path[: level - 1] + [title]
            out.append("\n" + "#" * min(level, 6) + " " + " › ".join(path) + "\n")
        for l in lines:
            s = l.strip()
            if s and s not in noise and not page_no.match(s):
                out.append(s)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(f"# {doc.metadata.get('title') or src.rsplit('/', 1)[-1]}\n\n" + "\n".join(out))
    print(f"{len(doc)} pages, {len(marks)} pages with headings -> {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
