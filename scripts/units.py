#!/usr/bin/env python3
"""units.py - read a paper (PDF / docx / md / txt / tex / json) into addressable evidence units (E012), sentences (E012.3), sections, pages, bbox.

Shared reading layer of the nanopublication builder (vendored from scholarly-note-cards 1.0.0; PDF parsing is scripts/parse_pdf.py).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nlib  # noqa: E402

EXCLUDED_SECTIONS = re.compile(r"^\s*(\d+[.\s]+)?(references?|bibliography|literature cited|acknowledge?ments?|funding|conflicts? of interest|author contributions|(table of )?contents|参考文献|致谢|目录)\s*$", re.I)
OPTIONAL_SECTIONS = re.compile(r"^\s*(\d+[.\s]+)?(appendix|appendices|supplementary|supplemental|附录)", re.I)

# ------------------------------------------------------------------------------------------------ io
def jload(p, default=None):
    if not os.path.isfile(p):
        return default
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def jsave(p, obj):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def find_key(obj, names):
    if isinstance(obj, dict):
        for k in names:
            if k in obj:
                return obj[k]
        for v in obj.values():
            r = find_key(v, names)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, names)
            if r is not None:
                return r
    return None


# ------------------------------------------------------------------------------------------------ source loading (PDF / docx / md / txt / tex / json)
def load_source(path, work, args):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        out = os.path.join(work, "parsed")
        cmd = [sys.executable, os.path.join(HERE, "parse_pdf.py"), path, "--out", out]
        if args.ocr:
            cmd += ["--ocr", args.ocr]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            summary = json.loads(res.stdout.strip().splitlines()[-1])
        except Exception:
            raise SystemExit("PDF parsing failed: %s" % (res.stdout[-300:] + res.stderr[-300:]))
        if summary.get("status") == "failed":
            raise SystemExit("PDF parsing failed: %s" % json.dumps(summary, ensure_ascii=False))
        doc = jload(os.path.join(out, "parsed.json"))
        tables = {t["id"]: t for t in doc.get("tables", [])}
        blocks = []
        for b in doc["blocks"]:
            t = b["type"]
            blk = {"type": {"reference_block": "reference"}.get(t, t), "text": b.get("text", ""), "pages": b.get("pages") or [b["page"]], "page": b["page"], "bbox": b.get("bbox"),
                   "block": b["id"], "level": b.get("level"), "number": b.get("number")}
            if t == "table":
                tb = tables.get(b.get("table_id"))
                if not tb:
                    continue
                blk["text"] = tb["markdown"]
                blk["pages"] = tb["pages"]
            blocks.append(blk)
        return blocks, {"format": "pdf", "parser_status": doc["status"], "parser_warnings": doc.get("warnings", []), "unparsed": doc.get("unparsed", []), "pages": doc["source"]["pages"],
                        "file": os.path.basename(path), "pdf_metadata": doc["source"].get("metadata", {})}
    if ext == ".docx":
        return docx_blocks(path), {"format": "docx", "file": os.path.basename(path)}
    with open(path, encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    if ext == ".json":
        try:
            obj = json.loads(raw)
        except Exception:
            obj = None
        if obj is not None:
            blocks = json_blocks(obj)
            if blocks:
                return blocks, {"format": "json", "file": os.path.basename(path)}
    return text_blocks(raw, ext), {"format": ext.lstrip(".") or "txt", "file": os.path.basename(path)}


def json_blocks(obj):
    """Accept {title, abstract, sections:[{heading, paragraphs}]}, {full_text:{section_name, paragraphs}}, {paragraphs:[...]}, {text:'...'}."""
    blocks = []

    def add(typ, text, **kw):
        if text and str(text).strip():
            blocks.append({"type": typ, "text": str(text).strip(), "pages": [kw.get("page")] if kw.get("page") else [], "page": kw.get("page"), "bbox": None,
                           "block": "j%d" % len(blocks), "level": kw.get("level"), "number": None})
    if isinstance(obj, dict):
        if obj.get("title"):
            add("title", obj["title"], level=0)
        if obj.get("abstract"):
            add("abstract", obj["abstract"])
        ft = obj.get("full_text")
        if isinstance(ft, dict) and "section_name" in ft:
            for name, paras in zip(ft["section_name"], ft["paragraphs"]):
                add("heading", name, level=1)
                for p in paras:
                    add("paragraph", p)
            return blocks
        secs = obj.get("sections")
        if isinstance(secs, list):
            for s in secs:
                if isinstance(s, dict):
                    add("heading", s.get("heading") or s.get("title") or s.get("name"), level=s.get("level", 1))
                    for p in s.get("paragraphs") or ([s["text"]] if s.get("text") else []):
                        add("paragraph", p if isinstance(p, str) else p.get("text", ""))
            if blocks:
                return blocks
        paras = obj.get("paragraphs") or obj.get("segments") or obj.get("blocks")
        if isinstance(paras, list):
            for p in paras:
                if isinstance(p, str):
                    add("paragraph", p)
                elif isinstance(p, dict):
                    t = p.get("type") if p.get("type") in ("heading", "title", "caption", "paragraph", "table", "list_item", "footnote", "abstract", "reference", "formula") else "paragraph"
                    add(t, p.get("text") or p.get("content"), page=p.get("page"), level=p.get("level"))
            return blocks
        t = obj.get("text") or obj.get("body") or obj.get("content")
        if isinstance(t, str):
            return text_blocks(t, ".md")
    elif isinstance(obj, list):
        for p in obj:
            add("paragraph", p if isinstance(p, str) else (p.get("text") if isinstance(p, dict) else ""))
    return blocks


def docx_blocks(path):
    import zipfile
    from xml.etree import ElementTree as ET
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main", "m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}
    W = "{%s}" % ns["w"]
    try:
        root = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    except Exception as e:
        raise SystemExit("cannot read .docx: %s" % e)
    blocks = []

    def ptext(p):
        return "".join(t.text or "" for t in p.iter(W + "t")).strip()
    for el in root.find(W + "body"):
        if el.tag == W + "p":
            txt = ptext(el)
            if not txt:
                continue
            style = el.find("w:pPr/w:pStyle", ns)
            sv = (style.get(W + "val") if style is not None else "") or ""
            m = re.match(r"(?i)heading\s*(\d)", sv)
            typ, lvl = "paragraph", None
            if sv.lower() == "title":
                typ, lvl = "title", 0
            elif m:
                typ, lvl = "heading", int(m.group(1))
            elif re.match(r"^\s*(Figure|Fig\.|Table|FIG\.|TABLE)\s*[\dA-Z]+[.:]", txt) or sv.lower() == "caption":
                typ = "caption"
            elif el.find("w:pPr/w:numPr", ns) is not None:
                typ = "list_item"
            blocks.append({"type": typ, "text": txt, "pages": [], "page": None, "bbox": None, "block": "d%d" % len(blocks), "level": lvl, "number": None})
        elif el.tag == W + "tbl":
            rows = [[" ".join(ptext(p) for p in tc.iter(W + "p")).replace("|", "/") for tc in tr_.findall(W + "tc")] for tr_ in el.iter(W + "tr")]
            if rows:
                md = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])] + ["| " + " | ".join(r) + " |" for r in rows[1:]]
                blocks.append({"type": "table", "text": "\n".join(md), "pages": [], "page": None, "bbox": None, "block": "d%d" % len(blocks), "level": None, "number": None})
    return blocks


def text_blocks(raw, ext):
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
    blocks, para, fence = [], [], False

    def flush():
        if para:
            txt = "\n".join(para).strip()
            if txt:
                typ = "paragraph"
                if re.match(r"^\s*(\|.+\|\s*\n?)+$", txt):
                    typ = "table"
                elif re.match(r"^\s*(Figure|Fig\.|Table|FIG\.|TABLE)\s*[\dA-Z]+[.:]", txt):
                    typ = "caption"
                elif re.match(r"^\s*([-*•]|\d+[.)])\s+", txt):
                    typ = "list_item"
                blocks.append({"type": typ, "text": txt if typ == "table" else re.sub(r"\s*\n\s*", " ", txt), "pages": [], "page": None, "bbox": None, "block": "t%d" % len(blocks),
                               "level": None, "number": None})
            para.clear()
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("```"):
            flush()
            fence = not fence
            continue
        if fence:
            continue
        if s.startswith("$$") and s.endswith("$$") and len(s) > 4:
            flush()
            blocks.append({"type": "formula", "text": s, "pages": [], "page": None, "bbox": None, "block": "t%d" % len(blocks), "level": None, "number": None})
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s) or re.match(r"^\\(section|subsection|subsubsection)\*?\{(.*)\}", s)
        if m:
            flush()
            lvl = len(m.group(1)) if m.group(1).startswith("#") else {"section": 1, "subsection": 2, "subsubsection": 3}[m.group(1)]
            is_title = lvl == 1 and not any(b["type"] in ("title", "heading") for b in blocks)
            blocks.append({"type": "title" if is_title else "heading", "text": m.group(2).strip(), "pages": [], "page": None, "bbox": None, "block": "t%d" % len(blocks),
                           "level": 0 if is_title else lvl, "number": None})
            continue
        if not s:
            flush()
            continue
        if s.startswith("%") and ext == ".tex":
            continue
        para.append(line)
    flush()
    return blocks


TERMINAL = tuple(".?!:;。？！：；”\"')]")
SKIPPABLE = ("caption", "table", "footnote", "formula", "header", "footer", "margin", "figure")


def merge_continuations(blocks):
    """Re-join a paragraph cut by a figure caption, column or page break."""
    alltext = " ".join(b.get("text", "") for b in blocks)
    hyph = set(w.lower() for w in re.findall(r"[A-Za-z]+-[A-Za-z]+", alltext))
    drop, merged = set(), 0
    for i, b in enumerate(blocks):
        if i in drop or b["type"] not in ("paragraph", "list_item"):
            continue
        txt = b.get("text", "").rstrip()
        if not txt or txt.endswith(TERMINAL) or len(txt) < 15:
            continue
        j = i + 1
        while j < len(blocks) and j <= i + 6 and (j in drop or blocks[j]["type"] in SKIPPABLE):
            j += 1
        if j >= len(blocks) or j > i + 6:
            continue
        q = blocks[j]
        qt = q.get("text", "").lstrip()
        if q["type"] not in ("paragraph", "list_item") or not qt or not (qt[0].islower() or qt[0] in "(,;"):
            continue
        if txt.endswith("-") and re.search(r"[A-Za-z]-$", txt):
            m1, m2 = re.search(r"([A-Za-z]+)-$", txt), re.match(r"([A-Za-z]+)", qt)
            keep = bool(m1 and m2 and (m1.group(1) + "-" + m2.group(1)).lower() in hyph)
            joined = txt + qt if keep else txt[:-1] + qt
        else:
            joined = txt + " " + qt
        b["text"] = joined
        b["pages"] = sorted(set((b.get("pages") or []) + (q.get("pages") or [])))
        drop.add(j)
        merged += 1
    return [b for k, b in enumerate(blocks) if k not in drop], merged


# ------------------------------------------------------------------------------------------------ units, sections
NUM_HEAD = re.compile(r"^\s*((?:\d{1,2}(?:\.\d{1,2}){0,3})|(?:[A-H](?:\.\d{1,2}){0,2})|(?:[IVX]{1,5}))[.)]?\s+(.+)$")


def build_units(blocks, args):
    blocks, merged = merge_continuations(blocks)
    units, sections = [], []
    cur = {"id": "§front", "title": "(front matter)", "level": 0, "number": None, "units": [], "excluded": False, "optional": True, "parent": None}
    sections.append(cur)
    stack = []
    seq = 0
    page_filter = None
    if args.pages:
        page_filter = set()
        for part in str(args.pages).split(","):
            m = re.fullmatch(r"(\d+)-(\d+)", part.strip())
            if m:
                page_filter.update(range(int(m.group(1)), int(m.group(2)) + 1))
            elif part.strip().isdigit():
                page_filter.add(int(part))
    in_abstract = False
    last_top_number = None
    for b in blocks:
        t, text = b["type"], (b.get("text") or "").strip()
        if not text or t in ("header", "footer", "margin"):
            continue
        pgs = b.get("pages") or ([b["page"]] if b.get("page") else [])
        if page_filter and pgs and not (set(pgs) & page_filter):
            continue
        if t == "heading" and text.endswith(":") and len(text.split()) <= 4:
            t = "paragraph"  # a run-in label such as "Decoder:" is not a section
        if t == "heading":
            m = NUM_HEAD.match(text)
            number, title = (m.group(1), m.group(2).strip()) if m else (None, text)
            lvl = b.get("level") if isinstance(b.get("level"), int) and b.get("level") else ((number.count(".") + 1) if number and re.match(r"^\d", number) else 1)
            # PRL style: "V. SEARCHES" followed by "A. Generic ..." / "B. ..." - a single letter under a ROMAN top-level section is a subsection, not an appendix
            if number and re.fullmatch(r"[A-H]", number) and last_top_number and re.fullmatch(r"[IVX]+", last_top_number):
                lvl = 2
            seq += 1
            sid = "§" + (number if number else "s%d" % seq)
            if number and sid in {x["id"] for x in sections} and lvl == 2:
                sid = "§%s.%s" % (last_top_number, number)
            if any(s["id"] == sid for s in sections):
                sid += "-%d" % seq
            if lvl <= 1:
                last_top_number = number
            is_abs = bool(re.match(r"^\s*(abstract|summary|摘要)\s*$", title, re.I))
            if is_abs:
                sid = "§abs"
            while stack and stack[-1]["level"] >= lvl:
                stack.pop()
            parent = stack[-1]["id"] if stack else None
            cur = {"id": sid, "title": title, "level": lvl, "number": number, "units": [], "excluded": bool(EXCLUDED_SECTIONS.match(text)), "parent": parent,
                   "optional": bool(OPTIONAL_SECTIONS.match(text)) or is_abs or bool(number and lvl <= 1 and re.match(r"^[A-H](\.\d+)*$", number)) or bool(re.match(r"^\s*contributions\s*$", title, re.I)), "pages": []}
            if stack and (stack[-1].get("excluded") or stack[-1].get("optional")) and lvl > stack[-1]["level"]:
                cur["excluded"] = cur["excluded"] or stack[-1].get("excluded", False)
                cur["optional"] = cur["optional"] or stack[-1].get("optional", False)
            stack.append(cur)
            sections.append(cur)
            in_abstract = is_abs
            continue
        if t in ("reference", "reference_block"):
            cur_ex = True
        else:
            cur_ex = cur["excluded"]
        typ = {"abstract": "abstract", "front_matter": "front"}.get(t, t)
        if t == "abstract":
            if not any(s["id"] == "§abs" for s in sections):
                cur = {"id": "§abs", "title": "Abstract", "level": 1, "number": None, "units": [], "excluded": False, "parent": None, "optional": True, "pages": []}
                sections.append(cur)
                stack[:] = [cur]
        uid = "E%03d" % (len(units) + 1)
        sents = nlib.split_sentences(text) if typ in ("paragraph", "abstract", "list_item", "caption", "footnote", "front") else [text]
        u = {"id": uid, "type": typ, "text": text, "sentences": sents, "pages": pgs, "page": b.get("page") or (pgs[0] if pgs else None), "bbox": b.get("bbox"),
             "block": b.get("block"), "section": cur["id"], "excluded": cur_ex, "words": nlib.wcount(text)}
        units.append(u)
        cur["units"].append(uid)
    # sections' page spans and sizes
    byid = {u["id"]: u for u in units}
    for s in sections:
        pg = sorted({p for uid in s["units"] for p in byid[uid]["pages"]})
        s["pages"] = pg
        s["n_units"] = len(s["units"])
        s["words"] = sum(byid[uid]["words"] for uid in s["units"])
        s["first"], s["last"] = (s["units"][0], s["units"][-1]) if s["units"] else (None, None)
    sections = [s for s in sections if s["units"] or s["id"] != "§front"]
    # normalise heading levels: the smallest level used in the document is the top level (Markdown "##" headings, Word styles ...)
    lv = [s["level"] for s in sections if s["id"] != "§front" and s["level"] and s["level"] >= 1]
    if lv and min(lv) > 1:
        shift = min(lv) - 1
        for s in sections:
            if s["id"] != "§front" and s["level"]:
                s["level"] -= shift
    # totals including all descendants (a "Results" heading may hold no text itself but 3 subsections)
    kids = defaultdict(list)
    for s in sections:
        if s.get("parent"):
            kids[s["parent"]].append(s["id"])
    byid_s = {s["id"]: s for s in sections}

    def total(sid):
        s = byid_s[sid]
        return s["words"] + sum(total(k) for k in kids[sid] if k in byid_s)
    for s in sections:
        s["words_total"] = total(s["id"])

    def path(sid):
        s = byid_s[sid]
        return (path(s["parent"]) + " > " if s.get("parent") in byid_s else "") + s["title"]
    for s in sections:
        s["path"] = path(s["id"])
    return units, sections, merged


def compute_cues(units, sections):
    sec = {s["id"]: s for s in sections}
    cues = []
    for u in units:
        if u["excluded"] or u["type"] in ("heading", "table", "formula", "front", "title"):
            continue
        title = sec[u["section"]].get("path") or sec[u["section"]]["title"]
        for i, s in enumerate(u["sentences"], 1):
            kinds = nlib.classify_sentence(s, title)
            if u["type"] in ("caption", "footnote"):
                kinds = [k for k in kinds if k == "result"]
            if not kinds:
                continue
            score = {}
            for k in kinds:
                sc = len(nlib.CUES[k].findall(s))
                if k == "limitation":
                    sc += 1.5 if nlib.LIMIT_SECTIONS.search(title) else 0
                    sc += 1 if re.search(r"\b(limitation|assum|future work|cannot|fail)", s, re.I) else 0
                if k == "result":
                    sc += 1 if re.search(r"\b(results?|experiments?|evaluation|performance)\b", title, re.I) else 0
                score[k] = sc
            cues.append({"unit": u["id"], "sent": i, "kinds": kinds, "score": score, "text": s})
    return cues


# ------------------------------------------------------------------------------------------------ anchors
ANCHOR_RE = re.compile(r"E(\d{3,})(?:\.(\d+)(?:-(\d+))?)?")


def parse_anchors(spec):
    """'E012, E014.2, E020-E022, E031.1-3' -> list of (unit_id, sent_from, sent_to) ; sentence None = whole unit."""
    out, bad = [], []
    spec = spec or ""
    for part in re.split(r"[,;\s]+", spec.strip()):
        if not part:
            continue
        m = re.fullmatch(r"E(\d{3,})-E?(\d{3,})", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < b - a <= 60:
                out += [("E%03d" % n, None, None) for n in range(a, b + 1)]
                continue
        m = ANCHOR_RE.fullmatch(part)
        if m:
            out.append(("E%03d" % int(m.group(1)), int(m.group(2)) if m.group(2) else None, int(m.group(3)) if m.group(3) else (int(m.group(2)) if m.group(2) else None)))
        else:
            bad.append(part)
    return out, bad


def anchor_text(units_by_id, anchors):
    txt, texts = [], []
    for uid, a, b in anchors:
        u = units_by_id.get(uid)
        if not u:
            continue
        if a:
            ss = u["sentences"][a - 1:b]
            texts.append(" ".join(ss))
        else:
            texts.append(u["text"])
    return " ".join(texts), texts


def fmt_anchor(units_by_id, uid, a=None, b=None):
    u = units_by_id[uid]
    pg = ",".join(str(p) for p in u["pages"]) or "-"
    return "%s%s · p%s · %s" % (uid, ".%d%s" % (a, "-%d" % b if b and b != a else "") if a else "", pg, u["section"])


# ------------------------------------------------------------------------------------------------ state
def load_all(work):
    d = jload(os.path.join(work, "units.json"))
    if d is None:
        raise SystemExit("no units.json in %s: run `prepare` first" % work)
    notes = jload(os.path.join(work, "notes.json"), {})
    return d, notes


def sec_of(d):
    return {s["id"]: s for s in d["sections"]}


def build_index(d):
    docs = []
    secs = sec_of(d)
    for u in d["units"]:
        docs.append(secs[u["section"]]["title"] + " " + u["text"])
    return nlib.BM25(docs)


def in_section(d, sec_id, uid):
    secs = sec_of(d)
    u = next((x for x in d["units"] if x["id"] == uid), None)
    if not u:
        return False
    cur = u["section"]
    while cur:
        if cur == sec_id:
            return True
        cur = (secs.get(cur) or {}).get("parent")
    return False


