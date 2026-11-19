#!/usr/bin/env python3
"""Evaluation of two checker components on the public SciFact data (allenai/scifact, CC BY-NC 2.0; claims written from citation sentences, with
abstract-sentence rationales annotated by experts).  Data: dev/ref/scifact/data/{corpus.jsonl,claims_dev.jsonl,claims_train.jsonl}

1. Minimal evidence: for every claim that has rationale sentences, the claim is bound to the WHOLE abstract as a unit-level anchor and validate_claim() proposes
   `minimal_anchors` (greedy content-word cover). We report hit@1 (best sentence is a gold rationale sentence), recall of gold sentences, mean predicted-set size
   versus gold size, against two baselines: random sentence, and the first sentence.
2. Atomicity: single SciFact claims are atomic by construction -> the share that is flagged is the false-alarm rate; two claims from different abstracts joined with
   ', and' / '; ' / ', while' are compound -> the share flagged is the detection rate.

usage: scifact_eval.py [N]
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "submission", "scripts"))
import claims as C  # noqa: E402
import nlib  # noqa: E402

D = os.path.join(HERE, "ref", "scifact", "data")


def doc_of(abstract_sents, title=""):
    text = " ".join(abstract_sents)
    u = {"id": "E001", "type": "abstract", "text": text, "sentences": abstract_sents, "pages": [1], "page": 1, "bbox": None, "block": "b1", "section": "§abs", "excluded": False, "words": len(text.split())}
    sec = {"id": "§abs", "title": "Abstract", "path": "Abstract", "level": 1, "parent": None, "units": ["E001"], "excluded": False, "optional": True}
    return {"meta": {"lang": "en"}, "units": [u], "sections": [sec], "refs": []}


def main(n_max):
    corpus = {}
    for ln in open(os.path.join(D, "corpus.jsonl"), encoding="utf-8"):
        o = json.loads(ln)
        corpus[str(o["doc_id"])] = o
    claims = []
    for fn in ("claims_dev.jsonl", "claims_train.jsonl"):
        for ln in open(os.path.join(D, fn), encoding="utf-8"):
            o = json.loads(ln)
            if o.get("evidence"):
                claims.append(o)
    rnd = random.Random(3)
    rnd.shuffle(claims)
    claims = claims[:n_max]
    hit1 = rec = tot = pred_sz = gold_sz = rnd_hit = first_hit = n = 0
    for o in claims:
        for did, ev in o["evidence"].items():
            doc = corpus.get(did)
            if not doc:
                continue
            gold = {s for e in ev for s in e["sentences"]}
            if not gold:
                continue
            d = doc_of(doc["abstract"])
            issues, ver = C.validate_claim(d, __import__("nlib").BM25([""]) if False else _BM(d), {"id": "C1", "text": o["claim"], "s": "x", "p": "other", "o": "y", "ev": "E001", "quote": "", "status": "reported"}, [], [])
            pred = {int(x.split(".")[1]) - 1 for x in ver.get("minimal_anchors", [])}
            if not pred:
                continue
            n += 1
            best = ver["minimal_anchors"][0]
            hit1 += (int(best.split(".")[1]) - 1) in gold
            rec += len(pred & gold) / len(gold)
            pred_sz += len(pred)
            gold_sz += len(gold)
            rnd_hit += rnd.randrange(len(doc["abstract"])) in gold
            first_hit += 0 in gold
    print("minimal evidence on SciFact (%d claim-abstract pairs with rationale sentences)" % n)
    print("  hit@1 (top proposed sentence is a gold rationale): %.2f | random sentence %.2f | first sentence %.2f" % (hit1 / n, rnd_hit / n, first_hit / n))
    print("  recall of gold rationale sentences by the proposed minimal set: %.2f | proposed set %.2f sentences vs gold %.2f sentences | whole abstract would be ~%.1f sentences" % (rec / n, pred_sz / n, gold_sz / n, sum(len(corpus[d]["abstract"]) for o in claims for d in o["evidence"] if d in corpus) / max(1, n)))
    # ---- atomicity
    allc = [o["claim"] for o in claims if len(o["claim"].split()) >= 6]
    base = sum(1 for t in allc if _atomic_flag(t))
    pairs = []
    for i in range(0, min(len(allc) - 1, 600), 2):
        a, b = allc[i].rstrip("."), allc[i + 1].rstrip(".")
        pairs.append(a + [", and ", "; ", ", while ", ", but "][(i // 2) % 4] + b[:1].lower() + b[1:] + ".")
    det = sum(1 for t in pairs if _atomic_flag(t))
    print("atomicity: single claims flagged (false alarms) %d/%d = %.1f%% | joined compound claims flagged %d/%d = %.1f%%" % (base, len(allc), 100.0 * base / len(allc), det, len(pairs), 100.0 * det / len(pairs)))


def _BM(d):
    return nlib.BM25([u["text"] for u in d["units"]])


def _atomic_flag(text):
    d = doc_of([text])
    iss, _ = C.validate_claim(d, _BM(d), {"id": "C1", "text": text, "s": "x", "p": "other", "o": "y", "ev": "E001", "quote": "", "status": "reported"}, [], [])
    return any(i["kind"] == "atomicity" for i in iss)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 400)
