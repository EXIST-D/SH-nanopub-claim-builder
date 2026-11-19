#!/usr/bin/env python3
"""claims.py - parse, verify and describe atomic claims (subject - relation - object + conditions) that are bound to evidence in a paper.

Every claim is checked the moment it is submitted (`ingest`): verbatim quotes and their exact position, numbers, whether subject / object really
occur in the evidence, relation direction, atomicity, scope that was dropped, over-broad wording, hedge / negation / polarity, who the claim is
attributed to (this paper or a cited work), whether the evidence is minimal, duplicates, identifier syntax. Checks are rule based and every
finding names the rule and the text that triggered it, so a reviewer can reproduce it.
"""
from __future__ import annotations

import difflib
import json
import re
from collections import Counter

import nlib
import srcmeta
import units as U
import vocab

CLAIM_HEAD = ("claim", "nanopub", "nanopublication", "assertion", "atom")
KEYS = {"text": "text", "claim": "text", "statement": "text", "s": "s", "subject": "s", "p": "p", "predicate": "p", "relation": "p", "o": "o", "object": "o", "cond": "cond", "conditions": "cond",
        "condition": "cond", "scope": "cond", "qualifier": "cond", "qualifiers": "cond", "ev": "ev", "evidence": "ev", "anchor": "ev", "anchors": "ev", "quote": "quote", "quotes": "quote",
        "evtype": "evtype", "evidence_type": "evtype", "modality": "modality", "polarity": "polarity", "origin": "origin", "attribution": "origin", "conf": "conf", "confidence": "conf",
        "basis": "basis", "conf_basis": "basis", "confidence_basis": "basis", "s_id": "s_id", "subject_id": "s_id", "o_id": "o_id", "object_id": "o_id", "value": "value", "unit": "unit",
        "type": "type", "claim_type": "type", "note": "note", "notes": "note", "searched": "searched", "status": "status", "sec": "sec", "section": "sec", "id": "id", "tags": "tags", "derived": "derived"}
PRONOUN = re.compile(r"^(it|its|they|them|their|this|that|these|those|which|he|she|one|the\s+(?:method|model|approach|system|study|paper|work|authors?|algorithm|technique|proposed\s+\w+)|our\s+\w+|we|us)$", re.I)
EFFECT_TERMS = ("increases", "decreases", "activates", "inhibits", "regulates", "causes", "prevents", "treats", "associated_with", "interacts_with", "outperforms")
COORD = re.compile(r"(?:,|;)\s*(?:and|while|whereas|but|although|yet)\b|\b(?:both\b.+\band\b|respectively|as well as)\b|;\s", re.I)
BODY_STOP = re.compile(r"[^A-Za-z0-9α-ωΑ-Ω]+")


def jlist(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


# ------------------------------------------------------------------------------------------------ parsing
def parse_claim_blocks(text):
    recs, cur, key = [], None, None
    for ln in text.splitlines():
        s = ln.rstrip()
        if re.match(r"^\s*```\w*\s*$", s):
            continue
        m = re.match(r"^\s*[#=*]{2,}\s*([a-z_]+)\b(.*?)[*=#]*\s*$", s, re.I)
        if m and m.group(1).lower() in CLAIM_HEAD:
            cur = {"attrs": {}, "fields": {}}
            for kv in re.findall(r"([a-z_]+)=((?:\"[^\"]*\")|\S+)", m.group(2)):
                cur["attrs"][KEYS.get(kv[0], kv[0])] = kv[1].strip('"')
            recs.append(cur)
            key = None
            continue
        if cur is None:
            continue
        mk = re.match(r"^\s*(?:[-*]\s*)?([A-Za-z_]+)\s*[:：]\s*(.*)$", s)
        if mk and mk.group(1).lower() in KEYS:
            key = KEYS[mk.group(1).lower()]
            cur["fields"].setdefault(key, [])
            if mk.group(2).strip():
                cur["fields"][key].append(mk.group(2).strip())
            continue
        if key and s.strip():
            cur["fields"][key].append(s.strip())
    out = []
    for r in recs:
        f = {k: (" ".join(v) if k != "quote" else v) for k, v in r["fields"].items()}
        f.update({k: v for k, v in r["attrs"].items() if k not in f})
        out.append(f)
    return out


def parse_claim_jsonl(text):
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            o = json.loads(ln)
        except ValueError:
            continue
        r = {}
        for k, v in o.items():
            k2 = KEYS.get(k, k)
            if isinstance(v, list) and k2 == "ev":
                v = ", ".join(map(str, v))
            if isinstance(v, str) and k2 == "quote":
                v = [v]
            r[k2] = v
        if isinstance(o.get("subject"), dict):  # {"subject": {"label": .., "id": ..}} form
            r["s"], r["s_id"] = o["subject"].get("label", ""), o["subject"].get("id", "")
        if isinstance(o.get("object"), dict):
            r["o"], r["o_id"] = o["object"].get("label", ""), o["object"].get("id", "")
        out.append(r)
    return out


def split_quotes(q):
    out = []
    for it in jlist(q):
        for part in re.split(r"\s*\|\|\|\s*", str(it)):
            part = part.strip().strip('"“”\'').strip()
            if part:
                out.append(part)
    return out


# ------------------------------------------------------------------------------------------------ text helpers
def alnum_map(text):
    """squashed lower-case alphanumerics of `text` and the original index of each kept char"""
    chars, idx = [], []
    for i, ch in enumerate(text):
        rep = nlib.LIGATURES.get(ch, ch)
        for c in rep:
            if c.isalnum():
                chars.append(c.lower())
                idx.append(i)
    return "".join(chars), idx


def locate(text, quote):
    """-> (start, end) of `quote` inside `text` (original character offsets) or None"""
    sq, _ = alnum_map(quote)
    st, idx = alnum_map(text)
    if len(sq) < 4:
        return None
    p = st.find(sq)
    if p < 0:
        return None
    start, end = idx[p], idx[p + len(sq) - 1] + 1
    q = quote.strip()
    if q and not q[-1].isalnum() and end < len(text) and text[end] == q[-1]:
        end += 1  # keep a closing bracket / period that the quote itself ends with
    if q and not q[0].isalnum() and start > 0 and text[start - 1] == q[0]:
        start -= 1
    return start, end


def sentence_spans(unit):
    spans, pos = [], 0
    text = unit["text"]
    for s in unit["sentences"]:
        k = text.find(s, pos)
        if k < 0:
            k = text.find(s)
        if k < 0:
            sq, _ = alnum_map(s)
            loc = locate(text[pos:], s)
            spans.append((pos + loc[0], pos + loc[1]) if loc else (pos, pos))
            continue
        spans.append((k, k + len(s)))
        pos = k + len(s)
    return spans


def words_pos(text):
    """[(stem, start_index_in_text)] of the alphanumeric words"""
    return [(nlib.stem(m.group(0).lower()), m.start()) for m in re.finditer(r"[A-Za-z0-9α-ωΑ-Ω][A-Za-z0-9α-ωΑ-Ω'’-]*", text)]


def label_stems(label):
    return [t for t in nlib.tokens(label) if len(t) > 1 or t.isdigit()]


def label_cover(label, ev_stems):
    st = label_stems(label)
    if not st:
        return 1.0
    return sum(1 for t in st if t in ev_stems) / len(st)


def ent_cover(label, text):
    """how much of an entity label occurs in `text`: stem coverage, or 1.0 when the label squashed (BERT-large vs BERTLARGE) occurs squashed"""
    sl = nlib.squash(label)
    if len(sl) >= 3 and sl in nlib.squash(text):
        return 1.0
    return label_cover(label, nlib.content_words(text))


def label_pos(label, wpos):
    st = set(label_stems(label))
    hits = [p for s, p in wpos if s in st]
    return min(hits) if hits else None


def label_pos_text(label, text):
    """character position of an entity label in a sentence (stem match, else squashed match)"""
    p = label_pos(label, words_pos(text))
    if p is not None:
        return p
    sl, (st, idx) = nlib.squash(label), alnum_map(text)
    k = st.find(sl) if len(sl) >= 3 else -1
    return idx[k] if k >= 0 else None


def doc_idf(d):
    """idf of content words over all sentences of the document (cached): rare words decide which sentence carries a claim"""
    if "_idf" not in d:
        import math
        df, n = Counter(), 0
        for u in d["units"]:
            if u["excluded"]:
                continue
            for s in u["sentences"]:
                n += 1
                df.update(nlib.content_words(s))
        d["_idf"] = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        d["_idf_default"] = math.log(1 + n)
    return d["_idf"], d["_idf_default"]


def wsum(d, words):
    idf, dflt = doc_idf(d)
    return sum(idf.get(w, dflt) for w in words)


def best_sentences(units_by_id, anchors, claim_words, k=2, d=None):
    sents = []
    tot = wsum(d, claim_words) if d else (len(claim_words) or 1)
    for uid, a, b in anchors:
        u = units_by_id[uid]
        ss = u["sentences"][a - 1:b] if a else u["sentences"]
        for s in ss:
            ov = claim_words & nlib.content_words(s)
            sents.append(((wsum(d, ov) if d else len(ov)) / (tot or 1), s, uid))
    sents.sort(key=lambda x: -x[0])
    return sents[:k]


# ------------------------------------------------------------------------------------------------ validation
def sev(kind, severity, detail):
    return {"severity": severity, "kind": kind, "detail": detail}


def numeric_value(o_label, value):
    if value not in (None, ""):
        m = re.match(r"^\s*([-+−]?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?)\s*(.*)$", str(value))
        if m:
            return float(m.group(1).replace(",", "").replace("−", "-")), (m.group(2) or "").strip()
        return None, ""
    m = re.match(r"^\s*([-+−]?\d[\d,]*\.?\d*)\s*(%|[A-Za-zµμ°/·^0-9-]{1,12})?\s*$", o_label or "")
    if m:
        return float(m.group(1).replace(",", "").replace("−", "-")), (m.group(2) or "").strip()
    return None, ""


def validate_claim(d, bm, c, others, refs):
    """-> (issues, ver). ver holds the computed fields (relation term, modality, origin, confidence, evidence type, locators ...)."""
    issues, ver = [], {}
    byu = {u["id"]: u for u in d["units"]}
    status = c.get("status") or "reported"
    text, s_lab, p_raw, o_lab = (c.get("text") or "").strip(), (c.get("s") or "").strip(), (c.get("p") or "").strip(), (c.get("o") or "").strip()
    cond = (c.get("cond") or "").strip()
    src_lang = d["meta"]["lang"]
    same_lang = (nlib.detect_lang(text) if text else src_lang) == src_lang
    # ---- structure
    missing = [k for k, v in (("text", text), ("s", s_lab), ("p", p_raw), ("o", o_lab)) if not v]
    if missing and status == "reported":
        issues.append(sev("incomplete", "error", "missing field(s): %s - a claim needs text, s (subject), p (relation), o (object)" % ", ".join(missing)))
    term, exact = vocab.resolve_relation(p_raw)
    ver["relation"] = term
    if p_raw and status == "reported":
        if term == "other":
            issues.append(sev("relation_free_text", "warn", "relation '%s' is not in the controlled vocabulary: it is exported as v:other with the text kept; pick one of: %s" % (p_raw, ", ".join(k for k in vocab.RELATIONS if k != "other"))))
        elif not exact:
            issues.append(sev("relation_mapped", "warn", "relation '%s' was mapped to '%s': confirm or use the controlled term" % (p_raw, term)))
    for role, lab in (("subject", s_lab), ("object", o_lab)):
        if lab and PRONOUN.match(lab.strip()):
            issues.append(sev("entity_unresolved", "error", "%s '%s' is a pronoun / generic phrase: name the entity (subject confusion)" % (role, lab)))
        elif lab and re.match(r"^(?:this|that|these|those|such|the\s+(?:former|latter|same|above|aforementioned))\s", lab.strip(), re.I):
            issues.append(sev("entity_unresolved", "warn", "%s '%s' starts with a demonstrative: replace it with the entity it refers to (the claim must stand alone)" % (role, lab[:50])))
        elif lab and re.search(r"[A-Za-z)\]]\s(?:and|or)\s[A-Za-z(]|,\s*[A-Za-z]{3,}", lab) and len(lab.split()) <= 12 and not re.search(r"\b(and|or)\b.*\b(of|in)\b", lab):
            issues.append(sev("entity_list", "warn", "%s '%s' looks like several entities: one claim per entity (atomicity)" % (role, lab[:60])))
    # ---- anchors
    anchors, bad = U.parse_anchors(c.get("ev", ""))
    if bad:
        issues.append(sev("anchor_syntax", "error", "bad anchors: %s (use E012, E012.2, E012-E014)" % ", ".join(bad[:4])))
    unknown = [x[0] for x in anchors if x[0] not in byu]
    if unknown:
        issues.append(sev("anchor_unknown", "error", "unknown evidence ids: %s (ids are E001..E%03d)" % (", ".join(sorted(set(unknown))[:5]), len(d["units"]))))
    anchors = [x for x in anchors if x[0] in byu]
    for uid, a_, b_ in anchors:
        u = byu[uid]
        if u["excluded"]:
            issues.append(sev("anchor_excluded", "error", "%s is in an excluded section (references/acknowledgements): it cannot be evidence" % uid))
        if a_ and (a_ > len(u["sentences"]) or (b_ and b_ > len(u["sentences"]))):
            issues.append(sev("anchor_sentence", "error", "%s has only %d sentences" % (uid, len(u["sentences"]))))
    anchors = [x for x in anchors if not byu[x[0]]["excluded"] and not (x[1] and x[1] > len(byu[x[0]]["sentences"]))]
    if status in ("unsupported", "unclear", "conflict", "not_reported") and not (c.get("note") or c.get("searched")):
        issues.append(sev("status_unexplained", "error", "status=%s needs `note:` (what you looked for, where, and why no support was found / what conflicts)" % status))
    if status == "reported" and not anchors:
        sug = None
        for i, sc in bm.top(text or (s_lab + " " + o_lab), 3):
            if not d["units"][i]["excluded"]:
                sug = d["units"][i]
                break
        issues.append(sev("no_evidence", "error", "no evidence anchor (ev:). %s If the paper gives no support, resubmit with status=unsupported." % (("Closest unit: %s [%s] %s..." % (sug["id"], sug["section"], sug["text"][:80])) if sug else "Use `find`.")))
    ev_full, _ = U.anchor_text(byu, [(x[0], None, None) for x in anchors])
    ev_exact, _ = U.anchor_text(byu, anchors)
    ev_stems = nlib.content_words(ev_exact)
    ev_stems_full = nlib.content_words(ev_full)
    # ---- quotes (verbatim + position)
    quotes = split_quotes(c.get("quote"))
    qres, locs = [], []
    for q in quotes:
        sq = nlib.squash(q)
        if len(sq) < 6:
            continue
        host = next((byu[x[0]] for x in anchors if locate(byu[x[0]]["text"], q)), None)
        if host:
            qres.append("verified")
            loc = locate(host["text"], q)
            locs.append({"unit": host["id"], "start": loc[0], "end": loc[1], "quote": host["text"][loc[0]:loc[1]]})
            continue
        where = [u for u in d["units"] if not u["excluded"] and locate(u["text"], q)]
        if where:
            qres.append("elsewhere")
            issues.append(sev("quote_other_unit", "error", "quote is verbatim but sits in %s (%s), not in the cited evidence: cite %s" % (where[0]["id"], where[0]["section"], where[0]["id"])))
            continue
        best, bi = 0.0, None
        for u in d["units"]:
            if u["excluded"] or len(q) > 600:
                continue
            su = nlib.squash(u["text"])
            if len(su) < len(sq):
                continue
            m = difflib.SequenceMatcher(None, su, sq, autojunk=False).find_longest_match(0, len(su), 0, len(sq))
            if m.size / len(sq) > best:
                best, bi = m.size / len(sq), u
        if best >= 0.9:
            qres.append("approx")
            issues.append(sev("quote_approx", "warn", "quote differs slightly from %s (%.0f%% matches): copy it exactly" % (bi["id"], 100 * best)))
        else:
            qres.append("missing")
            issues.append(sev("quote_missing", "error", "quote not found in the paper (best match %.0f%%%s): fabrication or paraphrase - quote verbatim or drop the quote" % (100 * best, " in " + bi["id"] if bi and best >= 0.5 else "")))
    ver["quotes"] = qres or ["none"]
    ver["quote_locators"] = locs
    # ---- numbers
    val, unit_ = numeric_value(o_lab, c.get("value"))
    core = nlib.numbers(" ".join(x for x in (text, cond, str(c.get("value") or "")) if x))
    labn = [n for n in nlib.numbers(" ".join(x for x in (s_lab, o_lab) if x)) if n not in core]
    nums = core + labn
    derived = bool(c.get("derived"))
    ev_nums = set(nlib.numbers_ev(ev_full)) if anchors else set()
    miss = [n for n in nums if n not in ev_nums and not (re.fullmatch(r"\d", n) and not derived)]
    ver["numbers"] = "ok" if not miss else "unsupported"
    if miss and anchors:
        where = []
        for n in miss[:4]:
            hit = next((u for u in d["units"] if not u["excluded"] and n in set(nlib.numbers_ev(u["text"]))), None)
            where.append("%s%s" % (n, " (found in %s)" % hit["id"] if hit else " (not in the paper)"))
        only_labels = all(n in labn for n in miss)
        issues.append(sev("numbers", "warn" if (derived or only_labels) else "error", "numbers not in the cited evidence: %s%s" % (", ".join(where), " - marked derived" if derived else (" - they occur only in the subject/object label: add the anchor that states them (indirect evidence) or drop them from the label" if only_labels else ". Cite the unit that contains them or add `derived:`"))))
    # ---- support: claim words, subject, object in the evidence
    cw = nlib.content_words(text + " " + cond)
    sup = len(cw & ev_stems_full) / len(cw) if cw else 1.0
    ver["support"] = round(sup, 2)
    if anchors and status == "reported" and same_lang:
        if len(cw) >= 4 and sup < 0.15:
            issues.append(sev("support", "error", "the cited evidence hardly shares any wording with the claim (support %.2f): wrong anchor or unsupported claim" % sup))
        elif len(cw) >= 4 and sup < 0.4:
            issues.append(sev("support", "warn", "weak wording support from the evidence (%.2f): check the anchor or add the missing anchor" % sup))
        for role, lab in (("subject", s_lab), ("object", o_lab)):
            if lab and (role == "subject" or val is None):
                cov = ent_cover(lab, ev_full)
                ver["%s_cover" % role] = round(cov, 2)
                if cov == 0 and label_stems(lab):
                    elsewhere = next((u for u in d["units"] if not u["excluded"] and ent_cover(lab, u["text"]) >= 0.99), None)
                    issues.append(sev("entity_not_in_evidence", "error", "%s '%s' does not occur in the cited evidence%s (subject/object mix-up or wrong anchor)" % (role, lab, " - it appears in %s" % elsewhere["id"] if elsewhere else "")))
                elif cov < 0.5:
                    issues.append(sev("entity_not_in_evidence", "warn", "only part of %s '%s' occurs in the evidence (%.0f%%)" % (role, lab, 100 * cov)))
    # ---- evidence sentences used for the cue checks
    best = best_sentences(byu, anchors, cw | set(label_stems(s_lab)) | set(label_stems(o_lab)), 2, d) if anchors else []
    ev_cue = " ".join(b[1] for b in best) if not any(x[1] for x in anchors) else ev_exact
    if locs:  # the verified quote is the minimal span the author relies on: judge hedge / negation / scope on it, not on the whole sentence
        ev_cue = " ".join(l["quote"] for l in locs)
    # ---- direction (active/passive aware), only for directional relations
    rel = vocab.RELATIONS[term]
    if anchors and status == "reported" and rel["directional"] and s_lab and o_lab and same_lang and nlib.cjk_ratio(ev_cue) < 0.3 and term not in ("is_a", "has_value", "uses", "evaluated_on", "trained_on", "part_of", "located_in", "has_phenotype"):
        for sc, sent, uid in best[:1]:
            ss_, os_ = set(label_stems(s_lab)), set(label_stems(o_lab))
            if ss_ & os_ and (ss_ - os_) and (os_ - ss_):  # near-identical labels ("... on 10 kPa gels" vs "... on 40 kPa gels"): compare where the DIFFERING words occur
                wp_ = words_pos(sent)
                pos_ = lambda keys: min([p_ for s_, p_ in wp_ if s_ in keys] or [None]) if any(s_ in keys for s_, _ in wp_) else None
                ps, po = pos_(ss_ - os_), pos_(os_ - ss_)
            else:
                ps, po = label_pos_text(s_lab, sent), label_pos_text(o_lab, sent)
            if ps is not None and po is not None and ps != po:
                passive = bool(vocab.PASSIVE.search(sent))
                reversed_ = (po < ps) != passive
                ver["direction"] = "reversed?" if reversed_ else "ok"
                if reversed_:
                    issues.append(sev("direction", "warn", "in the evidence sentence the object '%s' comes %s the subject '%s'%s: check that the relation '%s' really runs subject -> object (relation direction): \"%s\"" % (
                        o_lab, "before" if po < ps else "after", s_lab, " (no passive marker)" if po < ps and not passive else " (passive construction)", term, sent[:140])))
    # ---- relation type must be worded in the evidence (association is not causation)
    if anchors and status == "reported" and same_lang and nlib.cjk_ratio(ev_cue) < 0.3 and term in EFFECT_TERMS + ("causes", "prevents", "treats") and term not in ("outperforms", "associated_with", "interacts_with"):
        fam = "|".join(vocab.RELATIONS[k]["syn"] for k in ("increases", "decreases", "activates", "inhibits", "regulates", "causes", "prevents", "treats"))
        found = re.search(fam, ev_cue, re.I)
        assoc = re.search(r"associat|correlat|linked to|relat(?:ed|ion)|co-?occur|covary|consistent with", ev_cue, re.I)
        ver["relation_wording"] = found.group(0) if found else None
        if not found:
            if assoc and term in ("causes", "prevents", "treats", "increases", "decreases"):
                issues.append(sev("relation_type", "error", "relation '%s' asserts an effect but the evidence only states an association/consistency ('%s'): use associated_with / consistent_with, or cite evidence that states the effect (relation type error)" % (term, assoc.group(0))))
            else:
                issues.append(sev("relation_unsupported", "warn", "no wording for '%s' in the evidence sentence(s) (looked for: %s): the relation may be inferred rather than stated -> evtype=indirect or another relation" % (term, vocab.RELATIONS[term]["syn"][:60])))
    # ---- atomicity
    sig = []
    vpos = sorted((m.start(), k) for k in EFFECT_TERMS for m in vocab.REL_PATTERNS[k].finditer(text))
    verbs = sorted({k for _, k in vpos})
    coordinated = any(k2 != vpos[0][1] and re.search(r"[,;]|\b(?:and|but|while|whereas|although)\b", text[vpos[0][0]:p2]) for p2, k2 in vpos[1:]) if vpos else False
    if len(verbs) >= 2 and coordinated:
        sig.append("several coordinated relation verbs (%s)" % ", ".join(verbs))
    if COORD.search(text):
        sig.append("coordination (%s)" % COORD.search(text).group(0).strip())
    if nlib.wcount(text) > 45:
        sig.append("%d words" % nlib.wcount(text))
    distinct_units = {m.group(0).lower() for m in re.finditer(r"\d+(?:\.\d+)?\s*(?:%|percent|fold|x|ms|s|kg|mg|mm|cm|km|Hz|GHz|K|BLEU|points?|days?|years?|months?)\b", text)}
    if len(distinct_units) >= 3:
        sig.append("%d different quantities" % len(distinct_units))
    ver["atomicity_signals"] = sig
    if status == "reported" and sig:
        hard = (len(verbs) >= 2 and coordinated and COORD.search(text)) or nlib.wcount(text) > 70
        issues.append(sev("atomicity", "error" if hard else "warn", "claim is not atomic (%s): split it so that each claim is one subject - relation - object that can be judged true/false on its own" % "; ".join(sig)))
    # ---- over-broad wording and dropped scope
    if anchors and text and status == "reported":
        uni = [m.group(0).lower() for m in vocab.UNIVERSAL.finditer(text + " " + s_lab + " " + o_lab)]
        uni = [w for w in uni if not re.search(r"\b" + re.escape(w) + r"\b", ev_full, re.I)]
        if uni:
            issues.append(sev("overbroad", "warn", "quantifier(s) in the claim that the evidence does not use: %s (over-broad claim)" % ", ".join(sorted(set(uni))[:3])))
        oc = [m.group(0).lower() for m in nlib.OVERCLAIM.finditer(text)]
        oc = [w for w in oc if nlib.stem(w) not in set(nlib.tokens(ev_full)) and not re.search(r"\b" + re.escape(w) + r"\b", ev_full, re.I)]
        if oc:
            issues.append(sev("overclaim", "warn", "strength word(s) not in the evidence: %s" % ", ".join(sorted(set(oc))[:3])))
        covered = nlib.content_words(" ".join((text, cond, s_lab, o_lab)))
        dropped = []
        for m in vocab.SCOPE.finditer(ev_cue):
            ph = m.group(0)
            pw = nlib.content_words(ph)
            if pw and len(pw & covered) / len(pw) < 0.5:
                dropped.append(ph.strip())
        ver["scope_dropped"] = dropped[:3]
        if dropped:
            issues.append(sev("scope_dropped", "warn", "the evidence limits the statement (%s) but claim/cond do not say so: put it in `cond:`" % "; ".join('"%s"' % x[:60] for x in dropped[:2])))
    # ---- modality / polarity / strength
    hedge_ev = vocab.HEDGE_WORD.search(ev_cue) or nlib.HEDGE.search(ev_cue)
    hyp_ev = vocab.HYPOTHESIS.search(ev_cue)
    comp_mod = "hypothesis" if hyp_ev else ("hedged" if hedge_ev else "asserted")
    declared_mod = (c.get("modality") or "").lower()
    ver["modality"] = comp_mod
    ver["hedge_cue"] = (hyp_ev or hedge_ev).group(0) if (hyp_ev or hedge_ev) else None
    if declared_mod and declared_mod not in vocab.MODALITIES:
        issues.append(sev("modality_value", "error", "modality must be one of %s" % ", ".join(vocab.MODALITIES)))
    elif declared_mod == "asserted" and comp_mod != "asserted" and anchors:
        issues.append(sev("modality", "warn", "the evidence is hedged ('%s') but modality=asserted: use modality=%s" % (ver["hedge_cue"], comp_mod)))
    if anchors and text and status == "reported" and ver["hedge_cue"] and nlib.STRONG.search(text) and not re.search(nlib.STRONG.search(text).group(0), ev_full, re.I):
        issues.append(sev("strength", "warn", "evidence is hedged ('%s') but the claim states it as established ('%s')" % (ver["hedge_cue"], nlib.STRONG.search(text).group(0))))
    pol = (c.get("polarity") or "positive").lower()
    if pol not in vocab.POLARITIES:
        issues.append(sev("polarity_value", "error", "polarity must be positive or negative"))
        pol = "positive"
    if anchors and status == "reported" and same_lang:
        cue_neg = re.sub(r"\b(?:can(?:no|\s?no)t|could\s+not|can\s+not)\s+(?:be\s+)?(?:exclude[d]?|rule[d]?\s+out|ruled\s+out)\b", " ", ev_cue, flags=re.I)  # 'cannot exclude' is a hedge, not a negation
        neg_ev = nlib.NEGATION.search(cue_neg) or vocab.NEG_EXTRA.search(cue_neg)
        neg_cl = nlib.NEGATION.search(text + " " + cond)
        ver["negation_in_evidence"] = neg_ev.group(0) if neg_ev else None
        if neg_ev and pol == "positive" and not neg_cl:
            issues.append(sev("polarity", "warn", "the evidence contains a negation ('%s') but the claim is positive: set polarity=negative or reword (polarity error)" % neg_ev.group(0)))
        if pol == "negative" and not neg_ev and best:
            issues.append(sev("polarity", "warn", "polarity=negative but the evidence has no negation cue: check"))
    # ---- attribution: this paper or a cited work
    cites, comp_origin = [], "this_paper"
    if anchors and best:
        sent = best[0][1]
        cites_all = srcmeta.resolve_citations(sent, refs, vocab.CITE_NUM, vocab.CITE_AUTHOR)
        has_self = bool(vocab.SELF.search(sent))
        # a citation attributes the CLAIM to the cited work only when it closes the sentence or follows the subject; a citation after a compared baseline does not
        sub_start = sub_end = None
        if s_lab:
            sub_start = label_pos_text(s_lab, sent)
            sub_end = (sub_start + len(s_lab) + 25) if sub_start is not None else None
        cites = []
        for m in list(vocab.CITE_NUM.finditer(sent)) + list(vocab.CITE_AUTHOR.finditer(sent)):
            if m.end() >= len(sent.rstrip(" .;")) - 3 or (sub_end is not None and sub_start <= m.start() <= sub_end):
                cites += [x for x in cites_all if x["marker"] == m.group(0).strip(" (")]
        if cites and not has_self:
            comp_origin = "cited"
        elif vocab.BACKGROUND.search(sent) and not has_self:
            comp_origin = "background"
    ver["origin"] = comp_origin
    ver["citations"] = cites[:4]
    decl_origin = (c.get("origin") or "").strip().lower()
    decl_kind = "cited" if decl_origin.startswith("cited") else decl_origin
    if decl_kind and decl_kind not in ("this_paper", "cited", "background"):
        issues.append(sev("origin_value", "error", "origin must be this_paper, cited[:ref] or background"))
    elif anchors and status == "reported":
        if decl_kind in ("", "this_paper") and comp_origin in ("cited", "background") and ver.get("citations") is not None:
            issues.append(sev("attribution", "warn", "the evidence sentence cites other work (%s): the claim may belong to the cited work, not to this paper - set origin=cited and name it, or origin=this_paper if the authors own it" % (", ".join(x["marker"] for x in cites[:3]) or "background wording")))
        if decl_kind == "cited" and not cites:
            issues.append(sev("attribution", "warn", "origin=cited but the evidence sentence has no recognisable citation marker"))
    secs = {s["id"]: s for s in d["sections"]}
    sec_titles = " ".join((secs.get(byu[x[0]]["section"]) or {}).get("path", "") for x in anchors)
    if anchors and re.search(r"\b(introduction|related work|background|literature)\b", sec_titles, re.I) and (c.get("type") or "finding") == "finding" and decl_kind in ("", "this_paper") and not (best and vocab.SELF.search(best[0][1])):
        issues.append(sev("attribution", "warn", "a finding anchored in an introduction/related-work section without 'we/this paper': probably background from other work (origin=background)"))
    # ---- evidence minimality and type
    comp_type = "direct"
    if anchors and status == "reported":
        claim_terms = cw | set(label_stems(s_lab)) | set(label_stems(o_lab))
        sents = []
        for uid, a_, b_ in anchors:
            u = byu[uid]
            for i in range((a_ or 1), (b_ or len(u["sentences"])) + 1) if a_ else range(1, len(u["sentences"]) + 1):
                sents.append((uid, i, u["sentences"][i - 1]))
        cover = [(uid, i, len(claim_terms & nlib.content_words(s_)) / (len(claim_terms) or 1)) for uid, i, s_ in sents]
        top = max((x[2] for x in cover), default=0)
        both = any(ent_cover(s_lab, s_) >= 0.34 and ent_cover(o_lab, s_) >= 0.34 for _, _, s_ in sents) if (s_lab and o_lab and val is None) else True
        comp_type = "direct" if both and top >= 0.4 else "indirect"
        ver["best_sentence_cover"] = round(top, 2)
        # greedy cover: which anchored sentences add nothing
        remain, used = set(claim_terms), []
        claim_nums = set(nlib.numbers(text + " " + cond))
        pool_ = list(sents)
        while pool_ and remain:
            def gain_of(x):
                return wsum(d, remain & nlib.content_words(x[2])) + 1.5 * len(claim_nums & set(nlib.numbers_ev(x[2])))
            pool_.sort(key=lambda x: -gain_of(x))
            top_ = pool_.pop(0)
            gain = remain & nlib.content_words(top_[2])
            if not gain or gain_of(top_) <= 0:
                break
            used.append((top_[0], top_[1]))
            remain -= gain
            if wsum(d, remain) <= 0.25 * wsum(d, claim_terms):  # the rest is function-like wording: stop adding sentences
                break
        extra = [(uid, i) for uid, i, _ in sents if (uid, i) not in used]
        ver["minimal_anchors"] = ["%s.%d" % x for x in sorted(used)]
        if extra and len(sents) > 1 and used:
            issues.append(sev("evidence_not_minimal", "warn", "anchored sentence(s) %s add nothing to the claim: the minimal sufficient evidence is %s" % (", ".join("%s.%d" % x for x in extra[:4]), ", ".join("%s.%d" % x for x in sorted(used)[:4]))))
        elif any(a_ is None for _, a_, _ in anchors) and sents and used and len(used) <= 2 and len(sents) >= 4:
            issues.append(sev("evidence_not_minimal", "warn", "unit-level anchor with %d sentences: narrow it to %s (sentence-level anchors make the evidence minimal and exactly locatable)" % (len(sents), ", ".join("%s.%d" % x for x in sorted(used)))))
    ver["evtype"] = comp_type
    decl_type = (c.get("evtype") or "").lower()
    if decl_type and decl_type not in ("direct", "indirect"):
        issues.append(sev("evtype_value", "error", "evtype must be direct or indirect"))
    elif decl_type == "direct" and comp_type == "indirect" and status == "reported":
        issues.append(sev("evidence_type", "warn", "evtype=direct but no single anchored sentence contains subject, object and the claim's content: the claim is an inference from several statements (indirect)"))
    # ---- identifiers
    doc_text = " ".join(u["text"] for u in d["units"])
    for role, key in (("subject", "s_id"), ("object", "o_id")):
        cid = (c.get(key) or "").strip()
        if cid:
            if not vocab.curie_iri(cid):
                issues.append(sev("identifier", "warn", "%s identifier '%s' is not a recognised CURIE (prefixes: %s): exported without an IRI" % (role, cid, ", ".join(sorted(vocab.ID_PATTERNS)[:12]) + ", ...")))
            elif cid.split(":", 1)[1].lower() not in doc_text.lower():
                issues.append(sev("identifier_origin", "warn", "%s identifier %s does not occur in the paper: it comes from the claim author's knowledge, not from the source (exported with origin=asserted)" % (role, cid)))
    # ---- duplicates
    if text:
        for o in others:
            if o.get("id") == c.get("id") or (o.get("polarity") or "positive") != pol or nlib.norm(o.get("cond", "")) != nlib.norm(cond):
                continue
            same = o.get("s") and s_lab and nlib.norm(o["s"]) == nlib.norm(s_lab) and nlib.norm(o.get("o", "")) == nlib.norm(o_lab) and vocab.resolve_relation(o.get("p", ""))[0] == term
            ow = nlib.content_words((o.get("text") or ""))
            if same or (cw and ow and len(cw & ow) / len(cw | ow) >= 0.8):
                issues.append(sev("duplicate", "warn", "near-duplicate of %s: merge them (`merge`) so one claim carries all its evidence" % o.get("id")))
                break
    if c.get("type") and c["type"] not in vocab.CLAIM_TYPES:
        issues.append(sev("claim_type", "warn", "type '%s' not in %s" % (c["type"], ", ".join(vocab.CLAIM_TYPES))))
    # ---- confidence (extraction fidelity), computed from the checks above
    kinds = {i["kind"] for i in issues if i["severity"] != "error"}
    basis = []
    if "verified" in qres and "missing" not in qres:
        basis.append("quote verified verbatim")
    elif anchors and not quotes:
        basis.append("no author quote: span taken from the anchored sentence")
    basis.append("evidence is %s" % comp_type)
    basis.append("numbers present in evidence" if nums and ver["numbers"] == "ok" else ("numbers NOT all in evidence" if nums else "no numbers"))
    if ver["hedge_cue"]:
        basis.append("evidence hedged ('%s') -> modality=%s" % (ver["hedge_cue"], comp_mod))
    low = {"support", "direction", "polarity", "attribution", "quote_approx", "evidence_type"} & kinds
    mid = {"relation_unsupported", "scope_dropped", "evidence_not_minimal", "overbroad", "overclaim", "atomicity", "relation_free_text", "relation_mapped", "entity_not_in_evidence", "identifier_origin", "identifier", "strength", "modality", "entity_list", "duplicate"} & kinds
    if low or ver["support"] < 0.4 or status != "reported":
        level = "low"
    elif mid or comp_type == "indirect" or "verified" not in qres and quotes or (not quotes and not any(a_ for _, a_, _ in anchors)):
        level = "medium"
    else:
        level = "high"
    if low:
        basis.append("lowered by: " + ", ".join(sorted(low)))
    if mid:
        basis.append("reduced by: " + ", ".join(sorted(mid)))
    ver["confidence"] = {"level": level, "basis": basis}
    decl = (c.get("conf") or "").lower()
    order = {"low": 0, "medium": 1, "high": 2}
    if decl in order and order[decl] > order[level]:
        issues.append(sev("confidence", "warn", "declared confidence %s is higher than the computed %s (%s): the computed value is exported" % (decl, level, "; ".join(basis[-2:]))))
    return issues, ver


def status_of(issues):
    if any(i["severity"] == "error" for i in issues):
        return "error"
    return "warn" if issues else "ok"
