#!/usr/bin/env python3
"""srcmeta.py - source metadata and reference list of a paper, with the origin of every value.

Nothing is invented: a field is filled only from the file itself (PDF info dictionary, front matter, headers/footers, arXiv stamp, DOI strings) or,
if you ask for it (`meta --crossref`), from the Crossref REST API; every field says where it came from and how much to trust it. Fields that cannot
be found are listed in `missing` so the export says "unknown" instead of a plausible guess.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>\[\]{}|\\^`]+)", re.I)
ARXIV_RE = re.compile(r"arXiv:\s?(\d{4}\.\d{4,5})(v\d+)?(?:\s*\[([\w.-]+)\])?(?:\s+(\d{1,2}\s+[A-Z][a-z]{2}\s+((?:19|20)\d{2})))?")
ARXIV_OLD = re.compile(r"arXiv:\s?([a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?", re.I)
YEAR_CTX = re.compile(r"(?:published|accepted|received|available online|online|copyright|©|\(c\)|issued|date)\D{0,30}((?:19|20)\d{2})", re.I)
VENUE_RE = re.compile(r"((?:(?:IEEE|ACM|SIAM|AIP|APS|European|American|International|British|Royal|Annual|Chemical|Applied|Proceedings\s+of\s+the|Transactions\s+on)\s+){0,2}(?:Journal|Proceedings|Transactions|Letters|Reviews?|Annals|Conference|Symposium|Workshop|Bulletin|Communications)\b(?:\s+(?:of|on|in|for|the|and|&|[A-Z][\w&'’-]*)){1,8}"
                      r"|Nature(?:\s+[A-Z][a-z]+){0,3}|Science(?:\s+[A-Z][a-z]+){0,2}|Cell(?:\s+[A-Z][a-z]+){0,2}|PNAS|PLoS\s+[A-Z][a-z]+|Physical\s+Review\s+[A-Z]\w*|arXiv(?:\s+preprint)?|bioRxiv|medRxiv|"
                      r"\d+(?:st|nd|rd|th)\s+Conference\s+on\s+[^\n(]{5,70})(?:\s*[,(]\s*((?:19|20)\d{2}))?")
VERSION_LABEL = re.compile(r"\b(version of record|accepted manuscript|author(?:'s)? (?:accepted )?manuscript|preprint|pre-print|peer[- ]reviewed|under review|camera[- ]ready|early access|corrected proof)\b", re.I)
JUNK_TITLE = re.compile(r"^(untitled|microsoft word|document\d*|slide \d+|\S+\.(?:pdf|docx?|tex|dvi)|powerpoint)", re.I)
ORCID_RE = re.compile(r"\b(\d{4}-\d{4}-\d{4}-\d{3}[\dX])\b")
NOT_AUTHOR = re.compile(r"@|\b(universit|institut|department|school|college|laborator|corresponding|abstract|keywords?|received|accepted|published|doi|arxiv|copyright|licen[cs]e|google|microsoft|openai|deepmind|inc\.|ltd|gmbh|center|centre|faculty|academy|hospital)\b", re.I)
NAME_TOKEN = re.compile(r"^[A-ZÀ-ÝĀ-Ž][A-Za-zÀ-ÿĀ-ž'’.-]+$")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_doi(s):
    return re.sub(r"[.,;:)\]]+$", "", s).rstrip(".")


def fld(value, origin, conf, anchor=None, note=None):
    d = {"value": value, "origin": origin, "confidence": conf}
    if anchor:
        d["anchor"] = anchor
    if note:
        d["note"] = note
    return d


def split_names(line):
    """'Ashish Vaswani, Noam Shazeer, and Jakob Uszkoreit' -> list of names or []"""
    line = re.sub(r"[\d*†‡§¶∗#]+(?=[,\s]|$)", "", line).strip()
    line = re.sub(r"\band\b|&", ",", line)
    parts = [p.strip(" ,;") for p in re.split(r"[,;]", line) if p.strip(" ,;")]
    names = []
    for p in parts:
        toks = p.split()
        if 2 <= len(toks) <= 5 and all(NAME_TOKEN.match(t) or t.lower() in ("van", "von", "de", "der", "da", "di", "le", "la", "bin", "al", "el", "du") for t in toks):
            names.append(p)
        else:
            return []
    return names if 1 <= len(names) <= 40 else []


def extract(path, blocks, units, meta):
    """-> dict of source metadata fields (each {value, origin, confidence}) + missing list"""
    out = {}
    pdfmeta = meta.get("pdf_metadata") or {}
    first = [b for b in blocks if (b.get("pages") or [b.get("page") or 1])[0] <= 2]
    head_texts = [(b.get("text") or "").strip() for b in first if (b.get("text") or "").strip()]
    head = "\n".join(head_texts)
    first_ids = {u["id"] for u in units[:6]}
    u_front = [u for u in units if (u["type"] in ("title", "front", "abstract", "heading") or u["id"] in first_ids) and (u["pages"] or [1])[0] <= 2]
    file_info = {"file_name": os.path.basename(path), "format": meta.get("format"), "pages": meta.get("pages")}
    if os.path.isfile(path):
        file_info["sha256"] = sha256_file(path)
        file_info["bytes"] = os.path.getsize(path)
    out["file"] = file_info
    # ---- DOI (first two pages; most frequent wins)
    dois = [clean_doi(m) for m in DOI_RE.findall(head)]
    for k in ("doi", "subject", "keywords", "title"):
        v = str(pdfmeta.get(k) or "")
        dois += [clean_doi(m) for m in DOI_RE.findall(v)]
    if dois:
        doi, n = Counter(x.lower() for x in dois).most_common(1)[0]
        out["doi"] = fld(doi, "front-matter/header text", "high" if n > 1 or re.search(r"\bdoi\b", head, re.I) else "medium")
    # ---- arXiv
    m = ARXIV_RE.search(head)
    if m:
        out["arxiv_id"] = fld(m.group(1), "arXiv stamp on page 1", "high")
        if m.group(2):
            out["version"] = fld(m.group(2), "arXiv stamp on page 1", "high")
        if m.group(3):
            out["subject_class"] = fld(m.group(3), "arXiv stamp on page 1", "high")
        yy, mm_ = int(m.group(1)[:2]), int(m.group(1)[2:4])
        if 1 <= mm_ <= 12:
            out["year"] = fld(2000 + yy, "arXiv identifier %s (first submitted %d-%02d)" % (m.group(1), 2000 + yy, mm_), "medium", note="year of the first arXiv version; the published venue year may differ")
        if m.group(4):
            out["version_date"] = fld(m.group(4), "arXiv stamp on page 1", "high", note="date of the arXiv version in the file")
    else:
        m = ARXIV_OLD.search(head)
        if m:
            out["arxiv_id"] = fld(m.group(1), "arXiv stamp on page 1", "high")
            if m.group(2):
                out["version"] = fld(m.group(2), "arXiv stamp on page 1", "high")
    # ---- title
    t_unit = next((u for u in units if u["type"] == "title" and len(re.findall(r"[A-Za-z]{2,}", u["text"])) >= 2 and len(u["text"]) >= 8), None)  # OCR can label a stamp ("201") as the title
    if t_unit:
        out["title"] = fld(re.sub(r"\s+", " ", t_unit["text"]).strip(), "title block" + (" on page %s" % t_unit["page"] if t_unit["page"] else ""), "high", anchor=t_unit["id"])
    elif pdfmeta.get("title") and not JUNK_TITLE.match(str(pdfmeta["title"]).strip()) and len(str(pdfmeta["title"])) > 8:
        out["title"] = fld(str(pdfmeta["title"]).strip(), "PDF info dictionary", "medium", note="embedded metadata can be stale: compare with the first page")
    else:
        cand = next((u for u in u_front if u["type"] in ("front", "heading") and 15 <= len(u["text"]) <= 250 and not NOT_AUTHOR.search(u["text"])), None)
        if cand:
            t_unit = cand
            out["title"] = fld(cand["text"], "first heading/front line of the document", "low", anchor=cand["id"], note="no title block was recognised; verify")
    # ---- authors
    authors = None
    t_idx = next((i for i, u in enumerate(units) if t_unit and u["id"] == t_unit["id"]), -1)
    names, first_anchor, collab = [], None, None
    tpage = (t_unit or {}).get("page") or 1
    for u in (units[t_idx + 1:t_idx + 70] if t_idx >= 0 else units[:30]):
        if u["type"] == "abstract" or re.match(r"^\s*abstract\b", u["text"], re.I) or u["type"] == "heading" or (u.get("page") or 1) > tpage:
            break
        txt = u["text"].strip()
        cm = re.match(r"^\(?\s*((?:[A-Z][\w-]*\s+){0,5}(?:Collaboration|Consortium|Group|Team))\b[^)]*\)?\s*$", txt)
        if cm and not NOT_AUTHOR.search(txt.replace("Collaboration", "")) or (cm and re.match(r"^\(", txt)):
            collab = re.sub(r"^\(|\)$", "", txt).strip()
            continue
        m_al = re.match(r"^((?:[A-Z]\.\s*)+[A-Z][\w'’-]+)\s+et\s+al\.?[*†‡\d]*$", txt)
        if m_al:
            names.append(m_al.group(1) + " et al.")
            first_anchor = first_anchor or u["id"]
            continue
        if NOT_AUTHOR.search(txt):
            toks = txt.split()
            lead = []
            for tk in toks:
                if NOT_AUTHOR.search(tk) or "@" in tk:
                    break
                lead.append(tk)
            got = split_names(" ".join(lead)) if 2 <= len(lead) <= 3 and len(toks) <= 8 else []
        else:
            got = []
            for line in re.split(r"\n+", txt):
                got += split_names(line)
        if got:
            names += [n for n in got if n not in names]
            first_anchor = first_anchor or u["id"]
    if names and collab:
        names.append("(" + collab + ")")
    if names:
        authors = fld(names[:60], "front matter of page 1", "medium", anchor=first_anchor, note="author order as printed; affiliations and e-mail addresses are not exported")
    if not authors and pdfmeta.get("author"):
        nm = [x.strip() for x in re.split(r"[;,]|\band\b", str(pdfmeta["author"])) if x.strip()]
        if nm:
            authors = fld(nm, "PDF info dictionary", "low", note="embedded metadata; may be the typesetting user, verify against the first page")
    if authors:
        out["authors"] = authors
    # ---- year
    if "year" not in out:
        ym = YEAR_CTX.search(head)
        if ym:
            out["year"] = fld(int(ym.group(1)), "dated line on page 1-2 ('%s')" % re.sub(r"\s+", " ", ym.group(0))[:60], "medium")
        else:
            cd = str(pdfmeta.get("creationDate") or pdfmeta.get("creation_date") or "")
            mm = re.search(r"((?:19|20)\d{2})", cd)
            yrs = [int(y) for y in re.findall(r"\b((?:19|20)\d{2})\b", "\n".join(u["text"] for u in u_front))]
            if yrs:
                out["year"] = fld(Counter(yrs).most_common(1)[0][0], "most frequent year in the front matter", "low", note="no dated line found; verify")
            elif mm:
                out["year"] = fld(int(mm.group(1)), "PDF creation date", "low", note="file creation date, not necessarily publication year")
    # ---- venue
    jr = re.search(r"\b((?:[A-Z]{2,5}|(?:Phys\.?|Proc\.?|Nucl\.?|J\.?|Astrophys\.?|Appl\.?|Mon\.?)\s?[A-Z][\w.]*(?:\s[A-Z][\w.]*){0,2})\s+\d{1,4},\s*\d{3,7}\s*\((?:19|20)\d{2}\))", head)
    ven = VENUE_RE.search(head)
    if jr:
        out["venue"] = fld(re.sub(r"\s+", " ", jr.group(1)), "journal reference line in the page header", "medium", note="abbreviated journal, volume, article number, year as printed")
    elif ven:
        out["venue"] = fld(re.sub(r"\s+", " ", ven.group(1)).strip(" ,.;"), "header/footer/front text of page 1-2", "low", note="verbatim line fragment; verify")
        if ven.group(2) and "year" not in out:
            out["year"] = fld(int(ven.group(2)), "venue line ('%s')" % re.sub(r"\s+", " ", ven.group(0))[:60], "medium")
    # ---- version label, identifiers
    vl = VERSION_LABEL.search(head)
    if vl:
        out["version_label"] = fld(vl.group(1).lower(), "page 1-2 text", "medium")
    org = sorted(set(ORCID_RE.findall(head)))
    if org:
        out["orcids"] = fld(org, "front matter", "medium", note="order does not imply which author")
    pm = re.search(r"\bPMID:?\s*(\d{4,9})\b", head)
    if pm:
        out["pmid"] = fld(pm.group(1), "front matter", "high")
    iss = re.search(r"\bISSN:?\s*(\d{4}-\d{3}[\dX])\b", head)
    if iss:
        out["issn"] = fld(iss.group(1), "front matter", "high")
    # ---- keywords
    kw = re.search(r"(?im)^\s*(?:key\s*words?|index terms)\s*[:—-]\s*(.+)$", head)
    if kw:
        out["keywords"] = fld([x.strip() for x in re.split(r"[;,·•]", kw.group(1)) if x.strip()][:15], "front matter", "medium")
    out["missing"] = [k for k in ("title", "authors", "year", "doi", "venue") if k not in out and not (k == "doi" and "arxiv_id" in out)]
    return out


# ------------------------------------------------------------------------------------------------ references
REF_SPLIT = re.compile(r"(?:(?<=\s)|^)\[(\d{1,3})\]\s+")
REF_SPLIT2 = re.compile(r"(?m)^\s*(\d{1,3})[.)]\s+(?=[A-Z])")


def parse_references(units):
    """units flagged excluded that belong to a reference list -> [{n, text, doi, year, first_author}]"""
    texts = [u["text"] for u in units if u["excluded"] and u["type"] in ("reference", "paragraph", "list_item", "front")]
    if not texts:
        return []
    blob = "\n".join(texts)
    entries = []
    parts = REF_SPLIT.split(blob)
    if len(parts) >= 5:
        for i in range(1, len(parts) - 1, 2):
            entries.append((int(parts[i]), parts[i + 1]))
    else:
        parts = REF_SPLIT2.split(blob)
        if len(parts) >= 5:
            for i in range(1, len(parts) - 1, 2):
                entries.append((int(parts[i]), parts[i + 1]))
        else:
            entries = [(i + 1, t) for i, t in enumerate(texts) if len(t) > 25]
    out = []
    for n, t in entries:
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) < 15:
            continue
        doi = DOI_RE.search(t)
        yr = re.findall(r"\b((?:19|20)\d{2})[a-z]?\b", t)
        fa = re.match(r"\s*([A-Z][A-Za-zÀ-ÿ'’-]+)", t)
        out.append({"n": n, "text": t[:400], "doi": clean_doi(doi.group(1)).lower() if doi else None, "year": int(yr[0]) if yr else None, "first_author": fa.group(1) if fa else None})
    return out


def expand_nums(s):
    nums = []
    for part in re.split(r"[,;]", s):
        m = re.fullmatch(r"\s*(\d+)\s*[-–]\s*(\d+)\s*", part)
        if m and 0 < int(m.group(2)) - int(m.group(1)) <= 30:
            nums += list(range(int(m.group(1)), int(m.group(2)) + 1))
        elif part.strip().isdigit():
            nums.append(int(part))
    return nums


def resolve_citations(sentence, refs, cite_num_re, cite_author_re):
    """-> [{marker, ref_n, ref_text, doi}] for the citations found in one sentence"""
    byn = {r["n"]: r for r in refs}
    found = []
    for m in cite_num_re.finditer(sentence):
        grp = next((g for g in m.groups() if g), None)
        for n in expand_nums(grp or ""):
            r = byn.get(n)
            found.append({"marker": m.group(0).strip(), "ref_n": n, "ref_text": (r or {}).get("text"), "doi": (r or {}).get("doi")})
    for m in cite_author_re.finditer(sentence):
        sur, yr = m.group(1), m.group(2)[:4]
        r = next((x for x in refs if x.get("first_author") == sur and str(x.get("year")) == yr), None)
        if r or re.search(r"et\s+al|\(\s*" + yr, m.group(0)):
            found.append({"marker": m.group(0).strip(" ("), "ref_n": r["n"] if r else None, "ref_text": r["text"] if r else None, "doi": r["doi"] if r else None})
    return found


# ------------------------------------------------------------------------------------------------ optional Crossref lookup
def crossref(doi, timeout=8):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/")
    req = urllib.request.Request(url, headers={"User-Agent": "np-claim-builder/1.0 (open-source research tool)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            msg = json.loads(r.read().decode("utf-8"))["message"]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        return {"error": "%s: %s" % (type(e).__name__, str(e)[:100])}
    issued = (msg.get("issued") or {}).get("date-parts") or [[None]]
    return {"title": (msg.get("title") or [None])[0], "authors": ["%s %s" % (a.get("given", ""), a.get("family", "")) if a.get("family") else a.get("name", "") for a in msg.get("author", [])],
            "year": issued[0][0], "venue": (msg.get("container-title") or [None])[0], "publisher": msg.get("publisher"), "type": msg.get("type"), "url": msg.get("URL"),
            "volume": msg.get("volume"), "issue": msg.get("issue"), "pages": msg.get("page")}
