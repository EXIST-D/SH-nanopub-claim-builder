---
name: nanopub-claim-builder
description: Turn the key conclusions of a research paper (PDF, Word, Markdown/text, LaTeX, JSON; also a pasted paragraph) into atomic, evidence-bound, source-traceable nanopublication claims and export them as machine-readable files (nanopublication TriG with head/assertion/provenance/pubinfo graphs, JSON, JSONL, CSV). Each claim is one subject - relation - object with conditions, polarity, modality (asserted/hedged/hypothesis) and attribution (this paper or a cited work); it is bound to the minimal evidence quote with page, section, bbox and exact character offsets, and the source gets title/authors/year/DOI/arXiv/version/file hash with the origin of every value. Every claim is verified by script when submitted (verbatim quote, numbers, subject/object really in the evidence, relation direction and type, atomicity, dropped scope, over-broad wording, hedge/negation, cited-vs-own, minimal evidence, duplicates), and the export is validated against the nanopublication well-formedness rules. Use whenever a task asks to split a conclusion/paragraph into verifiable claims, bind claims to evidence and source, build nanopublications or knowledge units, or export claims in a form a program can read.
---

# nanopub-claim-builder

You read the paper and decide what its key claims are. The tool makes every claim **checkable and exportable**: it cuts the paper into
addressable evidence units (`E012`, sentences `E012.3`, with page and bbox), shows how a sentence decomposes, **verifies each claim the moment
you submit it**, keeps source metadata honest (every value says where it came from; unknown stays unknown), and writes nanopublications
(`nanopubs.trig`), `nanopubs.json`, `nanopubs.jsonl`, `claims.csv`, a review checklist and `result.json`.

## When to use
A paper (or a paragraph / section of it) must become atomic claims with evidence and source, nanopublications, knowledge units, a claim table,
or a machine-readable export - and each claim must be traceable to the exact place in the source. English and Chinese papers. Not for free-form
chat answers that need no evidence.

## Quick start (`SK` = directory of this file, installed as `/skills/weekly-skill`; `W=/app/work/np`)
```bash
python3 $SK/scripts/npb.py prepare /input/<file> --work $W --case /input/case.json   # or: prepare --work $W --case /input/case.json (finds the file / text itself)
python3 $SK/scripts/npb.py outline $W                    # the paper's own sections
python3 $SK/scripts/npb.py candidates $W                 # sentences that look like key conclusions (not yet covered)
python3 $SK/scripts/npb.py atoms $W E104.1 E105.1         # decomposition hints: clauses, relation verbs, entities, scope, numbers, hedges, citations
python3 $SK/scripts/npb.py read $W --sec 3 --sentences    # read with unit / sentence ids
python3 $SK/scripts/npb.py ingest $W <<'EOF'              # submit claims (format below): verified immediately
=== claim
...
EOF
python3 $SK/scripts/npb.py next $W                       # failing claims, missing metadata, uncovered key sentences
python3 $SK/scripts/npb.py assemble $W --out /app/output --case /input/case.json     # run after the first accepted batch AND at the end
python3 $SK/scripts/npb.py validate /app/output/nanopubs.trig
```
Also: `find $W "query"`, `meta $W [--set title=...] [--crossref]`, `merge $W C1 C2`, `drop $W C1`, `search /app/output "query"`,
`assemble W1 W2 --out OUT` (several papers in one export). `prepare` options: `--pages 3-9`, `--lang zh|en`, `--ocr auto|off|force`.

## Procedure (12-18 model requests for a typical case)
1. **Read the task** (`/input/case.json`, `task.md`): which paper, which paragraph / conclusion, how many claims, language, exact
   `output_contract`. `prepare` prints the task text, units, sections, parsed reference count and the source metadata it found or could not find.
2. **Choose the key claims.** If the task names a paragraph/section/conclusion, use exactly that scope; otherwise take the abstract's results,
   the main results and the conclusions (`candidates`). Typically 10-25 claims. Do not pad with trivia and do not skip the paper's headline results.
3. **Decompose** each key sentence with `atoms` (it lists clause splits, relation verbs, entity candidates, scope phrases, numbers, hedges,
   negations, citations). One claim = one subject - relation - object that can be judged true or false on its own.
4. **Write claims** in the block format below, 10-20 per `ingest`. Fix **only the failing claims** (resubmit with `id=`); warnings are things to look at - do not
   delete a warning-carrying claim to look clean, fix the cause or keep it with a `note:`.
5. **Source metadata**: `meta $W`. Fields marked low confidence or missing: read the first page (`read $W --page 1`) and set them with `meta --set key=value`
   only if the text shows them; otherwise they stay unknown (exported as unknown, listed in `uncertainty`). Never invent title/authors/year/DOI.
6. **Assemble** early (an honest partial result exists after the first batch) and again at the end; then `validate` the TriG. If `result.json` reports
   unfilled contract fields, put your values in `/app/work/answers.json` and re-run with `--answers`.
7. **Report honestly** in the final answer: status (`success` only if claims exist, none is rejected, TriG is valid, nothing essential is missing; else `partial` with the reasons),
   what is uncertain (`low` confidence claims, `unsupported` claims, missing metadata, parser warnings), where a human should look (`review_checklist.md`).

## Claim block format (no JSON escaping)
```
=== claim id=C1 status=reported                          <- id optional (reuse it to replace a claim); status: reported|unsupported|conflict|unclear|not_reported
text: One self-contained sentence stating the claim (no "it", "this", "these"; all entities named).
s: subject label                                          <- ONE entity (copy its name from the evidence; optional s_id: NCBIGene:7157 / CHEBI:15377 / DOI:... )
p: increases                                              <- controlled relation (list below) - free text allowed but exported as v:other
o: object label                                           <- ONE entity or a value (value: 2.3 / unit: fold for numbers)
cond: conditions that make it true: dataset, species, dose, sample, version, "n = 6", margin of a comparison
ev: E104.1, E105.1                                        <- evidence anchors: sentence E104.1, unit E104, range E104-E106 (required when status=reported)
quote: "verbatim snippet copied from the evidence"        <- minimal span; verified by script, exact offsets are exported; several quotes separated by |||
polarity: positive | negative                             <- negative = the paper says the relation does NOT hold
modality: asserted | hedged | hypothesis                  <- default is derived from the evidence wording (may/suggest/propose ...)
origin: this_paper | cited | background                   <- who owns the claim; cited claims are linked to the reference list
evtype: direct | indirect                                 <- direct = one stated sentence; indirect = inferred from several statements (cite them all)
type: finding | method | data | definition | background | limitation | hypothesis
conf: low | medium | high   basis: why                    <- optional; the exported confidence is COMPUTED and never higher than the checks allow
note: why uncertain / how a conflict was resolved         <- required for status other than reported (say where you searched)
derived: how a number was computed                        <- only for computed numbers
tags: lower-case, retrieval, tags
```
JSONL alternative: `{"text":"...","s":"..","p":"..","o":"..","ev":"E104.1","quote":"..."}`; or `ingest $W file.txt`.

## Relation vocabulary (`p:`; exact definitions and ontology mappings in `references/relations.md`)
`increases decreases activates inhibits regulates causes prevents treats associated_with interacts_with part_of located_in has_phenotype has_value outperforms
consistent_with differs_from uses evaluated_on trained_on produces requires enables predicts detects is_a derived_from other`.
Association is not causation: `associated_with` for correlations, `causes` only when the evidence says so. Comparisons: subject is the one that is higher / better.
"Not" is `polarity: negative`, never a new relation. Numbers: `has_value` with `o:` = the number and `value:` / `unit:`.

## What the checker enforces (details and blind spots: `references/checks.md`)
- **Errors (claim not exported)**: missing s/p/o/text, no evidence, unknown / excluded anchor, quote not verbatim in the paper, number not in the cited evidence, subject/object not
  in the evidence, pronoun as subject, causal relation backed only by an association sentence, claim wording unrelated to the evidence, several coordinated relations in one claim.
- **Warnings (exported, flagged for review, lower confidence)**: not atomic, over-broad quantifier, dropped scope (the evidence limits the statement, the claim does not), hedge or negation not
  reflected, relation direction reversed, claim may belong to a cited work, evidence not minimal, indirect evidence, free-text relation, duplicates, identifier not in the paper.
- **Exports**: each reported claim becomes one nanopublication (TriG graphs `Head`, `assertion`, `provenance`, `pubinfo`); `assemble` validates the TriG against the well-formedness
  rules and checks that every evidence locator reproduces its quote from the stored unit text.

## Exceptions
| Situation | Behaviour | You do |
|---|---|---|
| scanned / image-only PDF | OCR (rapidocr or tesseract) if installed; low-confidence text is flagged | say OCR was used; no OCR engine -> report the pages as not processed |
| encrypted / corrupt / not a PDF | `prepare` stops with the parser's message | report `failed`/`refused`; do not guess content |
| claim has no support in the paper | `status=unsupported` + `note:` (where you searched) | keep it as unsupported; it is listed, not exported to TriG |
| paper contradicts itself | `status=conflict`, cite both places in `ev:` | explain in `note:` |
| evidence is in a figure / table image | table text is citable; numbers inside images are not | do not read numbers from memory; mark `unclear` |
| claim belongs to a cited paper | `origin=cited`; the reference entry (and DOI) is attached | do not present it as a finding of this paper |
| title / authors / year / DOI absent | field stays unknown, listed in `uncertainty` | never invent; ask `meta --crossref` only if a DOI is known and network is available |
| very long paper | `outline`, `candidates`, `--sec` reading | cover headline results first, `assemble`, report the rest as not covered |
| several papers | one `prepare` per paper (`--work W1`, `--work W2`), then `assemble W1 W2` | claims carry their own source |

## Dependencies
Python 3.8+; the claim workflow uses only the standard library. PDFs use the bundled `scripts/parse_pdf.py` (needs `pymupdf`, falls back to `pdfplumber` / `pypdf`); scans need
`rapidocr` or `tesseract`. Markdown, text, LaTeX, `.docx` and `.json` need nothing extra. No network is needed at run time (`meta --crossref` is optional).

## Honesty rules (hard)
Never invent text, numbers, pages, identifiers, citations or bibliographic data; never report `success` with rejected claims, invalid TriG or missing essentials; never present a cited
claim as the paper's own; never raise a confidence the checks lowered; say what the checks cannot prove (the review checklist lists what a human must confirm); never state benchmark
scores - the platform records them. Exported IRIs are local placeholders: nanopublications are neither minted nor signed (no trusty URIs).

More: `README.md` (guide and measured results), `references/field-dictionary.md`, `references/relations.md`, `references/checks.md`, `references/failure-modes.md`,
`references/method-notes.md`, `examples/` (fictional paper, 19 claims, 13 flawed claims, real run output).
