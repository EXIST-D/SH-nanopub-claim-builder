#!/usr/bin/env python3
"""Regression tests (stdlib unittest): python3 dev/test_all.py   (uses submission/examples; no PDF, no network)"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SUB = os.path.join(HERE, "..", "submission")
sys.path.insert(0, os.path.join(SUB, "scripts"))
import export  # noqa: E402
import vocab  # noqa: E402

NPB = os.path.join(SUB, "scripts", "npb.py")
EX = os.path.join(SUB, "examples")

GOOD = """@prefix : <http://example.org/pub1/> .
@prefix ex: <http://example.org/> .
@prefix np: <http://www.nanopub.org/nschema#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
:Head { : a np:Nanopublication . : np:hasAssertion :assertion . : np:hasProvenance :provenance . : np:hasPublicationInfo :pubinfo . }
:assertion { ex:drugA ex:treats ex:diseaseB . }
:provenance { :assertion prov:wasDerivedFrom ex:paper1 . }
:pubinfo { : dct:created "2020-07-10T10:20:22Z"^^xsd:dateTime . }
"""


def npb(*args, stdin=None):
    r = subprocess.run([sys.executable, NPB, *args], input=stdin, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


class Validator(unittest.TestCase):
    def test_wellformed(self):
        self.assertTrue(export.validate_trig(GOOD)["ok"])

    def test_violations(self):
        cases = {"provenance does not refer to assertion": GOOD.replace(":assertion prov:wasDerivedFrom ex:paper1", "ex:x prov:wasDerivedFrom ex:paper1"),
                 "pubinfo does not refer to nanopub": GOOD.replace(": dct:created", "ex:z dct:created"),
                 "two graph roles share an IRI": GOOD.replace("np:hasProvenance :provenance", "np:hasProvenance :assertion"),
                 "missing hasPublicationInfo": GOOD.replace(" : np:hasPublicationInfo :pubinfo .", "")}
        for name, trig in cases.items():
            with self.subTest(name):
                self.assertFalse(export.validate_trig(trig)["ok"], name)

    def test_triples_outside_graph(self):
        self.assertFalse(export.validate_trig(GOOD + "\nex:a ex:b ex:c .\n")["ok"])

    def test_unsupported_syntax_not_invalid(self):
        r = export.validate_trig(GOOD.replace("ex:drugA ex:treats ex:diseaseB .", "ex:drugA ex:treats [ ex:x ex:y ] ."))
        self.assertIsNotNone(r["unsupported"])


class Vocabulary(unittest.TestCase):
    def test_resolve(self):
        self.assertEqual(vocab.resolve_relation("upregulates"), ("increases", True))
        self.assertEqual(vocab.resolve_relation("is associated with"), ("associated_with", True))
        self.assertEqual(vocab.resolve_relation("frobnicates")[0], "other")

    def test_curie(self):
        self.assertEqual(vocab.curie_iri("GO:0006915"), "http://purl.obolibrary.org/obo/GO_0006915")
        self.assertIsNone(vocab.curie_iri("GO:12"))
        self.assertIsNone(vocab.curie_iri("FOO:1"))


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.w = os.path.join(cls.tmp, "w")
        cls.out = os.path.join(cls.tmp, "out")
        rc, _ = npb("prepare", os.path.join(EX, "mini_paper.md"), "--work", cls.w)
        assert rc == 0

    def test_1_ingest_clean_claims(self):
        rc, out = npb("ingest", self.w, os.path.join(EX, "claims_20.txt"))
        self.assertEqual(rc, 0, out)
        self.assertIn("ERROR 0", out)

    def test_2_assemble_and_validate(self):
        rc, out = npb("assemble", self.w, "--out", self.out)
        self.assertEqual(rc, 0, out)
        res = json.loads(out.splitlines()[0])
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["nanopublications"], 18)
        self.assertEqual(res["other_status"], 1)
        self.assertTrue(res["trig_valid"] and res["locators_reproduce_quotes"])
        rc, out = npb("validate", os.path.join(self.out, "nanopubs.trig"))
        self.assertEqual(rc, 0, out)
        rc, out = npb("validate", os.path.join(self.out, "nanopubs.json"))
        self.assertEqual(rc, 0, out)

    def test_3_locators_reproduce_quotes(self):
        j = json.load(open(os.path.join(self.out, "nanopubs.json"), encoding="utf-8"))
        units = {u["id"]: u for u in json.load(open(os.path.join(self.out, "evidence_index.json"), encoding="utf-8"))[0]["units"]}
        for r in j["nanopubs"]:
            for e in r["evidence"]:
                loc = e["locator"]
                self.assertEqual(units[loc["unit"]]["text"][loc["char_start"]:loc["char_end"]], e["quote"])

    def test_4_cited_claims_are_linked_to_references(self):
        j = json.load(open(os.path.join(self.out, "nanopubs.json"), encoding="utf-8"))
        cited = [r for r in j["nanopubs"] if r["attribution"]["origin"] == "cited"]
        self.assertEqual(len(cited), 2)
        self.assertTrue(all(c["attribution"]["cited"] and c["attribution"]["cited"][0]["doi"] for c in cited))

    def test_5_negative_polarity_not_asserted_as_triple(self):
        trig = open(os.path.join(self.out, "nanopubs.trig"), encoding="utf-8").read()
        block = [b for b in trig.split("@prefix : ")[1:] if "does not differ significantly from that on 40 kPa" in b][0]
        self.assertIn('v:polarity "negative"', block)
        self.assertNotIn("v:differs_from <", block)

    def test_6_flawed_claims_are_caught(self):
        w2 = os.path.join(self.tmp, "w2")
        npb("prepare", os.path.join(EX, "mini_paper.md"), "--work", w2)
        rc, out = npb("ingest", w2, os.path.join(EX, "claims_flawed.txt"), "-v")
        self.assertEqual(rc, 2)
        for kind in ("quote_missing", "numbers", "relation_type", "atomicity", "overbroad", "entity_unresolved", "modality", "attribution", "direction",
                     "scope_dropped", "evidence_not_minimal", "duplicate", "anchor_unknown", "no_evidence", "polarity"):
            self.assertIn(kind, out, kind)

    def test_7_status_partial_when_claim_rejected(self):
        w3 = os.path.join(self.tmp, "w3")
        npb("prepare", os.path.join(EX, "mini_paper.md"), "--work", w3)
        bad = "=== claim\ntext: Verteporfin raises nodule area by 90%.\ns: verteporfin\np: increases\no: nodule area\nev: E008.2\nquote: \"raised nodule area by 90%\"\n"
        npb("ingest", w3, stdin=bad)
        rc, out = npb("assemble", w3, "--out", os.path.join(self.tmp, "out3"))
        self.assertEqual(json.loads(out.splitlines()[0])["status"], "failed")

    def test_8_case_contract(self):
        case = os.path.join(self.tmp, "case.json")
        json.dump({"case_id": "t1", "file": os.path.join(EX, "mini_paper.md"), "output_contract": {"fields": ["case_id", "claims", "status", "mystery_field"]}}, open(case, "w"))
        w4 = os.path.join(self.tmp, "w4")
        rc, out = npb("prepare", "--work", w4, "--case", case)
        self.assertEqual(rc, 0, out)
        npb("ingest", w4, os.path.join(EX, "claims_20.txt"))
        rc, out = npb("assemble", w4, "--out", os.path.join(self.tmp, "out4"), "--case", case)
        self.assertEqual(rc, 2)  # the unknown contract field is reported, not invented
        res = json.load(open(os.path.join(self.tmp, "out4", "result.json"), encoding="utf-8"))
        self.assertEqual(res["case_id"], "t1")
        self.assertIsNone(res["mystery_field"])
        self.assertIn("mystery_field", res["_meta"]["unfilled_fields"])
        self.assertEqual(len(res["claims"]), 18)


if __name__ == "__main__":
    unittest.main(verbosity=2)
