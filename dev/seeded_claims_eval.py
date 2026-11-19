#!/usr/bin/env python3
"""Seeded-defect evaluation of the claim verifier (development tool, not part of the Skill runtime).

Takes finished work directories (units.json + claims.json written by `npb.py ingest` from hand-written, correct claims), injects ONE typical defect at a
time into otherwise correct claims, runs the same validate_claim() that `ingest` uses, and reports how often the defect is caught (any issue / error level).
Also reports the false-alarm level on the unmodified claims.

usage: seeded_claims_eval.py WORK_DIR [WORK_DIR ...]
"""
import copy
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "submission", "scripts"))
import claims as C  # noqa: E402
import npb  # noqa: E402
import nlib  # noqa: E402
import units as U  # noqa: E402


def run(works):
    rnd = random.Random(7)
    rows = {}
    base = {"n": 0, "err": 0, "warn": 0}

    def tally(name, cid_ok, iss):
        r = rows.setdefault(name, [0, 0, 0])
        r[0] += 1
        r[1] += bool(iss)
        r[2] += any(i["severity"] == "error" for i in iss)

    for work in works:
        d, claimsd = npb.load(work)
        bm = npb.index(d)
        refs = d.get("refs", [])
        pool = [u for u in d["units"] if not u["excluded"] and u["type"] in ("paragraph", "list_item") and len(u["text"].split()) > 25]
        items = [c for c in claimsd.values() if c["status"] == "reported"]

        def val(c, mod):
            m = dict(c)
            m.update(mod)
            m["quote"] = " ||| ".join(m["quote"]) if isinstance(m.get("quote"), list) else m.get("quote", "")
            others = [v for k, v in claimsd.items() if k != c["id"]]
            return C.validate_claim(d, bm, m, others, refs)[0]

        def other_unit(c):
            cur = {a[0] for a in U.parse_anchors(c["ev"])[0]}
            secs = {u["section"] for u in d["units"] if u["id"] in cur}
            cand = [u for u in pool if u["id"] not in cur and u["section"] not in secs]
            return rnd.choice(cand) if cand else None

        for c in items:
            iss = val(c, {})
            base["n"] += 1
            base["err"] += any(i["severity"] == "error" for i in iss)
            base["warn"] += bool(iss)
            mods = {}
            if c["quote"]:
                q = c["quote"][0].split()
                if len(q) >= 5:
                    q2 = list(q)
                    q2[len(q2) // 2] = "remarkably"
                    q2[-1] = "universally"
                    mods["fabricated quote (2 words changed)"] = {"quote": [" ".join(q2)]}
                mods["paraphrase passed off as quote"] = {"quote": ["the approach was clearly shown to perform better than every competing method in all settings"]}
            u = other_unit(c)
            if u:
                mods["anchor points to another section (with quote)"] = {"ev": u["id"]}
                mods["anchor points to another section (no quote)"] = {"ev": u["id"], "quote": []}
            m = re.search(r"(?<![\w.])\d+\.\d+|(?<![\w.])\d{2,}", c["text"])
            if m:
                old = m.group(0)
                new = old[:-1] + str((int(old[-1]) + 3) % 10)
                mods["number changed in the claim text"] = {"text": c["text"].replace(old, new, 1), "cond": c["cond"].replace(old, new, 1)}
            mods["evidence anchor deleted"] = {"ev": ""}
            anc = U.parse_anchors(c["ev"])[0]
            if anc:
                ids = [x["id"] for x in d["units"]]
                k = ids.index(anc[0][0])
                extra = [i for i in ids[max(0, k - 1):k + 3] if i not in {a[0] for a in anc} and not next(x for x in d["units"] if x["id"] == i)["excluded"]][:2]
                if extra:
                    mods["unneeded evidence added (not minimal)"] = {"ev": c["ev"] + ", " + ", ".join(extra)}
            others = [x for x in pool if x["id"] not in {a[0] for a in U.parse_anchors(c["ev"])[0]}]
            if others:
                o2 = rnd.choice(others)
                words = re.findall(r"[A-Z][A-Za-z0-9-]{3,}", o2["text"])
                if words:
                    mods["subject replaced by an entity from elsewhere"] = {"s": words[0]}
                    mods["object replaced by an entity from elsewhere"] = {"o": words[-1]}
            if C.vocab.RELATIONS[C.vocab.resolve_relation(c["p"])[0]]["directional"] and c["s"] and c["o"] and C.vocab.resolve_relation(c["p"])[0] in ("increases", "decreases", "causes", "inhibits", "activates", "outperforms"):
                mods["subject and object swapped (direction error)"] = {"s": c["o"], "o": c["s"]}
            mods["polarity flipped to negative"] = {"polarity": "negative"} if (c.get("polarity") or "positive") == "positive" else {"polarity": "positive"}
            if c["cond"]:
                mods["conditions / scope removed"] = {"cond": ""}
            mods["universal quantifier added ('in all cases')"] = {"text": c["text"].rstrip(".") + " in all cases, always."}
            mods["relation changed to 'causes' (association/causation)"] = {"p": "causes"} if c["p"] not in ("causes",) else None
            mods["relation changed to 'treats'"] = {"p": "treats"}
            u2 = other_unit(c)
            if u2:
                mods["compound claim (two claims joined)"] = {"text": c["text"].rstrip(".") + ", and " + (u2["sentences"][0][:1].lower() + u2["sentences"][0][1:]).rstrip(".") + " while the model increases and decreases the rate."}
            mods["text replaced by an unrelated sentence"] = {"text": u["sentences"][0]} if u and u["sentences"] else None
            for name, mod in mods.items():
                if mod is None:
                    continue
                tally(name, True, val(c, mod))
    print("claims checked: %d | unmodified claims: error-level false alarms %d (%.0f%%), any warning %d (%.0f%%)" % (base["n"], base["err"], 100.0 * base["err"] / base["n"], base["warn"], 100.0 * base["warn"] / base["n"]))
    print("%-58s %6s %9s %11s" % ("injected defect", "cases", "caught", "caught(err)"))
    for name, (n, h, e) in rows.items():
        print("%-58s %6d %8.0f%% %10.0f%%" % (name, n, 100.0 * h / n, 100.0 * e / n))


if __name__ == "__main__":
    run(sys.argv[1:])
