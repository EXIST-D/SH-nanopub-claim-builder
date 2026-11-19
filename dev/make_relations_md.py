#!/usr/bin/env python3
"""Generate submission/references/relations.md from vocab.RELATIONS so that the documentation cannot drift from the code."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "submission", "scripts"))
import vocab  # noqa: E402

L = ["# Relation vocabulary (`p:`)", "",
     "Terms live in the namespace `%s` (a placeholder: replace it with `assemble --vocab-ns`). A closeMatch is given only where an OBO Relation Ontology / BFO term is close in meaning;" % vocab.VOCAB_NS,
     "each id was looked up in the EBI OLS service on 2026-11-20 and its label is recorded. Terms without a mapping have none - nothing is guessed. `closeMatch` is not `exactMatch`: check the definition.", "",
     "| term | reads as | direction matters | definition | closeMatch (OBO id, OLS label) |", "|---|---|---|---|---|"]
for k, v in vocab.RELATIONS.items():
    cm = "obo:%s (%s)" % (v["close"], v["map_label"]) if v["close"] else "-"
    L.append("| `%s` | subject %s object | %s | %s | %s |" % (k, v["label"], "yes" if v["directional"] else "no", v["definition"], cm))
L += ["", "## Choosing a term", "",
      "- **Association is not causation.** `associated_with` for correlations / co-occurrence; `causes`, `prevents`, `treats` only if the evidence states the effect. The checker rejects `causes` when the only wording is an association (`relation_type`).",
      "- **Comparisons**: the subject is the one that is higher / better / faster (`outperforms`); \"B is worse than A\" is `A outperforms B`. The measure and the data go in `cond:`.",
      "- **Negation** is `polarity: negative` (\"did not change\" -> `regulates` + negative; \"does not differ\" -> `differs_from` + negative). The plain triple is then **not** exported, only the claim node with its polarity, so a negative finding is never asserted as positive.",
      "- **Values**: `has_value` with `o:` the number (and `value:` / `unit:`): subject is the measured quantity including its context (\"BLEU score of X on dataset Y\").",
      "- **Observation vs theory**: `consistent_with` (+ negative for \"contradicts\"); `detects` for \"observed / demonstrated / identified\".",
      "- **Methods and data**: `uses`, `evaluated_on`, `trained_on`, `derived_from` (material origin), `part_of`.",
      "- `other` keeps the free text (`v:relationText`) and flags the claim for review. Prefer a controlled term.", "",
      "Aliases accepted for `p:` (case and punctuation insensitive): " + ", ".join("%s -> %s" % kv for kv in sorted(vocab.REL_ALIASES.items())) + ".", ""]
open(os.path.join(HERE, "..", "submission", "references", "relations.md"), "w", encoding="utf-8").write("\n".join(L))
print("written", len(L), "lines")
