#!/usr/bin/env python3
"""npb.py - nanopublication claim builder.

You read the paper and decide what its key claims are; this tool makes each claim checkable and exportable: it cuts the paper into addressable
evidence units (E012, sentences E012.3, page, bbox), helps to decompose sentences into atomic subject - relation - object claims, VERIFIES every
claim when it is submitted (verbatim quote + exact offsets, numbers, subject/object in the evidence, relation direction, atomicity, dropped scope,
hedge/negation, attribution to this paper or a cited work, minimal evidence, duplicates), records source metadata with the origin of each value,
and exports nanopublications (TriG: head / assertion / provenance / publicationInfo), JSON, JSONL and CSV, validated against the nanopublication
well-formedness rules.

  npb.py prepare [INPUT] --work W [--case /input/case.json] [--pages 1-8] [--ocr auto|off|force] [--lang auto]
  npb.py outline W | read W --sec 3 / --ids E010-E020 / --page 2 [--sentences] | find W "query"
  npb.py candidates W [--top 25]        sentences that look like key conclusions (not yet covered by a claim)
  npb.py atoms W E104.2 | --sec 4       decomposition hints: clauses, relation verbs, entities, scope, numbers, hedges, citations
  npb.py meta W [--crossref] [--set title=...]      source metadata with origin per field
  npb.py ingest W [FILE|-]              claim blocks / JSONL; each claim is verified at once
  npb.py next W | check W               what is missing or failing
  npb.py merge W C1 C2 | drop W C1 ...
  npb.py assemble W [W2 ...] --out OUT [--case ...] [--base IRI] [--answers answers.json]
  npb.py validate FILE.trig|nanopubs.json
  npb.py search OUT "query" | status W
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import claims as C  # noqa: E402
import export as X  # noqa: E402
import nlib  # noqa: E402
import srcmeta  # noqa: E402
import units as U  # noqa: E402
import vocab  # noqa: E402

VERSION = "1.0.0"
SCHEMA = "np-claim-builder/1"
jload, jsave, find_key = U.jload, U.jsave, U.find_key


# ------------------------------------------------------------------------------------------------ state
def load(work):
    d = jload(os.path.join(work, "units.json"))
    if d is None:
        raise SystemExit("no units.json in %s: run `prepare` first" % work)
    return d, jload(os.path.join(work, "claims.json"), {})


def index(d):
    return U.build_index(d)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------------------------------------ prepare
def discover_input(a):
    case = jload(a.case) if a.case and os.path.isfile(a.case) else None
    if a.input and os.path.isfile(a.input):
        return a.input, case
    cand = []
    if case:
        for k in ("file", "path", "paper", "pdf", "input_file", "material", "document", "source_file"):
            v = find_key(case, [k])
            if isinstance(v, str):
                cand.append(v)
            elif isinstance(v, list):
                cand += [x for x in v if isinstance(x, str)]
    base = os.path.dirname(os.path.abspath(a.case)) if a.case else "/input"
    for v in cand:
        for p in (v, os.path.join(base, v), os.path.join("/input", v), os.path.join("/input", os.path.basename(v))):
            if os.path.isfile(p):
                return p, case
    def scan(exts):
        found = []
        for root in dict.fromkeys((base, "/input")):
            if os.path.isdir(root):
                found += [os.path.join(root, f) for f in sorted(os.listdir(root)) if f.lower().endswith(exts) and f.lower() not in ("task.md", "readme.md", "case.json")]
        return found
    strong = scan((".pdf", ".docx", ".tex", ".html", ".htm"))
    if strong:
        if len(strong) > 1:
            print("NOTE: several candidate input files found (%s): using the first; run prepare once per paper with an explicit path if the task means another" % ", ".join(os.path.basename(x) for x in strong[:5]))
        return strong[0], case
    txt = find_key(case, ["paragraph", "passage", "text", "excerpt", "input_text", "content"]) if case else None
    if isinstance(txt, str) and len(txt) > 40:
        os.makedirs(a.work, exist_ok=True)
        p = os.path.join(a.work, "case_text.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(txt)
        return p, case
    weak = scan((".md", ".txt"))
    if weak:
        return weak[0], case
    raise SystemExit("no input file found: pass INPUT, or --case with a file path / text field (looked in %s and /input)" % base)


def cmd_prepare(a):
    os.makedirs(a.work, exist_ok=True)
    path, case = discover_input(a)
    blocks, meta = U.load_source(path, a.work, a)
    units, sections, merged = U.build_units(blocks, a)
    if not units:
        raise SystemExit("no readable text found in the input")
    body = " ".join(u["text"] for u in units if u["type"] in ("paragraph", "abstract"))
    lang = a.lang if a.lang != "auto" else nlib.detect_lang(body)
    cues = U.compute_cues(units, sections)
    source = srcmeta.extract(path, blocks, units, meta)
    refs = srcmeta.parse_references(units)
    meta.update({"lang": lang, "n_units": len(units), "n_sections": len(sections), "continuations_merged": merged, "version": VERSION, "input_path": path,
                 "task": (find_key(case, ["task", "instruction", "prompt", "question", "description"]) if case else None)})
    jsave(os.path.join(a.work, "units.json"), {"meta": meta, "units": units, "sections": sections, "cues": cues, "source": source, "refs": refs})
    if not os.path.isfile(os.path.join(a.work, "claims.json")):
        jsave(os.path.join(a.work, "claims.json"), {})
    nuse = [u for u in units if not u["excluded"]]
    print(json.dumps({"ok": True, "work": a.work, "file": meta["file"], "format": meta["format"], "lang": lang, "pages": meta.get("pages"), "units": len(units), "citable_units": len(nuse),
                      "sections": len(sections), "words": sum(u["words"] for u in nuse), "references_parsed": len(refs), "parser_status": meta.get("parser_status"),
                      "source_found": {k: (v["value"] if isinstance(v.get("value"), (str, int)) else "ok") for k, v in source.items() if isinstance(v, dict) and "value" in v}, "source_missing": source["missing"]}, ensure_ascii=False))
    for w in meta.get("parser_warnings", [])[:3]:
        print("WARNING (parser): " + w)
    if meta.get("unparsed"):
        print("WARNING: parts of the file could not be read (%s): report them as not processed." % json.dumps(meta["unparsed"][:3]))
    if meta.get("task"):
        print("TASK (from the case file): " + str(meta["task"])[:600])
    print("Next: `outline`, `candidates` (key-conclusion sentences), `atoms W E104.2` (decomposition hints), then write claims and `ingest` them.")


# ------------------------------------------------------------------------------------------------ reading
def cmd_outline(a):
    d, _ = load(a.work)
    per = defaultdict(Counter)
    byu = {u["id"]: u for u in d["units"]}
    for c in d["cues"]:
        for k in c["kinds"]:
            per[byu[c["unit"]]["section"]][k] += 1
    print("OUTLINE of %s (%s, %d citable units)" % (d["meta"]["file"], d["meta"]["lang"], sum(1 for u in d["units"] if not u["excluded"])))
    for s in d["sections"]:
        ind = "  " * max(0, (s["level"] or 1) - 1)
        flags = " [excluded]" if s["excluded"] else (" [optional]" if s["optional"] else "")
        cu = " ".join("%s:%d" % (k[:3], n) for k, n in per[s["id"]].most_common(3))
        print("%s%s %s | p%s | %s..%s | %d words%s%s" % (ind, s["id"], s["title"][:50], ",".join(map(str, s["pages"][:3])) or "-", s["first"], s["last"], s["words"], flags, ("  cues: " + cu) if cu else ""))


def cmd_read(a):
    d, _ = load(a.work)
    units = d["units"]
    if a.sec:
        sid = a.sec if a.sec.startswith("§") else "§" + a.sec
        sel = [u for u in units if U.in_section(d, sid, u["id"])]
        if not sel:
            raise SystemExit("no such section: %s (see `outline`)" % sid)
    elif a.ids:
        want = {x[0] for x in U.parse_anchors(a.ids)[0]}
        sel = [u for u in units if u["id"] in want]
    elif a.page:
        sel = [u for u in units if a.page in u["pages"]]
    else:
        sel = units
    sel = [u for u in sel if not u["excluded"] or a.ids]
    out, used = [], 0
    for u in sel:
        if used and used + u["words"] > a.max_words:
            break
        out.append(u)
        used += u["words"]
    secs = U.sec_of(d)
    last = None
    for u in out:
        if u["section"] != last:
            s = secs[u["section"]]
            print("\n## %s %s (p%s)" % (s["id"], s["title"], ",".join(map(str, s["pages"][:3])) or "-"))
            last = u["section"]
        pg = ",".join(map(str, u["pages"])) or "-"
        if a.sentences and len(u["sentences"]) > 1:
            print("%s [%s p%s]" % (u["id"], u["type"], pg))
            for i, s in enumerate(u["sentences"], 1):
                print("  %s.%d %s" % (u["id"], i, s))
        else:
            print("%s [%s p%s] %s" % (u["id"], u["type"], pg, u["text"]))
    if len(out) < len(sel):
        print("\n... %d more unit(s): continue with --ids %s-%s" % (len(sel) - len(out), sel[len(out)]["id"], sel[-1]["id"]))


def cmd_find(a):
    d, _ = load(a.work)
    bm = index(d)
    for i, sc in bm.top(a.query, a.k):
        u = d["units"][i]
        if not u["excluded"]:
            print("%s [p%s %s] (%.1f) %s" % (u["id"], ",".join(map(str, u["pages"])) or "-", u["section"], sc, u["text"][:240].replace("\n", " ")))


# ------------------------------------------------------------------------------------------------ candidates and atom hints
KEY_SECTION = re.compile(r"abstract|result|conclusion|discussion|finding|summary|experiment|evaluation|analysis|contribution", re.I)
ENTITY_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9α-ω]*(?:[-/][A-Za-z0-9α-ω]+)*(?:\s+(?:of|the|and|for|in)\s+)?(?:\s+[A-Z][A-Za-z0-9α-ω-]*){0,4}|[a-z]+-[a-z]+(?:-[a-z]+)?(?=\s)|[A-Za-z]+\d+[A-Za-z0-9-]*|[A-Z]{2,}[a-z0-9-]*)\b")
CLAUSE_SPLIT = re.compile(r"\s*(?:;|,\s*(?:while|whereas|but|although|though|and\s+(?=(?:we|it|they|the|this|these|those|both)\b)|which|where|whereby|so\s+that|because|since|thus|therefore|hence)\b|\s+(?:because|whereas|while|although)\s+)\s*", re.I)


def sentence_score(u, i, s, secs):
    kinds = nlib.classify_sentence(s, secs[u["section"]].get("path", ""))
    sc = 0.0
    sc += 1.5 * ("result" in kinds) + 1.0 * ("contribution" in kinds) + 0.4 * len(re.findall(r"\d", s) and [1])
    sc += 1.0 if KEY_SECTION.search(secs[u["section"]].get("path", "") or "") else 0
    sc += 0.7 if u["type"] == "abstract" else 0
    if re.search(r"\b(observ|detect|measur|demonstrat|reveal|show(?:s|ed|n)?|find|found|confirm|establish|estimat|infer|consistent with|first direct|identif|achiev|obtain|report)", s, re.I) and re.search(r"\d|first|new|significant", s):
        sc += 1.0
    if not vocab.SELF.search(s) and srcmeta.resolve_citations(s, [], vocab.CITE_NUM, vocab.CITE_AUTHOR):
        sc -= 1.2
    if re.search(r"\b(introduction|background|related)\b", secs[u["section"]].get("path", "") or "", re.I):
        sc -= 0.8
    sc -= 1.0 if "limitation" in kinds and "result" not in kinds else 0
    sc -= 1.2 if "setting" in kinds and not re.search(r"outperform|better|worse|higher|lower|improv|achiev|surpass|than|reduc|increas|decreas|drops?|hurts?", s, re.I) else 0
    sc -= 3 if (u["type"] == "footnote" or (u["type"] == "front" and u["section"] == "§front")) else 0
    if nlib.wcount(s) < 6:
        sc -= 2
    return sc, kinds


def restated(d, claimsd, s):
    """a sentence is 'covered' when an accepted claim restates it (>= 60% of its content words occur in the claim text + conditions)"""
    sw = nlib.content_words(s)
    if len(sw) < 4:
        return False
    for c in claimsd.values():
        if c.get("status_check") == "error":
            continue
        cw = nlib.content_words(" ".join((c.get("text", ""), c.get("cond", ""), c.get("s", ""), c.get("o", ""))))
        if len(sw & cw) / len(sw) >= 0.6:
            return True
    return False


def cmd_candidates(a):
    d, claimsd = load(a.work)
    secs = U.sec_of(d)
    covered = set()
    for c in claimsd.values():
        if c.get("status_check") != "error":
            for uid, s1, s2 in U.parse_anchors(c.get("ev", ""))[0]:
                if s1:
                    covered.update((uid, k) for k in range(s1, (s2 or s1) + 1))
                else:
                    covered.update((uid, k) for k in range(1, len(next(u for u in d["units"] if u["id"] == uid)["sentences"]) + 1))
    rows = []
    for u in d["units"]:
        if u["excluded"] or u["type"] in ("heading", "table", "formula", "title") or (u["type"] == "front" and u["section"] == "§front"):
            continue
        for i, s in enumerate(u["sentences"], 1):
            sc, kinds = sentence_score(u, i, s, secs)
            if sc >= (a.min_score if a.min_score is not None else 1.5) and (u["id"], i) not in covered and not restated(d, claimsd, s):
                rows.append((sc, u, i, s, kinds))
    rows.sort(key=lambda r: -r[0])
    print("%d candidate key-conclusion sentences not yet covered by a claim (top %d; hints, not truth):" % (len(rows), a.top))
    for sc, u, i, s, kinds in rows[:a.top]:
        cites = srcmeta.resolve_citations(s, d.get("refs", []), vocab.CITE_NUM, vocab.CITE_AUTHOR)
        print("  %s.%d [p%s %s %.1f %s%s] %s" % (u["id"], i, ",".join(map(str, u["pages"])) or "-", u["section"], sc, "/".join(kinds) or "-", " cites:" + ",".join(x["marker"] for x in cites[:2]) if cites else "", s[:230]))


def clause_split(s):
    parts = [p.strip(" ,;") for p in CLAUSE_SPLIT.split(s) if p and p.strip(" ,;")]
    return parts if len(parts) > 1 else []


def sentence_hints(d, u, i, s):
    h = {"id": "%s.%d" % (u["id"], i), "page": u["page"], "section": u["section"], "text": s}
    h["clauses"] = clause_split(s)
    rels = []
    for term, rx in vocab.REL_PATTERNS.items():
        m = rx.search(s)
        if m and term not in ("has_value", "is_a"):
            rels.append("%s ('%s')" % (term, m.group(0)))
    h["relations"] = rels[:6]
    ents = []
    for m in ENTITY_RE.finditer(s):
        t = re.sub(r"^(?:On|In|At|For|The|Of|And|By|With|From|To|A|An)\s+(?:the\s+)?", "", m.group(0).strip()).strip()
        if "-of-the-" in t or t.lower() in ("of-the-art", "state-of-the-art"):
            continue
        if len(t) > 2 and t.lower() not in ("the", "this", "that", "these", "those", "we", "our", "in", "for", "and", "however", "also", "here", "such", "while", "when", "figure", "table"):
            if m.start() == 0 and len(t.split()) == 1 and t[0].isupper() and not re.search(r"[A-Z]{2}|\d", t):
                continue
            ents.append(t)
    h["entities"] = list(dict.fromkeys(ents))[:10]
    h["scope"] = [m.group(0).strip()[:70] for m in vocab.SCOPE.finditer(s)][:4]
    h["numbers"] = nlib.numbers_ev(s)[:8]
    hed = vocab.HEDGE_WORD.search(s) or nlib.HEDGE.search(s)
    h["hedge"] = hed.group(0) if hed else None
    neg = nlib.NEGATION.search(s)
    h["negation"] = neg.group(0) if neg else None
    cites = srcmeta.resolve_citations(s, d.get("refs", []), vocab.CITE_NUM, vocab.CITE_AUTHOR)
    h["citations"] = [{"marker": x["marker"], "ref": (x["ref_text"] or "")[:90]} for x in cites[:3]]
    h["origin_guess"] = "cited" if (cites and not vocab.SELF.search(s)) else ("background" if vocab.BACKGROUND.search(s) and not vocab.SELF.search(s) else "this_paper")
    h["universal"] = [m.group(0) for m in vocab.UNIVERSAL.finditer(s)][:3]
    return h


def cmd_atoms(a):
    d, _ = load(a.work)
    byu = {u["id"]: u for u in d["units"]}
    targets = []
    if a.sec:
        sid = a.sec if a.sec.startswith("§") else "§" + a.sec
        for u in d["units"]:
            if U.in_section(d, sid, u["id"]) and not u["excluded"] and u["type"] in ("paragraph", "abstract", "list_item", "caption"):
                targets += [(u, i, s) for i, s in enumerate(u["sentences"], 1)]
    else:
        for tok in a.anchors:
            anchors, bad = U.parse_anchors(tok)
            for uid, s1, s2 in anchors:
                u = byu.get(uid)
                if not u:
                    raise SystemExit("unknown unit " + uid)
                rng = range(s1, (s2 or s1) + 1) if s1 else range(1, len(u["sentences"]) + 1)
                targets += [(u, i, u["sentences"][i - 1]) for i in rng if i <= len(u["sentences"])]
    for u, i, s in targets[:a.max]:
        h = sentence_hints(d, u, i, s)
        print("%s [p%s %s] %s" % (h["id"], h["page"] if h["page"] is not None else "-", h["section"], s))
        if h["clauses"]:
            print("    clauses (split candidates): " + " || ".join(c[:90] for c in h["clauses"]))
        if h["relations"]:
            print("    relation verbs: " + "; ".join(h["relations"]))
        if h["entities"]:
            print("    entity candidates: " + "; ".join(h["entities"]))
        if h["scope"]:
            print("    scope / conditions to keep in cond: " + "; ".join(h["scope"]))
        flags = []
        if h["numbers"]:
            flags.append("numbers " + ", ".join(h["numbers"]))
        if h["hedge"]:
            flags.append("hedge '%s' -> modality=hedged" % h["hedge"])
        if h["negation"]:
            flags.append("negation '%s' -> polarity?" % h["negation"])
        if h["universal"]:
            flags.append("universal quantifier %s (keep only if the paper does)" % ",".join(h["universal"]))
        if flags:
            print("    " + " | ".join(flags))
        if h["citations"]:
            print("    cites: " + "; ".join("%s -> %s" % (c["marker"], c["ref"] or "unresolved") for c in h["citations"]))
        print("    origin guess: %s" % h["origin_guess"])
    if len(targets) > a.max:
        print("... %d more sentences: narrow with anchors or --max" % (len(targets) - a.max))


# ------------------------------------------------------------------------------------------------ source metadata
def cmd_meta(a):
    d, _ = load(a.work)
    src = d["source"]
    for kv in a.set or []:
        k, _, v = kv.partition("=")
        k = k.strip()
        if not v.strip() or k not in ("title", "authors", "year", "doi", "venue", "version", "arxiv_id", "pmid", "keywords"):
            raise SystemExit("--set key=value with key in title, authors, year, doi, venue, version, arxiv_id, pmid, keywords (got %r)" % kv)
        val = [x.strip() for x in re.split(r";", v)] if k in ("authors", "keywords") else (int(v) if k == "year" and v.strip().isdigit() else v.strip())
        src[k] = srcmeta.fld(val, "set by the agent (read from the paper text)", "medium", note="manual entry; the value must be visible in the paper")
        if k in src.get("missing", []):
            src["missing"].remove(k)
    if a.crossref:
        doi = (src.get("doi") or {}).get("value")
        if not doi:
            print("no DOI known: cannot query Crossref")
        else:
            cr = srcmeta.crossref(doi)
            if "error" in cr:
                print("Crossref unavailable (%s): metadata stays as extracted from the file" % cr["error"])
            else:
                src["crossref"] = {"retrieved": now_iso(), **cr}
                for k in ("title", "authors", "year", "venue"):
                    if cr.get(k) and k not in src:
                        src[k] = srcmeta.fld(cr[k], "Crossref (doi %s)" % doi, "high")
                        if k in src["missing"]:
                            src["missing"].remove(k)
                    elif cr.get(k) and k in src and str(src[k]["value"]).lower() != str(cr[k]).lower() and k in ("title", "year"):
                        src.setdefault("conflicts", []).append({"field": k, "file": src[k]["value"], "crossref": cr[k]})
                print("Crossref: filled missing fields; conflicts: %s" % json.dumps(src.get("conflicts", []), ensure_ascii=False)[:300])
    jsave(os.path.join(a.work, "units.json"), d)
    print(json.dumps({k: (v if k in ("file", "missing", "crossref", "conflicts") else {"value": v["value"], "origin": v["origin"], "confidence": v["confidence"]}) for k, v in src.items()}, ensure_ascii=False, indent=1))
    if src["missing"]:
        print("MISSING: %s - they are exported as unknown; do not invent them. If the paper text shows them, `meta W --set title=...`." % ", ".join(src["missing"]))


# ------------------------------------------------------------------------------------------------ ingest
def next_id(claimsd):
    n = 1
    while "C%d" % n in claimsd:
        n += 1
    return "C%d" % n


def norm_ent(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def cmd_ingest(a):
    d, claimsd = load(a.work)
    bm = index(d)
    text = sys.stdin.read() if (not a.file or a.file == "-") else open(a.file, encoding="utf-8").read()
    recs = C.parse_claim_jsonl(text) if text.lstrip().startswith("{") else C.parse_claim_blocks(text)
    if not recs:
        raise SystemExit("no claims found: start each claim with '=== claim' and give text:, s:, p:, o:, ev: (see SKILL.md)")
    refs = d.get("refs", [])
    n, lines, touched = Counter(), [], set()
    for r in recs:
        cid = (r.get("id") or "").strip() or None
        replaced = False
        if not cid:
            cw = nlib.content_words(r.get("text") or "")
            best, bj = None, 0.0
            for k2, v2 in claimsd.items():
                if k2 in touched:
                    continue
                same = norm_ent(v2.get("s")) == norm_ent(r.get("s")) and norm_ent(v2.get("o")) == norm_ent(r.get("o")) and v2.get("s") and vocab.resolve_relation(v2.get("p", ""))[0] == vocab.resolve_relation(r.get("p", ""))[0]
                ow = nlib.content_words(v2.get("text") or "")
                j = len(cw & ow) / len(cw | ow) if cw and ow else 0.0
                j = max(j, 1.0 if same and j >= 0.5 else 0.0)
                if j > bj:
                    best, bj = k2, j
            if best and bj >= 0.85:
                cid, replaced = best, True
        cid = cid or next_id(claimsd)
        touched.add(cid)
        rec = {"id": cid, "text": (r.get("text") or "").strip(), "s": (r.get("s") or "").strip(), "p": (r.get("p") or "").strip(), "o": (r.get("o") or "").strip(), "cond": (r.get("cond") or "").strip(),
               "ev": str(r.get("ev") or "").strip(), "quote": C.split_quotes(r.get("quote")), "evtype": (r.get("evtype") or "").strip().lower(), "modality": (r.get("modality") or "").strip().lower(),
               "polarity": (r.get("polarity") or "").strip().lower(), "origin": (r.get("origin") or "").strip(), "conf": (r.get("conf") or "").strip().lower(), "basis": r.get("basis", ""),
               "s_id": (r.get("s_id") or "").strip(), "o_id": (r.get("o_id") or "").strip(), "value": r.get("value", ""), "unit": r.get("unit", ""), "type": (r.get("type") or "finding").strip().lower(),
               "note": r.get("note", ""), "searched": r.get("searched", ""), "status": (r.get("status") or "reported").strip().lower(), "sec": r.get("sec", ""), "derived": r.get("derived", ""),
               "tags": ", ".join(sorted({t.strip().lower() for t in re.split(r"[,;]", r.get("tags", "")) if t.strip()}))}
        if rec["status"] not in vocab.STATUSES:
            lines.append("%s status '%s' unknown (%s): treated as reported" % (cid, rec["status"], ", ".join(vocab.STATUSES)))
            rec["status"] = "reported"
        others = [v for k2, v in claimsd.items() if k2 != cid]
        issues, ver = C.validate_claim(d, bm, {**rec, "quote": " ||| ".join(rec["quote"])}, others, refs)
        rec.update({"issues": issues, "verification": ver, "status_check": C.status_of(issues), "tries": claimsd.get(cid, {}).get("tries", 0) + 1, "ts": int(time.time())})
        claimsd[cid] = rec
        n[rec["status_check"]] += 1
        if replaced:
            lines.append("%s replaced the earlier version (same subject/relation/object or wording; use id=%s to be explicit)" % (cid, cid))
        for iss in issues:
            if iss["severity"] == "error" or a.verbose:
                lines.append("%s %s %s: %s" % (cid, iss["severity"].upper(), iss["kind"], iss["detail"]))
    jsave(os.path.join(a.work, "claims.json"), claimsd)
    acc = [v for v in claimsd.values() if v["status_check"] != "error"]
    print("stored %d | ok %d | warn %d | ERROR %d | accepted claims in total: %d (reported %d)" % (len(recs), n["ok"], n["warn"], n["error"], len(acc), sum(1 for v in acc if v["status"] == "reported")))
    print("ids: " + " ".join("%s%s" % (k, "*" if claimsd[k]["status_check"] == "error" else "") for k in sorted(touched, key=lambda x: int(re.sub(r"\D", "", x) or 0))) + "   (* = failing; resubmit with id=<id>)")
    for ln in lines[:40]:
        print("  " + ln)
    if n["warn"] and not a.verbose:
        print("  (%d claim(s) have warnings: `check %s` or ingest -v to list them)" % (n["warn"], a.work))
    sys.exit(2 if n["error"] else 0)


# ------------------------------------------------------------------------------------------------ check / next
def covered_sentences(d, claimsd):
    cov = set()
    byu = {u["id"]: u for u in d["units"]}
    for c in claimsd.values():
        if c["status_check"] == "error":
            continue
        for uid, s1, s2 in U.parse_anchors(c.get("ev", ""))[0]:
            if uid in byu:
                cov.update((uid, k) for k in (range(s1, (s2 or s1) + 1) if s1 else range(1, len(byu[uid]["sentences"]) + 1)))
    return cov


def run_check(work):
    d, claimsd = load(work)
    secs = U.sec_of(d)
    acc = [c for c in claimsd.values() if c["status_check"] != "error"]
    rep = [c for c in acc if c["status"] == "reported"]
    cov = covered_sentences(d, claimsd)
    cand = []
    for u in d["units"]:
        if u["excluded"] or u["type"] in ("heading", "table", "formula", "title") or (u["type"] == "front" and u["section"] == "§front"):
            continue
        for i, s in enumerate(u["sentences"], 1):
            sc, kinds = sentence_score(u, i, s, secs)
            if sc >= 2.5 and (u["id"], i) not in cov and not restated(d, claimsd, s):
                cand.append((sc, "%s.%d" % (u["id"], i), s))
    cand.sort(key=lambda x: -x[0])
    issues = Counter(i["kind"] for c in claimsd.values() for i in c["issues"])
    conf = Counter(c["verification"]["confidence"]["level"] for c in rep)
    src = d["source"]
    summary = {"claims": len(claimsd), "accepted": len(acc), "reported": len(rep), "with_errors": sum(1 for c in claimsd.values() if c["status_check"] == "error"),
               "with_warnings": sum(1 for c in claimsd.values() if c["status_check"] == "warn"), "non_reported": Counter(c["status"] for c in acc if c["status"] != "reported"),
               "quotes_verified": sum(v["verification"]["quotes"].count("verified") for v in claimsd.values()), "quotes_failed": sum(sum(1 for q in v["verification"]["quotes"] if q in ("missing", "elsewhere")) for v in claimsd.values()),
               "confidence": dict(conf), "origin": dict(Counter(c["verification"]["origin"] for c in rep)), "relations": dict(Counter(c["verification"]["relation"] for c in rep)),
               "issue_kinds": dict(issues), "source_missing": src["missing"], "uncovered_candidates": len(cand)}
    summary["non_reported"] = dict(summary["non_reported"])
    return {"summary": summary, "error_claims": [k for k, c in claimsd.items() if c["status_check"] == "error"], "uncovered_candidates": ["%s %s" % (x[1], x[2][:140]) for x in cand[:12]]}


def cmd_check(a):
    r = run_check(a.work)
    print(json.dumps(r["summary"], ensure_ascii=False, indent=1))
    d, claimsd = load(a.work)
    for k, c in claimsd.items():
        for i in c["issues"]:
            if a.all or i["severity"] == "error" or c["status_check"] == "warn":
                print("%s %s %s: %s" % (k, i["severity"].upper(), i["kind"], i["detail"][:260]))
    if r["uncovered_candidates"]:
        print("Uncovered key-conclusion candidates (turn them into claims or leave them out on purpose):")
        for x in r["uncovered_candidates"][:8]:
            print("  " + x)
    sys.exit(2 if r["error_claims"] else 0)


def cmd_next(a):
    r = run_check(a.work)
    s = r["summary"]
    d, claimsd = load(a.work)
    t0 = (jload(os.path.join(a.work, "state.json"), {}) or {}).get("t0")
    print("claims: %d accepted (%d reported), %d failing | confidence %s | origin %s" % (s["accepted"], s["reported"], s["with_errors"], s["confidence"], s["origin"]))
    todo = 0
    for k in r["error_claims"]:
        todo += 1
        print("FIX %s: %s" % (k, "; ".join(i["kind"] + ": " + i["detail"][:140] for i in claimsd[k]["issues"] if i["severity"] == "error")))
    if s["reported"] == 0:
        print("TODO write claims: `candidates W` lists the key-conclusion sentences; `atoms W E104.2` shows how to split them.")
    if s["source_missing"]:
        print("TODO source metadata missing: %s (`meta W`; set from the paper text or leave unknown)" % ", ".join(s["source_missing"]))
    if r["uncovered_candidates"]:
        print("TODO %d uncovered key-conclusion candidate sentence(s), e.g.:" % s["uncovered_candidates"])
        for x in r["uncovered_candidates"][:5]:
            print("  " + x)
    if not todo and s["reported"] and not r["uncovered_candidates"]:
        print("Nothing blocking. Run `assemble W --out OUT` (and `validate OUT/nanopubs.trig`).")
    if t0:
        print("elapsed %ds" % (time.time() - t0))


# ------------------------------------------------------------------------------------------------ merge / drop
def cmd_drop(a):
    d, claimsd = load(a.work)
    for k in a.ids:
        print(("dropped " + k) if claimsd.pop(k, None) else ("no such claim " + k))
    jsave(os.path.join(a.work, "claims.json"), claimsd)


def cmd_merge(a):
    d, claimsd = load(a.work)
    if a.keep not in claimsd or a.other not in claimsd:
        raise SystemExit("unknown claim id")
    k, o = claimsd[a.keep], claimsd[a.other]
    ev = ", ".join(x for x in (k["ev"], o["ev"]) if x)
    quotes = list(dict.fromkeys(k["quote"] + o["quote"]))
    k["ev"], k["quote"] = ev, quotes
    del claimsd[a.other]
    bm = index(d)
    issues, ver = C.validate_claim(d, bm, {**k, "quote": " ||| ".join(quotes)}, [v for i2, v in claimsd.items() if i2 != a.keep], d.get("refs", []))
    k.update({"issues": issues, "verification": ver, "status_check": C.status_of(issues)})
    jsave(os.path.join(a.work, "claims.json"), claimsd)
    print("merged %s into %s (evidence: %s) -> %s" % (a.other, a.keep, ev, k["status_check"]))


# ------------------------------------------------------------------------------------------------ records
def source_record(d, idx):
    src = d["source"]
    g = lambda k: (src.get(k) or {}).get("value")
    doi, arx = g("doi"), g("arxiv_id")
    sha = (src.get("file") or {}).get("sha256")
    if doi:
        s_iri = "https://doi.org/" + doi
    elif arx:
        s_iri = "https://arxiv.org/abs/" + arx
    elif sha:
        s_iri = "urn:sha256:" + sha
    else:
        s_iri = "urn:np-claim-builder:source:%d" % idx
    return {"source_id": "S%d" % idx, "iri": s_iri, "title": g("title"), "authors": g("authors"), "year": g("year"), "venue": g("venue"), "doi": doi, "arxiv_id": arx, "pmid": g("pmid"), "version": g("version") or g("version_label"),
            "sha256": sha, "file_name": (src.get("file") or {}).get("file_name"), "pages": (src.get("file") or {}).get("pages"), "fields": {k: {"origin": v["origin"], "confidence": v["confidence"]} for k, v in src.items() if isinstance(v, dict) and "origin" in v},
            "missing": src.get("missing", []), "conflicts": src.get("conflicts", [])}


def evidence_list(d, c):
    byu = {u["id"]: u for u in d["units"]}
    secs = U.sec_of(d)
    ver = c["verification"]
    out = []

    def mk(uid, start, end, quote, kind):
        u = byu[uid]
        spans = C.sentence_spans(u)
        sidx = [i + 1 for i, (a0, b0) in enumerate(spans) if a0 < end and b0 > start]
        sec = secs[u["section"]]
        loc = {"unit": uid, "sentences": ("%d" % sidx[0] if len(sidx) == 1 else "%d-%d" % (sidx[0], sidx[-1])) if sidx else None, "page": u["page"], "pages": u["pages"], "bbox": u["bbox"], "block": u.get("block"),
               "section_id": u["section"], "section_title": sec["title"], "section_path": sec.get("path") or sec["title"], "char_start": start, "char_end": end,
               "prefix": u["text"][max(0, start - 40):start].lstrip(), "suffix": u["text"][end:end + 40].rstrip()}
        return {"kind": kind, "quote": quote, "locator": loc}
    for q in ver.get("quote_locators", []):
        out.append(mk(q["unit"], q["start"], q["end"], q["quote"], "author_quote"))
    if not out:
        use = ver.get("minimal_anchors") or []
        anchors, _ = U.parse_anchors(c.get("ev", ""))
        want = []
        for uid, s1, s2 in anchors:
            if uid not in byu or byu[uid]["excluded"]:
                continue
            if s1:
                want += [(uid, k) for k in range(s1, (s2 or s1) + 1)]
            else:
                pick = [int(x.split(".")[1]) for x in use if x.startswith(uid + ".")] or [1]
                want += [(uid, k) for k in pick]
        for uid, k in want[:4]:
            u = byu[uid]
            spans = C.sentence_spans(u)
            if k <= len(spans):
                a0, b0 = spans[k - 1]
                out.append(mk(uid, a0, b0, u["text"][a0:b0], "anchored_sentence"))
    return out


def build_record(d, c, src, created, idx):
    ver = c["verification"]
    term = ver["relation"]
    rel = vocab.RELATIONS[term]
    val, unit_ = C.numeric_value(c["o"], c.get("value"))
    if c.get("unit"):
        unit_ = c["unit"]
    s_iri = vocab.curie_iri(c["s_id"]) if c.get("s_id") else None
    o_iri = vocab.curie_iri(c["o_id"]) if c.get("o_id") else None
    h = hashlib.sha256(("%s|%s|%s|%s|%s" % (src["sha256"] or src["iri"], c["id"], c["s"], term, c["o"])).encode("utf-8")).hexdigest()[:12]
    ev = evidence_list(d, c)
    cites = ver.get("citations") or []
    origin = (c.get("origin") or ver["origin"]).strip()
    kind = "cited" if origin.startswith("cited") else origin
    cited = [{"marker": x["marker"], "ref_n": x["ref_n"], "ref_text": x["ref_text"], "doi": x["doi"]} for x in cites] if kind in ("cited", "background") or ver["origin"] == "cited" else []
    level = ver["confidence"]["level"]
    if c.get("conf") in ("low", "medium", "high") and {"low": 0, "medium": 1, "high": 2}[c["conf"]] < {"low": 0, "medium": 1, "high": 2}[level]:
        level = c["conf"]
    declared_mod = c.get("modality") or ""
    modality = ver["modality"] if declared_mod in ("", "asserted") else declared_mod
    problems = [i for i in c["issues"] if i["severity"] != "error"]
    needs = bool(problems) or level == "low" or c["status"] != "reported"
    rec = {"np_id": "np" + h, "claim_id": c["id"], "status": c["status"], "claim_text": c["text"], "claim_type": c.get("type") or "finding",
           "assertion": {"subject": {"label": c["s"], "id": c.get("s_id") or None, "iri": s_iri, "id_origin": ("asserted by the claim author (not in the paper)" if c.get("s_id") and "identifier_origin" in {i["kind"] for i in c["issues"]} else ("paper" if c.get("s_id") else None))},
                         "relation": {"term": term, "label": rel["label"], "iri": vocab.VOCAB_NS + term, "close_match": ("http://purl.obolibrary.org/obo/" + rel["close"]) if rel["close"] else None, "close_match_label": rel["map_label"],
                                      "free_text": c["p"] if term == "other" or c["p"].lower() != term else None, "directional": rel["directional"]},
                         "object": {"label": c["o"], "id": c.get("o_id") or None, "iri": o_iri, "value": val, "unit": unit_ or None,
                                    "id_origin": ("asserted by the claim author (not in the paper)" if c.get("o_id") and "identifier_origin" in {i["kind"] for i in c["issues"]} else ("paper" if c.get("o_id") else None))},
                         "polarity": c.get("polarity") or "positive", "conditions": c.get("cond") or None, "claim_type": c.get("type") or "finding"},
           "modality": modality, "evidence_type": c.get("evtype") if c.get("evtype") and c.get("evtype") == ver["evtype"] else ver["evtype"], "evidence": ev,
           "source": src, "attribution": {"origin": kind or "this_paper", "computed_origin": ver["origin"], "cited": cited},
           "confidence": {"level": level, "basis": ver["confidence"]["basis"] + (["declared: %s" % c["basis"]] if c.get("basis") else []), "scope": "extraction fidelity: how well the evidence supports this wording; not a judgement of scientific truth"},
           "checks": {"status": c["status_check"], "issues": [{"severity": i["severity"], "kind": i["kind"], "detail": i["detail"]} for i in c["issues"]], "support": ver["support"], "numbers": ver["numbers"], "quotes": ver["quotes"], "direction": ver.get("direction"),
                      "minimal_anchors": ver.get("minimal_anchors")},
           "review": {"needs_human": needs, "status": "machine-extracted; unreviewed" if needs or True else "", "reasons": sorted({i["kind"] for i in problems} | ({"low_confidence"} if level == "low" else set()) | ({c["status"]} if c["status"] != "reported" else set()))},
           "note": c.get("note") or None, "tags": [t for t in (c.get("tags") or "").split(", ") if t], "created": created, "tool_version": VERSION, "schema": SCHEMA}
    return rec


def roundtrip_check(d, rec):
    """every evidence locator must reproduce its quote from the stored unit text: the 'trace back' guarantee"""
    byu = {u["id"]: u for u in d["units"]}
    bad = []
    for e in rec["evidence"]:
        loc = e["locator"]
        u = byu.get(loc["unit"])
        if not u or u["text"][loc["char_start"]:loc["char_end"]] != e["quote"]:
            bad.append(loc["unit"])
    return bad


# ------------------------------------------------------------------------------------------------ assemble
def contract_fields(case):
    oc = find_key(case, ["output_contract", "outputContract", "output_schema", "outputs"]) if case else None
    fields = []

    def add(x):
        if isinstance(x, str) and x not in fields:
            fields.append(x)
    if isinstance(oc, list):
        for it in oc:
            add(it if isinstance(it, str) else (it.get("name") or it.get("field") or it.get("key")) if isinstance(it, dict) else None)
    elif isinstance(oc, dict):
        inner = oc.get("fields") or oc.get("required") or oc.get("properties") or oc.get("required_fields")
        if isinstance(inner, list):
            for it in inner:
                add(it if isinstance(it, str) else (it.get("name") or it.get("field") or it.get("key")) if isinstance(it, dict) else None)
        elif isinstance(inner, dict):
            for k in inner:
                add(k)
        else:
            for k in oc:
                if k not in ("type", "description", "title", "version", "schema", "$schema", "additionalProperties"):
                    add(k)
    return fields


def derive_field(name, ctx):
    n = name.lower()
    recs = ctx["records"]
    if n in ("status", "run_status", "state", "outcome"):
        return True, ctx["status"]
    if n in ("sources", "source", "input", "inputs", "input_id", "input_identification", "input_files", "papers"):
        return True, ctx["sources"]
    if n in ("uncertainty", "uncertainties", "caveats", "risks", "unresolved", "uncertain_items", "limitations"):
        return True, ctx["uncertainty"]
    if n in ("change_records", "changes", "change_log", "modifications", "edits"):
        return True, ctx["changes"]
    if n in ("claims", "nanopublications", "nanopubs", "assertions", "items", "results", "records", "knowledge_units", "atomic_claims", "extractions", "answer", "main_result"):
        return True, [r for r in recs if r["status"] == "reported"]
    if n in ("unsupported_claims", "non_reported", "unsupported", "unresolved_claims", "rejected_claims", "gaps"):
        return True, [r for r in recs if r["status"] != "reported"] + ctx["rejected"]
    if n in ("evidence", "evidence_links", "anchors", "evidence_map", "locations", "evidence_locations"):
        return True, [{"np_id": r["np_id"], "claim": r["claim_text"], "evidence": r["evidence"]} for r in recs]
    if n in ("provenance", "source_metadata", "metadata", "bibliography", "paper_info", "source_info", "paper_metadata", "references_to_source"):
        return True, ctx["sources"]
    if n in ("trig", "nanopub_trig", "serialization", "export", "rdf", "nanopublication_trig"):
        return True, ctx["trig"] if n != "export" else {"files": ctx["files"], "trig_valid": ctx["trig_check"]["ok"]}
    if n in ("verification", "checks", "qa", "validation", "quality", "self_check", "quality_checks"):
        return True, {"summary": ctx["rep"]["summary"], "trig_validation": ctx["trig_check"], "roundtrip": ctx["roundtrip"]}
    if n in ("human_review", "needs_review", "review_items", "todo", "manual_review", "to_confirm"):
        return True, ctx["review"]
    if n in ("summary", "overview", "report"):
        return True, ctx["summary_text"]
    if n in ("files", "outputs_files", "artifacts", "output_files"):
        return True, ctx["files"]
    if n in ("title", "paper_title"):
        return True, (ctx["sources"][0].get("title") if ctx["sources"] else None)
    return False, None


def review_md(recs, srcs, rep):
    L = ["# Review checklist", "", "Machine-extracted nanopublications: nothing here has been reviewed by a person. Tick each item after comparing with the paper (page / bbox / quote are in `nanopubs.json`).", ""]
    for s in srcs:
        L += ["## Source %s" % s["source_id"], "- file: `%s` (sha256 %s)" % (s.get("file_name"), (s.get("sha256") or "?")[:16]),
              "- title: %s | authors: %s | year: %s | venue: %s | doi: %s" % (s.get("title") or "UNKNOWN", "; ".join(s.get("authors") or []) or "UNKNOWN", s.get("year") or "UNKNOWN", s.get("venue") or "UNKNOWN", s.get("doi") or s.get("arxiv_id") or "UNKNOWN"),
              "- origin of the values: " + "; ".join("%s=%s (%s)" % (k, v["origin"], v["confidence"]) for k, v in s["fields"].items()), "- [ ] confirm bibliographic fields against the first page" + ("; missing: " + ", ".join(s["missing"]) if s["missing"] else ""), ""]
    L += ["## Claims", "", "| id | conf | modality | origin | claim | evidence | to check |", "|---|---|---|---|---|---|---|"]
    for r in recs:
        ev = "; ".join("%s%s p%s" % (e["locator"]["unit"], "." + e["locator"]["sentences"] if e["locator"].get("sentences") else "", e["locator"]["page"]) for e in r["evidence"])
        tc = ", ".join(r["review"]["reasons"]) or "-"
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (r["np_id"], r["confidence"]["level"], r["modality"], r["attribution"]["origin"], r["claim_text"].replace("|", "/")[:140], ev, tc))
    L += ["", "## Always verify by hand", "- relation direction and polarity of every `low`/`medium` claim (the checker is lexical and cannot prove meaning)",
          "- that the quote really supports the whole claim, including conditions", "- identifiers marked `asserted by the claim author`", "- claims attributed to cited work: open the cited reference", ""]
    return "\n".join(L)


def cmd_assemble(a):
    created = now_iso()
    srcs, recs, rejected, status_issues, changes = [], [], [], [], []
    reps, dall = [], []
    for idx, work in enumerate(a.works, 1):
        d, claimsd = load(work)
        reps.append(run_check(work))
        dall.append(d)
        src = source_record(d, idx)
        srcs.append(src)
        for c in claimsd.values():
            if c["status_check"] == "error":
                rejected.append({"claim": c["id"], "source": src["source_id"], "reason": "; ".join(i["kind"] + ": " + i["detail"] for i in c["issues"] if i["severity"] == "error")[:300]})
                continue
            recs.append(build_record(d, c, src, created, idx))
        if d["meta"].get("unparsed"):
            status_issues += [{"kind": "unparsed_input", "page": u.get("page"), "detail": "%s %s" % (u.get("reason"), u.get("detail", ""))} for u in d["meta"]["unparsed"]]
        status_issues += [{"kind": "parser_warning", "detail": w} for w in d["meta"].get("parser_warnings", [])]
        changes.append({"change": "paragraphs re-joined across figures/columns/pages", "count": d["meta"].get("continuations_merged", 0), "source": src["source_id"]})
        changes.append({"change": "claims resubmitted after failing a check", "count": sum(1 for v in claimsd.values() if v.get("tries", 1) > 1), "source": src["source_id"]})
    out = a.out
    os.makedirs(out, exist_ok=True)
    base = a.base or vocab.DEFAULT_BASE
    w = X.Writer(base, a.vocab_ns or vocab.VOCAB_NS)
    reported = [r for r in recs if r["status"] == "reported"]
    header = "# Nanopublications generated by np-claim-builder %s on %s.\n# Local placeholder IRIs (%s): they are not minted / signed (no trusty URIs). %d nanopublication(s)." % (VERSION, created, base, len(reported))
    trig = w.trig(reported, header)
    trig_check = X.validate_trig(trig) if reported else {"ok": False, "nanopubs": 0, "errors": ["no reported claims to export"], "unsupported": None}
    bad_rt = [(r["np_id"], roundtrip_check(dall[r["source"]["source_id"] and int(r["source"]["source_id"][1:]) - 1], r)) for r in recs]
    bad_rt = [x for x in bad_rt if x[1]]
    roundtrip = {"claims": len(recs), "locators_reproduce_quotes": not bad_rt, "failures": bad_rt[:5]}
    top = {"schema": SCHEMA, "tool_version": VERSION, "generated": created, "sources": srcs, "counts": {"nanopublications": len(reported), "other_status": len(recs) - len(reported), "rejected_claims": len(rejected)},
           "vocabulary": {"namespace": a.vocab_ns or vocab.VOCAB_NS, "relations": {k: {"label": v["label"], "definition": v["definition"], "directional": v["directional"], "close_match": ("obo:" + v["close"]) if v["close"] else None, "close_match_label": v["map_label"]} for k, v in vocab.RELATIONS.items()}},
           "nanopubs": recs}
    jsave(os.path.join(out, "nanopubs.json"), top)
    with open(os.path.join(out, "nanopubs.jsonl"), "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(out, "nanopubs.trig"), "w", encoding="utf-8") as fh:
        fh.write(trig)
    with open(os.path.join(out, "claims.csv"), "w", encoding="utf-8", newline="") as fh:
        fh.write(X.csv_text(recs))
    jsave(os.path.join(out, "source.json"), {"sources": srcs, "raw": [d["source"] for d in dall], "references": [d.get("refs", []) for d in dall]})
    jsave(os.path.join(out, "evidence_index.json"), [{"source": "S%d" % (i + 1), "file": d["meta"]["file"], "sections": d["sections"], "units": [{k: u[k] for k in ("id", "type", "section", "pages", "page", "bbox", "block", "excluded", "text", "sentences")} for u in d["units"]]} for i, d in enumerate(dall)])
    with open(os.path.join(out, "review_checklist.md"), "w", encoding="utf-8") as fh:
        fh.write(review_md(recs, srcs, reps[0]))
    rep0 = {"summary": reps[0]["summary"], "per_source": [r["summary"] for r in reps], "rejected_claims": rejected, "uncovered_candidates": [x for r in reps for x in r["uncovered_candidates"]], "trig_validation": trig_check, "roundtrip": roundtrip}
    jsave(os.path.join(out, "check_report.json"), rep0)
    files = ["nanopubs.json", "nanopubs.jsonl", "nanopubs.trig", "claims.csv", "source.json", "evidence_index.json", "review_checklist.md", "check_report.json"]
    # ---- status and uncertainty
    unc = list(status_issues)
    for r in rejected:
        unc.append({"kind": "rejected_claim", "claim": r["claim"], "detail": r["reason"]})
    for r in recs:
        if r["status"] != "reported":
            unc.append({"kind": r["status"], "claim": r["np_id"], "detail": r["note"] or ""})
        elif r["confidence"]["level"] == "low":
            unc.append({"kind": "low_confidence", "claim": r["np_id"], "detail": "; ".join(r["review"]["reasons"])})
    for s in srcs:
        if s["missing"]:
            unc.append({"kind": "source_metadata_missing", "source": s["source_id"], "detail": ", ".join(s["missing"]) + " not found in the file (exported as unknown)"})
    for x in rep0["uncovered_candidates"][:5]:
        unc.append({"kind": "uncovered_key_sentence", "detail": x})
    if not trig_check["ok"]:
        unc.append({"kind": "trig_not_valid", "detail": "; ".join(trig_check["errors"])[:300]})
    ok = bool(reported) and trig_check["ok"] and not rejected and roundtrip["locators_reproduce_quotes"] and all(not s["missing"] or set(s["missing"]) <= {"venue"} or s.get("file_name") == "case_text.txt" for s in srcs)
    status = "success" if ok else ("partial" if reported else "failed")
    summary_text = "%d nanopublication(s) from %s: %s. Source fields missing: %s. TriG valid: %s." % (len(reported), ", ".join(s["file_name"] or s["source_id"] for s in srcs), "; ".join(r["claim_text"][:110] for r in reported[:3]),
                                                                                                       "; ".join("%s: %s" % (s["source_id"], ",".join(s["missing"]) or "none") for s in srcs), trig_check["ok"])
    review = [{"claim": r["np_id"], "why": r["review"]["reasons"], "confidence": r["confidence"]["level"]} for r in recs if r["review"]["needs_human"]]
    ctx = {"records": recs, "status": status, "sources": srcs, "uncertainty": unc, "changes": changes, "trig": trig, "trig_check": trig_check, "roundtrip": roundtrip, "rep": rep0, "review": review, "files": files, "summary_text": summary_text, "rejected": rejected}
    case = jload(a.case) if a.case and os.path.isfile(a.case) else None
    fields = contract_fields(case)
    answers = jload(a.answers, {}) if a.answers else {}
    cid = (find_key(case, ["case_id", "caseId"]) or find_key(case, ["id"])) if case else None
    result = {"case_id": cid}
    unfilled = []
    for fld in fields:
        if fld == "case_id":
            continue
        if fld in answers:
            result[fld] = answers[fld]
            continue
        okf, v = derive_field(fld, ctx)
        result[fld] = v if okf else None
        if not okf:
            unfilled.append(fld)
    for nm in ("status", "sources", "uncertainty", "change_records", "nanopubs", "verification", "human_review", "files"):
        if nm not in result:
            result[nm] = answers.get(nm, derive_field(nm if nm != "nanopubs" else "nanopubs", ctx)[1])
    for k, v in answers.items():
        result.setdefault(k, v)
    if case is not None and cid is None:
        unfilled.append("case_id")
    result["_meta"] = {"generator": "np-claim-builder/npb.py %s" % VERSION, "contract_fields": fields, "unfilled_fields": unfilled, "contract_found": bool(fields), "files": files}
    jsave(os.path.join(out, "result.json"), result)
    print(json.dumps({"written": out, "status": status, "nanopublications": len(reported), "other_status": len(recs) - len(reported), "rejected_claims": len(rejected), "trig_valid": trig_check["ok"],
                      "locators_reproduce_quotes": roundtrip["locators_reproduce_quotes"], "source_missing": [s["missing"] for s in srcs], "confidence": dict(Counter(r["confidence"]["level"] for r in reported)),
                      "unfilled_contract_fields": unfilled, "contract_found": bool(fields)}, ensure_ascii=False))
    if not trig_check["ok"]:
        print("TriG problems: " + "; ".join(trig_check["errors"][:3] or [str(trig_check["unsupported"])]))
    if unfilled:
        print("UNFILLED contract fields (put them in answers.json and re-run assemble --answers): " + ", ".join(unfilled))
    if not fields and a.case:
        print("WARNING: no output_contract found in the case file: read /input/case.json and task.md and add the fields by hand via --answers")
    sys.exit(0 if ((not unfilled and fields) or not a.case) else 2)


# ------------------------------------------------------------------------------------------------ validate / search / status
def cmd_validate(a):
    p = a.file
    if not os.path.isfile(p):
        raise SystemExit("no such file: " + p)
    raw = open(p, encoding="utf-8").read()
    if p.endswith(".json"):
        j = json.loads(raw)
        recs = j.get("nanopubs", j if isinstance(j, list) else [])
        need = ["np_id", "claim_text", "assertion", "evidence", "source", "attribution", "confidence", "modality", "status"]
        errs = []
        for r in recs:
            for k in need:
                if k not in r:
                    errs.append("%s: missing %s" % (r.get("np_id", "?"), k))
            if r.get("status") == "reported" and not r.get("evidence"):
                errs.append("%s: reported claim without evidence" % r.get("np_id"))
            for e in r.get("evidence", []):
                if not {"unit", "page", "section_path", "char_start", "char_end"} <= set(e.get("locator", {})):
                    errs.append("%s: incomplete evidence locator" % r.get("np_id"))
        print(json.dumps({"ok": not errs, "records": len(recs), "errors": errs[:10]}, ensure_ascii=False))
        sys.exit(0 if not errs else 2)
    res = X.validate_trig(raw)
    print(json.dumps(res, ensure_ascii=False))
    sys.exit(0 if res["ok"] else 2)


def cmd_search(a):
    p = a.target
    path = os.path.join(p, "nanopubs.json") if os.path.isdir(p) else p
    recs = json.load(open(path, encoding="utf-8"))["nanopubs"]
    docs = ["%s %s %s %s %s" % (r["claim_text"], r["assertion"]["subject"]["label"], r["assertion"]["object"]["label"], r["assertion"].get("conditions") or "", " ".join(r["tags"])) for r in recs]
    bm = nlib.BM25(docs)
    for i, sc in bm.top(a.query, a.k):
        r = recs[i]
        print("%s [%s %s p%s] (%.1f) %s | %s -%s-> %s" % (r["np_id"], r["confidence"]["level"], r["modality"], r["evidence"][0]["locator"]["page"] if r["evidence"] else "-", sc, r["claim_text"][:150],
                                                       r["assertion"]["subject"]["label"], r["assertion"]["relation"]["term"], r["assertion"]["object"]["label"]))


def cmd_status(a):
    r = run_check(a.work)
    print(json.dumps(r["summary"], ensure_ascii=False, indent=1))


# ------------------------------------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(prog="npb.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("input", nargs="?")
    p.add_argument("--work", required=True)
    p.add_argument("--case")
    p.add_argument("--pages")
    p.add_argument("--lang", default="auto")
    p.add_argument("--ocr", default=None)
    p.add_argument("--budget", type=int, default=900)
    p.set_defaults(fn=cmd_prepare)
    p = sub.add_parser("outline")
    p.add_argument("work")
    p.set_defaults(fn=lambda a: cmd_outline(argparse.Namespace(work=a.work)))
    p = sub.add_parser("read")
    p.add_argument("work")
    p.add_argument("--sec")
    p.add_argument("--ids")
    p.add_argument("--page", type=int)
    p.add_argument("--sentences", action="store_true")
    p.add_argument("--max-words", type=int, default=1500)
    p.set_defaults(fn=cmd_read)
    p = sub.add_parser("find")
    p.add_argument("work")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=5)
    p.set_defaults(fn=cmd_find)
    p = sub.add_parser("candidates")
    p.add_argument("work")
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--min-score", type=float, default=None)
    p.set_defaults(fn=cmd_candidates)
    p = sub.add_parser("atoms")
    p.add_argument("work")
    p.add_argument("anchors", nargs="*")
    p.add_argument("--sec")
    p.add_argument("--max", type=int, default=12)
    p.set_defaults(fn=cmd_atoms)
    p = sub.add_parser("meta")
    p.add_argument("work")
    p.add_argument("--crossref", action="store_true")
    p.add_argument("--set", action="append")
    p.set_defaults(fn=cmd_meta)
    p = sub.add_parser("ingest")
    p.add_argument("work")
    p.add_argument("file", nargs="?")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(fn=cmd_ingest)
    p = sub.add_parser("next")
    p.add_argument("work")
    p.set_defaults(fn=cmd_next)
    p = sub.add_parser("check")
    p.add_argument("work")
    p.add_argument("--all", action="store_true")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("merge")
    p.add_argument("work")
    p.add_argument("keep")
    p.add_argument("other")
    p.set_defaults(fn=cmd_merge)
    p = sub.add_parser("drop")
    p.add_argument("work")
    p.add_argument("ids", nargs="+")
    p.set_defaults(fn=cmd_drop)
    p = sub.add_parser("assemble")
    p.add_argument("works", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--case")
    p.add_argument("--answers")
    p.add_argument("--base")
    p.add_argument("--vocab-ns", dest="vocab_ns")
    p.set_defaults(fn=cmd_assemble)
    p = sub.add_parser("validate")
    p.add_argument("file")
    p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("search")
    p.add_argument("target")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=8)
    p.set_defaults(fn=cmd_search)
    p = sub.add_parser("status")
    p.add_argument("work")
    p.set_defaults(fn=cmd_status)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
