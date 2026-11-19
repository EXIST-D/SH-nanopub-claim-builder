# dev/ - tests and evaluations of nanopub-claim-builder (not part of the Skill runtime)

| file | what |
|---|---|
| `test_all.py` | 14 regression tests (stdlib `unittest`): TriG validator on the well-formedness rules, vocabulary, the full pipeline on the fictional example (ingest -> assemble -> validate, locator round trip, cited claims, negative polarity, flawed claims, case contract). `python3 dev/test_all.py` |
| `seeded_claims_eval.py` | inject one defect at a time into correct claims and measure how often `ingest` catches it. Needs the four prepared papers below. Result: `seeded_eval_result.txt` |
| `scifact_eval.py` | minimal-evidence proposal and atomicity check on the public SciFact data. Result: `scifact_eval_result.txt` |
| `attention_claims.txt`, `bert_claims.txt`, `resnet_claims.txt`, `ligo_claims.txt` | 31 hand-written claims (8 + 8 + 8 + 7; the Attention file also holds one deliberately wrong claim, C9, which is dropped before the evaluation) |
| `make_example.py`, `make_relations_md.py` | regenerate `examples/example_output/`, `examples/minimal-example.md` and `references/relations.md` from real runs / the vocabulary module |

## Reproduce the seeded-defect evaluation
Public papers (open access): Attention Is All You Need (arXiv 1706.03762), BERT (arXiv 1810.04805), Deep Residual Learning (arXiv 1512.03385), Observation of Gravitational Waves from a Binary Black Hole Merger
(Phys. Rev. Lett. 116, 061102, CC BY 3.0).
```bash
for p in attention bert resnet ligo; do python3 scripts/npb.py prepare $p.pdf --work work/$p; python3 scripts/npb.py ingest work/$p dev/${p}_claims.txt; done
python3 scripts/npb.py drop work/attention C9
python3 dev/seeded_claims_eval.py work/attention work/bert work/resnet work/ligo
```
The claims were written by the tool's author while developing the checker: the numbers are optimistic. Quotes are short excerpts used for testing.

## Reproduce the SciFact evaluation
SciFact (Wadden et al. 2020, https://github.com/allenai/scifact, CC BY-NC 2.0, non-commercial use): download `data.tar.gz` from the repository's release link, unpack to `dev/ref/scifact/data/`
(`corpus.jsonl`, `claims_dev.jsonl`, `claims_train.jsonl`), then `python3 dev/scifact_eval.py 1000`. The data is not redistributed here.

## References used while building
- Nanopublication Guidelines (https://github.com/Nanopublication/Guidelines): head / assertion / provenance / publicationInfo and the well-formedness rules implemented in `export.validate_trig`.
- OBO Relation Ontology ids in `scripts/vocab.py` were looked up in EBI OLS on 2026-11-20 (labels recorded in `references/relations.md`).
- Web Annotation vocabulary (`oa:TextQuoteSelector`, `oa:SpecificResource`), PROV-O, Dublin Core terms.
