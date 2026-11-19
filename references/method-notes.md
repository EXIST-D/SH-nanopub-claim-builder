# Method notes

## Why this design
The four questions of the task map to four mechanisms.
1. **Fine granularity** - a claim is one subject - relation - object with conditions, polarity, modality; `atoms` shows clause splits and relation verbs; the checker rejects claims that bundle several coordinated relations,
   warns on lists of entities, long texts and several quantities, and rejects pronouns as subjects.
2. **Matching** - evidence is addressed by unit and sentence; a quote must occur verbatim in the anchored unit (spacing, hyphenation and ligatures are normalised, words are not), the number tokens must occur in the evidence,
   subject and object must occur in the evidence, the relation must be worded there, and the evidence is compared with the *minimal* sentence set that covers the claim (idf-weighted greedy cover).
3. **Traceability** - every evidence item has unit, sentence, page, bbox, section path and character offsets into the stored unit text; `assemble` re-checks that each locator reproduces its quote; source metadata keeps the origin
   and confidence of every field; the source file is identified by SHA-256; claims taken from cited work are linked to the parsed reference list (DOI when present).
4. **Machine readability** - TriG with the four nanopublication graphs, JSON / JSONL / CSV from the same records, a stdlib validator of the well-formedness rules, controlled relation vocabulary with documented ontology mappings.

## What is computed and what is judged by the model
Computed: units, sentences, offsets, quote and number verification, retrieval hints, relation direction (word order + passive markers), atomicity signals, hedge / negation / universal-quantifier / scope cues, attribution cues,
confidence, identifiers syntax, duplicate detection, exports, validation. Judged by the model: which claims are key, the claim wording, the choice of relation and polarity, conditions.
The checks are lexical and structural: they catch the common errors, not every error (see `checks.md`).

## Confidence
`confidence.level` measures **extraction fidelity** (how well the evidence supports the wording), not scientific truth. `high`: verbatim quote (or sentence anchor), direct evidence, no warning; `medium`: any of scope dropped,
non-minimal evidence, over-broad wording, free-text relation, indirect evidence, unverifiable identifier, strength / modality mismatch, relation not worded in the evidence, duplicate; `low`: weak support (< 0.4), direction / polarity /
attribution doubts, approximate quote, any status other than `reported`. A declared `conf:` can only lower the level.

## Budget
A typical case needs: `prepare` (1), `outline` + `candidates` (1-2), `atoms` / `read` (2-4), `ingest` (2-4 including fixes), `meta` (1), `assemble` + `validate` (1-2) = about 12-18 model requests. The tool prints compact output on purpose.
These numbers are estimated from the procedure, not measured on the evaluation platform.

## Known limits
- Rule-based: a claim that changes the meaning but keeps the evidence's words (subject/object exchange in a symmetric label, a flipped comparison without word-order change) can pass.
- Relation direction uses word order and passive markers; complex syntax and nominalisations are misjudged both ways (warnings, not errors).
- Hedge / negation / scope detection depends on word lists (English plus basic Chinese quote/number/anchor checks; the linguistic cues are English).
- Entity grounding is lexical (stems and squashed spelling: BERT-large = BERTLARGE); synonyms and abbreviations defined elsewhere in the paper are not resolved.
- Identifiers are only syntax-checked; they are not resolved against a registry (no network at run time).
- Source metadata extraction is heuristic (authors of very long collaboration lists are summarised, venue lines are verbatim fragments); every value carries its origin and confidence and must be confirmed.
- Nanopublications are not minted, signed or published; IRIs are placeholders.
- PDFs: figures as images, equations and complex tables are only as good as the parser; claims whose evidence is inside an image cannot be bound (mark `unclear`).
