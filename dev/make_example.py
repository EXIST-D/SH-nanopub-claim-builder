#!/usr/bin/env python3
"""Regenerate submission/examples/example_output/ and examples/minimal-example.md from REAL runs of the tool on the fictional example paper."""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "submission")
NPB = os.path.join(ROOT, "scripts", "npb.py")
W = os.path.join(HERE, "..", "work", "example_work")
OUT = os.path.join(ROOT, "examples", "example_output")
EX = os.path.join(ROOT, "examples")
shutil.rmtree(W, ignore_errors=True)
shutil.rmtree(OUT, ignore_errors=True)


def run(*args, stdin=None, cut=None):
    r = subprocess.run([sys.executable, "-W", "ignore", NPB, *args], input=stdin, capture_output=True, text=True, cwd=os.path.join(ROOT, "examples"))
    out = (r.stdout + r.stderr).strip().replace("../../work/example_work", "W").replace("../../work/example_flawed", "W2")
    if cut:
        out = "\n".join(l[:cut] for l in out.splitlines())
    return out


md = ["# Minimal example (real output of the tool on a FICTIONAL paper)", "",
      "`mini_paper.md` is an invented paper written for this example: its findings, numbers and DOI are not real. Everything below is the unedited output of the commands "
      "(long lines shortened with `...`). `example_output/` holds the files `assemble` wrote. Nothing here is a result of a platform case.", ""]
steps = [("1. Parse the paper into evidence units and source metadata", ["prepare", "mini_paper.md", "--work", "../../work/example_work"], None, 700),
         ("2. The paper's own sections", ["outline", "../../work/example_work"], None, 160),
         ("3. Decomposition hints for two key sentences", ["atoms", "../../work/example_work", "E008.2", "E005.2"], None, 260),
         ("4. Submit 19 claims (`claims_20.txt`; claim C19 is a deliberate `unsupported` example)", ["ingest", "../../work/example_work", "claims_20.txt"], None, 260),
         ("5. Same tool on 13 deliberately flawed claims (`claims_flawed.txt`): what the checks say", ["ingest", "../../work/example_flawed", "claims_flawed.txt", "-v"], None, 250),
         ("6. What is missing", ["next", "../../work/example_work"], None, 200),
         ("7. Export", ["assemble", "../../work/example_work", "--out", "example_output"], None, 400),
         ("8. Validate the nanopublications", ["validate", "example_output/nanopubs.trig"], None, 200)]
for title, args, stdin, cut in steps:
    if "example_flawed" in " ".join(args):
        run("prepare", "mini_paper.md", "--work", "../../work/example_flawed")
    out = run(*args, stdin=stdin, cut=cut)
    cmd = "python3 scripts/npb.py " + " ".join(a.replace("../../work/example_work", "W").replace("../../work/example_flawed", "W2") for a in args)
    md += ["## " + title, "```bash", cmd, "```", "```text", out, "```", ""]
trig = open(os.path.join(OUT, "nanopubs.trig"), encoding="utf-8").read()
blocks = ["@prefix : " + b for b in trig.split("@prefix : ")[1:]]
np1 = next(b for b in blocks if "The YAP inhibitor verteporfin reduces nodule area" in b)
np1 = np1.split("\n\n@prefix")[0]
md += ["## 9. One nanopublication (TriG) - claim C7, a measured effect with a quote located by character offsets", "```turtle", np1.strip(), "```", "",
       "## What to look at", "- `example_output/nanopubs.json`: one record per claim (assertion with subject / relation / object / polarity / conditions, evidence with page / section / bbox / offsets, source, attribution, confidence with basis, checks, review flags).",
       "- `example_output/nanopubs.trig`: the same claims as nanopublications; `claims.csv`: flat table; `review_checklist.md`: what a person must confirm; `check_report.json`: counts and issues; `result.json`: contract-shaped result.", ""]
open(os.path.join(EX, "minimal-example.md"), "w", encoding="utf-8").write("\n".join(md))
print("example written; files:", sorted(os.listdir(OUT)))
