#!/usr/bin/env python3
"""export.py - serialise claim records as nanopublications (TriG), JSON, JSONL, CSV; and validate a TriG file against the nanopublication
well-formedness rules (Nanopublication Guidelines: head / assertion / provenance / publicationInfo, exactly-one quads, distinct graph IRIs,
every triple in one of the four graphs, provenance references the assertion, pubinfo references the nanopublication).

The validator is a small stdlib TriG reader that understands the subset this tool writes (and the guidelines' own examples): @prefix/PREFIX, `a`,
`;` and `,` lists, <iri>, prefixed names, string / number / boolean literals with ^^datatype or @lang. It does not support blank-node
property lists or collections: files using them are reported as "unsupported syntax", not as invalid.
"""
from __future__ import annotations

import csv
import io
import json
import re

import vocab

NS = vocab.PREFIXES
NP_TYPE = NS["np"] + "Nanopublication"


def slug(label, maxlen=60):
    s = re.sub(r"[^A-Za-z0-9]+", "_", re.sub(r"[^\x00-\x7f]", lambda m: "u%04x" % ord(m.group(0)), label or "")).strip("_")
    return (s[:maxlen] or "x").lower()


def lit(s):
    s = str(s)
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return '"%s"' % s


def iri(s):
    return "<%s>" % re.sub(r"[\s<>\"{}|\\^`]", lambda m: "%%%02X" % ord(m.group(0)), s)


def typed(v):
    if isinstance(v, bool):
        return '"%s"^^xsd:boolean' % str(v).lower()
    if isinstance(v, int):
        return '"%d"^^xsd:integer' % v
    if isinstance(v, float):
        return '"%s"^^xsd:decimal' % repr(v)
    return lit(v)


class Writer:
    def __init__(self, base, vocab_ns):
        self.base = base if base.endswith("/") else base + "/"
        self.vns = vocab_ns

    def v(self, name):
        return "v:" + name

    def entity_iri(self, ent):
        if ent.get("iri"):
            return iri(ent["iri"])
        return iri(self.base + "entity/" + slug(ent["label"]))

    def source_iri(self, src):
        return iri(src["iri"])

    def nanopub(self, rec):
        """-> TriG text of one nanopublication"""
        pid = rec["np_id"]
        N = self.base + "np/" + pid + "/"
        a = rec["assertion"]
        s_iri, o_iri = self.entity_iri(a["subject"]), self.entity_iri(a["object"])
        rel = a["relation"]
        rel_iri = "v:" + rel["term"]
        src = rec["source"]
        L = ["@prefix : <%s> ." % N] + ["@prefix %s: <%s> ." % (k, NS[k]) for k in ("rdf", "rdfs", "xsd", "skos", "np", "prov", "dct", "oa")] + ["@prefix v: <%s> ." % self.vns, ""]
        L += [":Head {", "  : a np:Nanopublication ;", "    np:hasAssertion :assertion ;", "    np:hasProvenance :provenance ;", "    np:hasPublicationInfo :pubinfo .", "}", ""]
        # ---- assertion
        A = [f"  {s_iri} rdfs:label {lit(a['subject']['label'])} .", f"  {o_iri} rdfs:label {lit(a['object']['label'])} ."]
        if a["polarity"] == "positive":
            A.append(f"  {s_iri} {rel_iri} {o_iri} .")
        if rel.get("close_match"):
            A.append(f"  {rel_iri} skos:closeMatch {iri(rel['close_match'])} .")
        props = [("a", "v:Claim"), ("v:statement", lit(rec["claim_text"])), ("v:subject", s_iri), ("v:relation", rel_iri), ("v:object", o_iri), ("v:polarity", lit(a["polarity"])), ("v:claimType", lit(a["claim_type"]))]
        if rel["term"] == "other" and rel.get("free_text"):
            props.append(("v:relationText", lit(rel["free_text"])))
        if a.get("conditions"):
            props.append(("v:condition", lit(a["conditions"])))
        if a["object"].get("value") is not None:
            props.append(("v:objectValue", typed(a["object"]["value"])))
        if a["object"].get("unit"):
            props.append(("v:objectUnit", lit(a["object"]["unit"])))
        A.append("  :claim " + " ;\n    ".join("%s %s" % p for p in props) + " .")
        L += [":assertion {"] + A + ["}", ""]
        # ---- provenance
        P = []
        srcn = self.source_iri(src)
        P.append(f"  :assertion prov:wasDerivedFrom {srcn} ;")
        pl = []
        pl.append(("v:evidenceType", lit(rec["evidence_type"])))
        pl.append(("v:modality", lit(rec["modality"])))
        pl.append(("v:confidence", lit(rec["confidence"]["level"])))
        pl.append(("v:confidenceBasis", lit("; ".join(rec["confidence"]["basis"]))))
        pl.append(("v:attribution", lit(rec["attribution"]["origin"])))
        pl.append(("v:extractionStatus", lit(rec["status"])))
        for i, ev in enumerate(rec["evidence"], 1):
            pl.append(("v:supportedBy", ":evidence%d" % i))
        cited = rec["attribution"].get("cited") or []
        for j, c in enumerate(cited, 1):
            if c.get("doi"):
                pl.append(("prov:wasDerivedFrom", iri("https://doi.org/" + c["doi"])))
            else:
                pl.append(("prov:wasDerivedFrom", ":cited%d" % j))
        P.append("    " + " ;\n    ".join("%s %s" % p for p in pl) + " .")
        for j, c in enumerate(cited, 1):
            if not c.get("doi"):
                P.append(f"  :cited{j} dct:bibliographicCitation {lit(c.get('ref_text') or c.get('marker') or 'unresolved citation')} ; v:marker {lit(c.get('marker') or '')} .")
        for i, ev in enumerate(rec["evidence"], 1):
            loc = ev["locator"]
            e = [("a", "oa:SpecificResource, v:EvidenceSpan"), ("oa:hasSource", srcn), ("v:evidenceKind", lit(ev["kind"])), ("rdf:value", lit(ev["quote"] or ""))]
            e.append(("v:unit", lit(loc["unit"])))
            if loc.get("sentences"):
                e.append(("v:sentences", lit(loc["sentences"])))
            if loc.get("page") is not None:
                e.append(("v:page", typed(int(loc["page"]))))
            if loc.get("section_path"):
                e.append(("v:section", lit(loc["section_path"])))
            if loc.get("bbox"):
                e.append(("v:bbox", lit(json.dumps(loc["bbox"]))))
            if loc.get("char_start") is not None:
                e.append(("v:startInUnit", typed(int(loc["char_start"]))))
                e.append(("v:endInUnit", typed(int(loc["char_end"]))))
            if ev["quote"]:
                e.append(("oa:hasSelector", ":selector%d" % i))
            P.append(f"  :evidence{i} " + " ;\n    ".join("%s %s" % p for p in e) + " .")
            if ev["quote"]:
                sel = [("a", "oa:TextQuoteSelector"), ("oa:exact", lit(ev["quote"]))]
                if loc.get("prefix"):
                    sel.append(("oa:prefix", lit(loc["prefix"])))
                if loc.get("suffix"):
                    sel.append(("oa:suffix", lit(loc["suffix"])))
                P.append(f"  :selector{i} " + " ;\n    ".join("%s %s" % p for p in sel) + " .")
        sp = [("a", "v:Source")]
        if src.get("title"):
            sp.append(("dct:title", lit(src["title"])))
        for au in src.get("authors") or []:
            sp.append(("dct:creator", lit(au)))
        if src.get("year"):
            sp.append(("dct:issued", '"%s"^^xsd:gYear' % src["year"]))
        if src.get("venue"):
            sp.append(("dct:isPartOf", lit(src["venue"])))
        if src.get("version"):
            sp.append(("dct:hasVersion", lit(src["version"])))
        for k, p in (("doi", "doi"), ("arxiv_id", "arXiv"), ("pmid", "PMID")):
            if src.get(k):
                sp.append(("dct:identifier", lit("%s:%s" % (p, src[k]))))
        if src.get("sha256"):
            sp.append(("v:fileSha256", lit(src["sha256"])))
        if src.get("file_name"):
            sp.append(("v:fileName", lit(src["file_name"])))
        P.append(f"  {srcn} " + " ;\n    ".join("%s %s" % p for p in sp) + " .")
        L += [":provenance {"] + P + ["}", ""]
        # ---- publication info
        I = [f"  : dct:created {lit(rec['created'])}^^xsd:dateTime ;", f"    dct:creator {iri(self.base + 'agent/np-claim-builder')} ;",
             f"    v:toolVersion {lit(rec['tool_version'])} ;", f"    v:reviewStatus {lit(rec['review']['status'])} ."]
        L += [":pubinfo {"] + I + ["}", ""]
        return "\n".join(L)

    def trig(self, recs, header=""):
        out = [header.rstrip() + "\n"] if header else []
        out += [self.nanopub(r) for r in recs]
        return "\n".join(out)


def flat_rows(recs):
    cols = ["np_id", "status", "claim_text", "subject", "subject_id", "relation", "relation_text", "object", "object_id", "object_value", "object_unit", "polarity", "conditions", "claim_type", "modality",
            "evidence_type", "attribution", "confidence", "confidence_basis", "quote", "evidence_units", "pages", "section", "source_title", "source_doi", "source_arxiv", "source_year", "source_sha256",
            "needs_review", "issues"]
    rows = []
    for r in recs:
        a = r["assertion"]
        ev = r["evidence"]
        rows.append({"np_id": r["np_id"], "status": r["status"], "claim_text": r["claim_text"], "subject": a["subject"]["label"], "subject_id": a["subject"].get("id") or "", "relation": a["relation"]["term"],
                     "relation_text": a["relation"].get("free_text") or "", "object": a["object"]["label"], "object_id": a["object"].get("id") or "", "object_value": a["object"].get("value") if a["object"].get("value") is not None else "",
                     "object_unit": a["object"].get("unit") or "", "polarity": a["polarity"], "conditions": a.get("conditions") or "", "claim_type": a["claim_type"], "modality": r["modality"],
                     "evidence_type": r["evidence_type"], "attribution": r["attribution"]["origin"], "confidence": r["confidence"]["level"], "confidence_basis": "; ".join(r["confidence"]["basis"]),
                     "quote": " ||| ".join(e["quote"] for e in ev if e["quote"]), "evidence_units": ", ".join(e["locator"]["unit"] + ("." + e["locator"]["sentences"] if e["locator"].get("sentences") else "") for e in ev),
                     "pages": ", ".join(sorted({str(e["locator"].get("page")) for e in ev if e["locator"].get("page") is not None})), "section": "; ".join(sorted({e["locator"].get("section_path") or "" for e in ev})),
                     "source_title": r["source"].get("title") or "", "source_doi": r["source"].get("doi") or "", "source_arxiv": r["source"].get("arxiv_id") or "", "source_year": r["source"].get("year") or "",
                     "source_sha256": r["source"].get("sha256") or "", "needs_review": r["review"]["needs_human"], "issues": "; ".join(i["kind"] for i in r["checks"]["issues"])})
    return cols, rows


def csv_text(recs):
    cols, rows = flat_rows(recs)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


# ------------------------------------------------------------------------------------------------ TriG reader + well-formedness validator
LOC = r"[\w:%/#-]*(?:\.[\w:%/#-]+)*"
TOKEN = re.compile(r"\s*(?:(#[^\n]*)|(<[^>]*>)|(\"(?:[^\"\\]|\\.)*\")|(\^\^)|(@[A-Za-z][\w-]*)|([A-Za-z_][\w-]*(?:\.[\w-]+)*:" + LOC + r"|:" + LOC + r")|(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)|([;,.{}\[\]()])|(a\b|true\b|false\b|PREFIX\b|BASE\b))")


class TrigError(Exception):
    pass


def tokenize(text):
    pos, toks = 0, []
    n = len(text)
    while pos < n:
        if text[pos:].strip() == "":
            break
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise TrigError("cannot tokenise near %r" % text[pos:pos + 40])
        pos = m.end()
        for i, g in enumerate(m.groups()):
            if g is not None:
                if i == 0:
                    break
                toks.append((i + 1, g))
                break
    return toks


def parse_trig(text):
    """-> list of quads (g, s, p, o) with IRIs expanded and literals as ('lit', value, datatype)"""
    toks = tokenize(text)
    prefixes, quads = {}, []
    i = 0

    def expand(t):
        kind, g = t
        if kind == 2:
            return g[1:-1]
        if kind == 6:
            pre, _, loc = g.partition(":")
            if pre not in prefixes:
                raise TrigError("undefined prefix '%s:'" % pre)
            return prefixes[pre] + loc
        if g == "a":
            return NS["rdf"] + "type"
        raise TrigError("expected IRI, got %r" % g)

    def unescape(s):
        m = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "'": "'"}
        return re.sub(r"\\(u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|.)", lambda x: chr(int(x.group(1)[1:], 16)) if x.group(1)[0] in "uU" and len(x.group(1)) > 1 else m.get(x.group(1), x.group(1)), s)

    def term(t):
        kind, g = t
        if kind == 3:
            return ("lit", unescape(g[1:-1]), None)
        if kind == 7:
            return ("lit", g, NS["xsd"] + ("decimal" if "." in g else "integer"))
        if kind == 9 and g in ("true", "false"):
            return ("lit", g, NS["xsd"] + "boolean")
        return expand(t)

    graph = None
    while i < len(toks):
        kind, g = toks[i]
        if g.lower() in ("@prefix", "prefix") or (kind == 5 and g == "@prefix"):
            if toks[i + 1][0] != 6 or toks[i + 2][0] != 2:
                raise TrigError("bad @prefix declaration")
            prefixes[toks[i + 1][1].rstrip(":")] = toks[i + 2][1][1:-1]
            i += 3
            if i < len(toks) and toks[i][1] == ".":
                i += 1
            continue
        if g.lower() in ("@base", "base"):
            raise TrigError("unsupported syntax: @base")
        if g in ("[", "("):
            raise TrigError("unsupported syntax: blank-node property list or collection")
        if kind in (2, 6) and i + 1 < len(toks) and toks[i + 1][1] == "{":
            graph = expand(toks[i])
            i += 2
            continue
        if g == "{":
            graph = ""
            i += 1
            continue
        if g == "}":
            graph = None
            i += 1
            continue
        # a triple group: subject predicate-object lists until '.'
        s = expand(toks[i])
        i += 1
        while True:
            p = expand(toks[i])
            i += 1
            while True:
                if toks[i][1] in ("[", "("):
                    raise TrigError("unsupported syntax: blank-node property list or collection")
                o = term(toks[i])
                i += 1
                if toks[i][0] == 4:  # ^^ datatype
                    o = ("lit", o[1], expand(toks[i + 1]))
                    i += 2
                elif toks[i][0] == 5:  # @lang
                    o = ("lit", o[1], "@" + toks[i][1][1:])
                    i += 1
                quads.append((graph, s, p, o))
                if toks[i][1] == ",":
                    i += 1
                    continue
                break
            if toks[i][1] == ";":
                i += 1
                if toks[i][1] in (".", "}"):
                    break
                continue
            break
        if toks[i][1] == ".":
            i += 1
        elif toks[i][1] != "}":
            raise TrigError("expected '.' near %r" % (toks[i][1],))
    return quads


def validate_trig(text):
    """-> {'ok': bool, 'nanopubs': n, 'errors': [...], 'unsupported': str|None}"""
    errors = []
    try:
        quads = parse_trig(text)
    except TrigError as e:
        msg = str(e)
        return {"ok": False, "nanopubs": 0, "errors": [] if msg.startswith("unsupported") else [msg], "unsupported": msg if msg.startswith("unsupported") else None}
    except (IndexError, ValueError) as e:
        return {"ok": False, "nanopubs": 0, "errors": ["syntax error: %s" % e], "unsupported": None}
    if any(q[0] in (None, "") for q in quads):
        errors.append("a triple is outside any named graph (the context of every triple has to be a valid URI)")
    heads = [q for q in quads if q[2] == NS["rdf"] + "type" and q[3] == NP_TYPE]
    for h in heads:
        g, N = h[0], h[1]
        part = {}
        for name, prop in (("assertion", "hasAssertion"), ("provenance", "hasProvenance"), ("pubinfo", "hasPublicationInfo")):
            xs = [q[3] for q in quads if q[0] == g and q[1] == N and q[2] == NS["np"] + prop]
            if len(xs) != 1:
                errors.append("%s: expected exactly one np:%s quad in the head, found %d" % (N, prop, len(xs)))
            else:
                part[name] = xs[0]
        ids = [N, g] + list(part.values())
        if len(set(map(str, ids))) != len(ids):
            errors.append("%s: the URIs of nanopublication, head, assertion, provenance and publicationInfo must all be different" % N)
        if len(part) == 3:
            allowed = {g, *part.values()}
            mine = [q for q in quads if q[0] in allowed]
            # all triples belong to a graph of this nanopublication (checked below globally)
            if not any(q[0] == part["provenance"] and (q[1] == part["assertion"] or q[3] == part["assertion"]) for q in quads):
                errors.append("%s: no triple in the provenance graph refers to the assertion graph" % N)
            if not any(q[0] == part["pubinfo"] and (q[1] == N or q[3] == N) for q in quads):
                errors.append("%s: no triple in the publicationInfo graph refers to the nanopublication" % N)
            if any(q[0] == part["pubinfo"] and q[1] != N and q[1] == part["assertion"] for q in quads):
                pass
            del mine
    if len([q for q in quads if q[0] is not None]) and not heads:
        errors.append("no '[N] rdf:type np:Nanopublication [H]' quad found")
    known = set()
    for h in heads:
        known.add(h[0])
        known |= {q[3] for q in quads if q[0] == h[0] and q[1] == h[1] and q[2] in (NS["np"] + "hasAssertion", NS["np"] + "hasProvenance", NS["np"] + "hasPublicationInfo")}
    stray = {q[0] for q in quads if q[0] not in known}
    if stray:
        errors.append("triples in graph(s) that are not part of any nanopublication: %s" % ", ".join(sorted(map(str, stray))[:3]))
    return {"ok": not errors and bool(heads), "nanopubs": len(heads), "errors": errors, "unsupported": None}
