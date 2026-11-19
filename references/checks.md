# Checks run by `ingest` (per claim) and `assemble` (per export)

Severity: **error** = the claim is not exported (it stays in `claims.json`, listed under `rejected_claims`); **warn** = exported, flagged for review, confidence reduced.
Every message names the rule and the text that triggered it, so a reviewer can reproduce it by hand.

| kind | severity | rule | known blind spots |
|---|---|---|---|
| `incomplete` | error | `text`, `s`, `p`, `o` missing | - |
| `entity_unresolved` | error / warn | subject/object is a pronoun or generic phrase (error); starts with a demonstrative (warn) | other vague labels ("the method") are only caught when listed |
| `entity_list` | warn | label joins several alphabetic entities with and / or / commas | genuine single entities with "and" in the name |
| `anchor_syntax`, `anchor_unknown`, `anchor_sentence`, `anchor_excluded` | error | anchor does not exist / refers to references or acknowledgements | - |
| `no_evidence` | error | `status=reported` without an anchor (the message names the closest unit) | - |
| `status_unexplained` | error | status other than `reported` without `note:` | - |
| `quote_missing` / `quote_approx` / `quote_other_unit` | error / warn / error | quote must occur verbatim (spacing, hyphen breaks, ligatures, case, punctuation tolerated) in the anchored unit; >= 90 % match -> warn; verbatim but elsewhere -> error naming the unit | a short quote (< 6 characters) is ignored |
| `numbers` | error / warn | every number in text / cond / value must occur in the evidence (decimals, thousands, exponents; citation markers and "Figure 3" excluded); numbers occurring only in labels -> warn; `derived:` -> warn | numbers written as words; single digits are not checked |
| `support` | error / warn | content-word overlap claim <-> evidence: < 0.15 error, < 0.4 warn | paraphrase with different vocabulary |
| `entity_not_in_evidence` | error / warn | subject / object label does not occur in the anchored evidence (0 % error, < 50 % warn; squashed spelling accepted) | abbreviations defined elsewhere; synonyms |
| `direction` | warn | word order + passive / inverse-comparative markers say object comes first for a directional relation | complex syntax, nominalisation |
| `relation_type` | error | effect relation (`causes`, `prevents`, `treats`, `increases`, `decreases`) and the evidence wording is only association / consistency | evidence with no cue at all is a warn (`relation_unsupported`) |
| `relation_unsupported` | warn | no wording of the relation (verb stems of the term) in the evidence | paraphrased verbs |
| `relation_free_text`, `relation_mapped` | warn | `p` not controlled / mapped from a verb phrase | - |
| `atomicity` | warn / error | signals: several coordinated relation verbs, coordination (", and", "; ", ", while", "respectively"), > 45 words, >= 3 different quantities; error when coordinated relation verbs + coordination, or > 70 words | compounds without a coordinator or verb cue |
| `overbroad` | warn | quantifier (all, every, always, never, generally, ...) in claim / labels that the evidence does not use | implicit generalisation |
| `overclaim`, `strength` | warn | strength word ("proves", "breakthrough") not in the evidence; hedged evidence stated as established | - |
| `scope_dropped` | warn | the evidence span carries a limiting phrase (in mice, among ..., only if ..., on the X dataset, when ...) that neither claim, cond nor labels contain | scope expressed in other words; cue list is finite |
| `modality` | warn | evidence hedged (may, suggest, propose, ...) but `modality: asserted` declared | - |
| `polarity` | warn | evidence span has a negation (not, no, contradict, ...) but polarity positive; or polarity negative without any negation cue | scope of the negation inside a long sentence (the verified quote is used as the span when given) |
| `attribution` | warn | citation marker after the subject or closing the sentence, no "we/our" -> claim probably belongs to the cited work; `origin: cited` without a marker; finding anchored in an introduction without "we" | authors citing their own earlier work |
| `evidence_not_minimal` | warn | anchored sentences that add nothing to the claim (greedy idf-weighted cover) or a unit-level anchor of >= 4 sentences where <= 2 suffice | - |
| `evidence_type` | warn | `evtype: direct` declared but no single sentence holds subject, object and content (inference across statements) | - |
| `identifier`, `identifier_origin` | warn | CURIE not recognised; local id does not occur in the paper (exported as asserted by the author) | ids are not resolved against registries |
| `duplicate` | warn | same subject / relation / object or >= 0.8 word overlap, same polarity and conditions | - |
| `confidence` | warn | declared confidence is higher than the computed one | - |
| TriG validity | assemble | well-formedness rules of the Nanopublication Guidelines (see `field-dictionary.md`) | blank-node syntax is reported as unsupported, not invalid |
| locator round trip | assemble | for every evidence item `unit_text[char_start:char_end] == quote` | - |

## Measured behaviour (development tests; not platform scores)
**Seeded defects** (`dev/seeded_claims_eval.py`): 31 claims written by hand for 4 real papers (Attention Is All You Need, BERT, ResNet, LIGO GW150914), one defect injected at a time and re-checked with the same code as `ingest`.
The claims were written by the tool's author, so the numbers are optimistic; unmodified claims: 0 error-level false alarms, 10/31 carry a (reasonable) warning.

| injected defect | caught (any issue) | caught at error level |
|---|---|---|
| fabricated quote (two words changed) | 100 % | 100 % |
| paraphrase passed off as quote | 100 % | 100 % |
| anchor points to another section (with / without quote) | 100 % / 100 % | 100 % / 94 % |
| number changed in the claim text | 100 % | 100 % |
| evidence anchor deleted | 100 % | 100 % |
| unneeded evidence added (not minimal) | 100 % | 0 % (warning by design) |
| subject / object replaced by an entity from elsewhere | 79 % / 83 % | 72 % / 69 % |
| polarity flipped | 97 % | 0 % (warning by design) |
| universal quantifier added | 100 % | 0 % (warning by design) |
| relation changed to `causes` / `treats` | 77 % / 77 % | 0 % (warning by design) |
| two claims joined | 100 % | 100 % |
| text replaced by an unrelated sentence | 90 % | 42 % |
| subject and object swapped (direction) | 71 % | 0 % (warning by design) |
| conditions / scope removed | 19 % | 0 % |
The low rate for removed conditions is expected: in these claims the scope is usually also in the claim text, and the check only fires when the evidence carries a limiting phrase that nothing in the claim repeats.

**SciFact** (public data, CC BY-NC 2.0; `dev/scifact_eval.py`): 772 claim-abstract pairs with expert rationale sentences. Proposing the minimal evidence from the whole abstract: the top proposed sentence is a gold rationale in 32 %
(random sentence 21 %, first sentence 7 %); the proposed set (2.0 sentences) contains 55 % of the gold rationale sentences (gold sets have 1.8 sentences, the abstract about 9.7). Atomicity: 3.3 % of 673 single SciFact claims are flagged
(false alarms); 300 / 300 synthetic compounds (two claims joined by ", and" / "; " / ", while" / ", but") are flagged - an easy test: compounds without coordinator are not covered.
