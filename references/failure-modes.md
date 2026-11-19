# Failure modes -> what to do

| symptom | cause | action |
|---|---|---|
| `prepare`: `PDF parsing failed ... not a PDF` / `encrypted PDF` | bad file | report `failed`/`refused` with the parser's message; do not guess content |
| `prepare`: many units empty, `unparsed` pages | scanned PDF without OCR engine | `pip install rapidocr` (or tesseract) and `--ocr force`; otherwise report the pages as not processed |
| `source_found` has no title/authors/year | scan, unusual front matter, bare paragraph | `read --page 1`; `meta --set` only what the text shows; the rest stays unknown |
| `ingest`: `quote_missing` | paraphrase or edited quote | copy the span from `read --sentences` output exactly (spacing and hyphen breaks are tolerated, words are not) |
| `quote_other_unit` | quote is in another unit | cite the unit the message names |
| `numbers ... (found in E0xx)` | the number is stated elsewhere | cite that unit as well (then `evtype: indirect`) or drop the number |
| `entity_not_in_evidence` | subject/object label not in the anchored text | use the name as written in the paper, or add the anchor that introduces it |
| `relation_type` | `causes/treats/...` backed only by an association sentence | use `associated_with` / `consistent_with` or cite an effect statement |
| `atomicity` | several relations / coordinated clauses / long text | split with the hints from `atoms`; keep conditions in `cond` |
| `direction` | evidence reads object-before-subject without passive | check the sentence; if the claim is right (inverse comparatives, "worse than") keep it, otherwise swap s and o |
| `attribution` | evidence sentence cites other work | `origin: cited` (the reference is attached) or `origin: this_paper` if the authors own the result |
| `scope_dropped` | evidence limits the statement (species, dataset, "only if") | put it into `cond:` |
| `no_evidence` for a claim the paper does not support | claim comes from background knowledge | `status: unsupported` + `note:` saying where you searched |
| TriG validation fails | claims all rejected / hand-edited file | fix the claims, re-run `assemble`; `validate` names the violated rule |
| `assemble` prints UNFILLED contract fields | field name not derivable | write the values to `answers.json`, re-run with `--answers` |
| runtime budget nearly used | long paper | `assemble` now (partial result with `status: partial`), then continue |
