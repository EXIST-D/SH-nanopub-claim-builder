# Field dictionary

## Claim input (`ingest`)
| key | meaning | required |
|---|---|---|
| `text` | one self-contained sentence stating the claim | yes (reported) |
| `s` / `p` / `o` | subject label, relation (controlled term, see `relations.md`), object label | yes (reported) |
| `s_id`, `o_id` | CURIE of the subject / object (`NCBIGene:7157`, `CHEBI:15377`, `GO:0006915`, `UniProt:P04637`, `MESH:D000001`, `DOI:...`, `ORCID:...`, ...); checked for syntax; if the local id does not occur in the paper it is exported as *asserted by the claim author* | no |
| `value`, `unit` | numeric object (also parsed from `o:` when it is a number with a unit) | no |
| `cond` | conditions that make the claim true: data, species, sample, dose, version, n, p, margin of a comparison | strongly advised |
| `ev` | evidence anchors: sentence `E104.1`, unit `E104`, range `E104-E106`, sentence range `E104.1-3` | yes (reported) |
| `quote` | verbatim minimal span; several separated by `|||`; located by character offsets | advised |
| `polarity` | `positive` (default) / `negative` | no |
| `modality` | `asserted` / `hedged` / `hypothesis`; default derived from the evidence wording | no |
| `origin` | `this_paper` / `cited` / `background`; default derived (citation marker after the subject or ending the sentence, no "we/our") | no |
| `evtype` | `direct` (one stated sentence) / `indirect` (inferred from several); computed and exported as `evidence_type` | no |
| `type` | `finding method data definition background limitation hypothesis recommendation other` | no |
| `status` | `reported` (default) / `unsupported` / `conflict` / `unclear` / `not_reported`; anything but `reported` needs `note:` and is not written to TriG | no |
| `conf`, `basis` | optional declared confidence and reason; the exported confidence is computed and can only be lower | no |
| `note`, `derived`, `tags`, `id`, `sec` | free note; how a computed number was derived; tags; claim id (reuse to replace); section hint | no |

## Evidence addressing
`E012` = unit (paragraph, list item, caption, table, ...), `E012.3` = its third sentence, `E012-E015` = range. Each unit stores text, sentences, page(s), bbox (PDF),
section id / title / path, block id. `evidence_index.json` holds all units, so anyone can open the source position: unit id -> page, bbox, section, text, and the
claim's character offsets (`char_start`, `char_end`) index into that unit text.

## Output files (`assemble --out OUT`)
| file | content |
|---|---|
| `nanopubs.trig` | one nanopublication per reported claim: graphs `:Head`, `:assertion`, `:provenance`, `:pubinfo` (TriG, validated) |
| `nanopubs.json` | `{schema, tool_version, generated, sources[], counts, vocabulary, nanopubs[]}`; one record per claim (all statuses) |
| `nanopubs.jsonl` | the same records, one per line |
| `claims.csv` | flat table: ids, claim text, subject / relation / object, value, polarity, conditions, modality, evidence type, attribution, confidence, quote, units, pages, section, source fields, issues |
| `source.json` | source metadata with origin / confidence per field, raw extraction and the parsed reference list |
| `evidence_index.json` | every unit with page / bbox / sentences (the key to the evidence locators) |
| `review_checklist.md` | what a person must confirm, per claim and per source |
| `check_report.json` | counts, issue kinds, rejected claims, uncovered key sentences, TriG validation, locator round-trip |
| `result.json` | contract fields (derived from `output_contract` when the case has one) + `case_id`, `status`, `sources`, `uncertainty`, `change_records`, `nanopubs`, `verification`, `human_review`, `files`, `_meta` |

## Record of one claim (`nanopubs.json` -> `nanopubs[]`)
```
np_id, claim_id, status, claim_text, claim_type, modality, evidence_type, schema, tool_version, created
assertion: subject{label,id,iri,id_origin}, relation{term,label,iri,close_match,close_match_label,free_text,directional},
           object{label,id,iri,value,unit,id_origin}, polarity, conditions, claim_type
evidence[]: kind (author_quote | anchored_sentence), quote, locator{unit, sentences, page, pages, bbox, block, section_id, section_title, section_path,
            char_start, char_end, prefix, suffix}
source: source_id, iri, title, authors[], year, venue, doi, arxiv_id, pmid, version, sha256, file_name, pages, fields{origin,confidence}, missing[], conflicts[]
attribution: origin, computed_origin, cited[{marker, ref_n, ref_text, doi}]
confidence: level (high|medium|low), basis[], scope   (extraction fidelity, not a judgement of scientific truth)
checks: status, issues[{severity,kind,detail}], support, numbers, quotes, direction, minimal_anchors
review: needs_human, status, reasons[]
note, tags[]
```
`np_id` is a hash of (source hash or IRI, claim id, subject, relation, object): stable across runs on the same file, so repeated runs can be de-duplicated.

## Mapping of a claim to the nanopublication graphs
- `:Head` - `: a np:Nanopublication; np:hasAssertion :assertion; np:hasProvenance :provenance; np:hasPublicationInfo :pubinfo`.
- `:assertion` - entity labels (`rdfs:label`), the plain triple `subject v:<relation> object` **only for positive polarity**, and `:claim a v:Claim` with `v:statement`, `v:subject`, `v:relation`,
  `v:object`, `v:polarity`, `v:claimType`, `v:condition`, `v:objectValue` / `v:objectUnit`, `v:relationText` (for `other`).
- `:provenance` - `:assertion prov:wasDerivedFrom <source IRI>` (DOI > arXiv > `urn:sha256:`) and, for cited claims, the cited work (DOI IRI or `dct:bibliographicCitation`);
  `v:evidenceType`, `v:modality`, `v:confidence`, `v:confidenceBasis`, `v:attribution`, `v:extractionStatus`, `v:supportedBy :evidenceN`; each `:evidenceN` is an
  `oa:SpecificResource` with `rdf:value` (quote), `v:unit`, `v:sentences`, `v:page`, `v:section`, `v:bbox`, `v:startInUnit` / `v:endInUnit` and an `oa:TextQuoteSelector` (`oa:exact`, `oa:prefix`, `oa:suffix`);
  the source node carries `dct:title`, `dct:creator`, `dct:issued`, `dct:isPartOf` (venue), `dct:hasVersion`, `dct:identifier`, `v:fileSha256`.
- `:pubinfo` - `: dct:created`, `dct:creator <tool agent>`, `v:toolVersion`, `v:reviewStatus "machine-extracted; unreviewed"`.
IRIs use a placeholder base (`--base`, default `https://example.org/np-claim-builder/`); nanopublications are **not signed or published** and carry no trusty URI.
Validation (`validate FILE.trig`): exactly one `np:Nanopublication` quad with exactly one `hasAssertion` / `hasProvenance` / `hasPublicationInfo`, five distinct IRIs, every triple in one of the
named graphs, provenance refers to the assertion, publicationInfo refers to the nanopublication. Cross-checked in development with rdflib (parses all graphs; the guidelines' SPARQL pattern returns every nanopublication).

## `result.json`
Contract fields are read from the case's `output_contract` (list or dict). Derivable names are filled (`status`, `sources`, `uncertainty`, `change_records`, `claims` / `nanopublications` / `nanopubs`,
`evidence`, `source_metadata` / `provenance`, `trig`, `export`, `verification`, `human_review`, `summary`, `files`, `title`); the others are `null` and listed in `_meta.unfilled_fields`
(supply them with `--answers answers.json`). Without a contract the file still carries `case_id`, `status`, `sources`, `uncertainty`, `change_records`, `nanopubs`, `verification`, `human_review`, `files`.
`status`: `success` (claims exported, none rejected, TriG valid, locators reproduce the quotes, source fields found), `partial` (claims exported but something is missing / rejected / invalid), `failed` (no exportable claim).
