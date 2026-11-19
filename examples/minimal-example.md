# Minimal example (real output of the tool on a FICTIONAL paper)

`mini_paper.md` is an invented paper written for this example: its findings, numbers and DOI are not real. Everything below is the unedited output of the commands (long lines shortened with `...`). `example_output/` holds the files `assemble` wrote. Nothing here is a result of a platform case.

## 1. Parse the paper into evidence units and source metadata
```bash
python3 scripts/npb.py prepare mini_paper.md --work W
```
```text
{"ok": true, "work": "W", "file": "mini_paper.md", "format": "md", "lang": "en", "pages": null, "units": 11, "citable_units": 10, "sections": 10, "words": 423, "references_parsed": 2, "parser_status": null, "source_found": {"doi": "10.9999/jib.2024.0042", "title": "Soft-Substrate Culture Raises Osteoblast Mineralisation: A Fictional Example Paper", "authors": "ok", "year": 2024, "venue": "Journal of Imaginary Biomaterials"}, "source_missing": []}
Next: `outline`, `candidates` (key-conclusion sentences), `atoms W E104.2` (decomposition hints), then write claims and `ingest` them.
```

## 2. The paper's own sections
```bash
python3 scripts/npb.py outline W
```
```text
OUTLINE of mini_paper.md (en, 10 citable units)
§front (front matter) | p- | E001..E003 | 26 words [optional]
§abs Abstract | p- | E004..E004 | 82 words [optional]  cues: res:2 lim:1
§1 Introduction | p- | E005..E005 | 60 words
§2 Methods | p- | E006..E006 | 77 words
§3 Results | p- | None..None | 0 words
  §3.1 Mineralisation | p- | E007..E007 | 49 words  cues: res:2 lim:1
  §3.2 YAP localisation | p- | E008..E008 | 57 words  cues: lim:1 res:1
  §3.3 Human cell line | p- | E009..E009 | 18 words  cues: lim:1
§4 Discussion | p- | E010..E010 | 54 words  cues: lim:2 fut:1
§s9 References | p- | E011..E011 | 54 words [excluded]
```

## 3. Decomposition hints for two key sentences
```bash
python3 scripts/npb.py atoms W E008.2 E005.2
```
```text
E008.2 [p- §3.2] Treatment with the YAP inhibitor verteporfin reduced nodule area on 40 kPa gels by 22%, but it did not change nodule area on 10 kPa gels.
    clauses (split candidates): Treatment with the YAP inhibitor verteporfin reduced nodule area on 40 kPa gels by 22% || it did not change nodule area on 10 kPa gels.
    relation verbs: decreases ('reduc'); inhibits ('inhibit'); regulates ('change'); treats ('Treat')
    entity candidates: YAP
    numbers 40, 22, 10 | negation 'not' -> polarity?
    origin guess: this_paper
E005.2 [p- §1] Engler et al. showed that matrix elasticity directs lineage specification of mesenchymal stem cells [2].
    relation verbs: regulates ('directs'); detects ('showed')
    cites: [2] -> Engler AJ, Sen S, Sweeney HL, Discher DE. Matrix elasticity directs stem cell lineage spec
    origin guess: cited
```

## 4. Submit 19 claims (`claims_20.txt`; claim C19 is a deliberate `unsupported` example)
```bash
python3 scripts/npb.py ingest W claims_20.txt
```
```text
stored 19 | ok 17 | warn 2 | ERROR 0 | accepted claims in total: 19 (reported 18)
ids: C1 C2 C3 C4 C5 C6 C7 C8 C9 C10 C11 C12 C13 C14 C15 C16 C17 C18 C19   (* = failing; resubmit with id=<id>)
  (2 claim(s) have warnings: `check W` or ingest -v to list them)
```

## 5. Same tool on 13 deliberately flawed claims (`claims_flawed.txt`): what the checks say
```bash
python3 scripts/npb.py ingest W2 claims_flawed.txt -v
```
```text
stored 13 | ok 0 | warn 7 | ERROR 6 | accepted claims in total: 7 (reported 7)
ids: F1* F2 F3* F4 F5* F6* F7 F8 F9 F10 F11 F12* F13*   (* = failing; resubmit with id=<id>)
  F1 ERROR quote_missing: quote not found in the paper (best match 56% in E007): fabrication or paraphrase - quote verbatim or drop the quote
  F1 ERROR numbers: numbers not in the cited evidence: 3.3 (not in the paper). Cite the unit that contains them or add `derived:`
  F2 WARN direction: in the evidence sentence the object 'mineralised nodule area on 10 kPa gels' comes before the subject 'mineralised nodule area on 40 kPa gels' (no passive marker): check that the relation 'outperforms' really runs subject -> obje
  F3 WARN direction: in the evidence sentence the object 'nodule area' comes before the subject 'cell density' (no passive marker): check that the relation 'causes' really runs subject -> object (relation direction): "Nodule area did not correlate wi
  F3 ERROR relation_type: relation 'causes' asserts an effect but the evidence only states an association/consistency ('correlat'): use associated_with / consistent_with, or cite evidence that states the effect (relation type error)
  F3 WARN polarity: the evidence contains a negation ('not') but the claim is positive: set polarity=negative or reword (polarity error)
  F4 WARN atomicity: claim is not atomic (several coordinated relation verbs (decreases, inhibits)): split it so that each claim is one subject - relation - object that can be judged true/false on its own
  F4 WARN overbroad: quantifier(s) in the claim that the evidence does not use: all (over-broad claim)
  F4 WARN polarity: the evidence contains a negation ('not') but the claim is positive: set polarity=negative or reword (polarity error)
  F5 ERROR support: the cited evidence hardly shares any wording with the claim (support 0.14): wrong anchor or unsupported claim
  F5 ERROR entity_not_in_evidence: object 'mineralisation' does not occur in the cited evidence - it appears in E001 (subject/object mix-up or wrong anchor)
  F5 WARN relation_unsupported: no wording for 'increases' in the evidence sentence(s) (looked for: increas|upregulat|up-regulat|elevat|enhanc|boost|rais|amplif): the relation may be inferred rather than stated -> evtype=indirect or another relation
  F5 WARN overbroad: quantifier(s) in the claim that the evidence does not use: all, always (over-broad claim)
  F5 WARN overclaim: strength word(s) not in the evidence: always
  F6 ERROR entity_unresolved: subject 'It' is a pronoun / generic phrase: name the entity (subject confusion)
  F6 WARN polarity: the evidence contains a negation ('not') but the claim is positive: set polarity=negative or reword (polarity error)
  F7 WARN polarity: the evidence contains a negation ('not') but the claim is positive: set polarity=negative or reword (polarity error)
  F8 WARN modality: the evidence is hedged ('suggest') but modality=asserted: use modality=hedged
  F8 WARN strength: evidence is hedged ('suggest') but the claim states it as established ('demonstrates')
  F9 WARN attribution: the evidence sentence cites other work ([1]): the claim may belong to the cited work, not to this paper - set origin=cited and name it, or origin=this_paper if the authors own it
  F9 WARN attribution: a finding anchored in an introduction/related-work section without 'we/this paper': probably background from other work (origin=background)
  F10 WARN scope_dropped: the evidence limits the statement ("In the human") but claim/cond do not say so: put it in `cond:`
  F11 WARN evidence_not_minimal: anchored sentence(s) E008.1, E008.3, E006.1, E006.2 add nothing to the claim: the minimal sufficient evidence is E008.2
  F11 WARN duplicate: near-duplicate of F13: merge them (`merge`) so one claim carries all its evidence
  F12 ERROR anchor_unknown: unknown evidence ids: E999 (ids are E001..E011)
  F12 ERROR no_evidence: no evidence anchor (ev:). Closest unit: E010 [§4] Our findings contradict the view that stiffer matrices always promote osteogenic... If the paper gives no support, resubmit with status=unsupported.
  F13 ERROR no_evidence: no evidence anchor (ev:). Closest unit: E008 [§3.2] The fraction of nuclei with nuclear YAP was 31% on 10 kPa gels and 58% on 40 kPa... If the paper gives no support, resubmit with status=unsupported.
  F13 WARN duplicate: near-duplicate of F11: merge them (`merge`) so one claim carries all its evidence
```

## 6. What is missing
```bash
python3 scripts/npb.py next W
```
```text
claims: 19 accepted (18 reported), 0 failing | confidence {'high': 13, 'medium': 5} | origin {'this_paper': 16, 'cited': 2}
TODO 1 uncovered key-conclusion candidate sentence(s), e.g.:
  E004.3 Nuclear YAP localisation was lower on 10 kPa gels, which suggests that YAP signalling mediates part of the stiffness response.
```

## 7. Export
```bash
python3 scripts/npb.py assemble W --out example_output
```
```text
{"written": "example_output", "status": "success", "nanopublications": 18, "other_status": 1, "rejected_claims": 0, "trig_valid": true, "locators_reproduce_quotes": true, "source_missing": [[]], "confidence": {"high": 13, "medium": 5}, "unfilled_contract_fields": [], "contract_found": false}
```

## 8. Validate the nanopublications
```bash
python3 scripts/npb.py validate example_output/nanopubs.trig
```
```text
{"ok": true, "nanopubs": 18, "errors": [], "unsupported": null}
```

## 9. One nanopublication (TriG) - claim C7, a measured effect with a quote located by character offsets
```turtle
@prefix : <https://example.org/np-claim-builder/np/npddcff292cf62/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix np: <http://www.nanopub.org/nschema#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix oa: <http://www.w3.org/ns/oa#> .
@prefix v: <https://example.org/np-claim-builder/vocab#> .

:Head {
  : a np:Nanopublication ;
    np:hasAssertion :assertion ;
    np:hasProvenance :provenance ;
    np:hasPublicationInfo :pubinfo .
}

:assertion {
  <https://example.org/np-claim-builder/entity/verteporfin> rdfs:label "verteporfin" .
  <https://example.org/np-claim-builder/entity/nodule_area> rdfs:label "nodule area" .
  <https://example.org/np-claim-builder/entity/verteporfin> v:decreases <https://example.org/np-claim-builder/entity/nodule_area> .
  v:decreases skos:closeMatch <http://purl.obolibrary.org/obo/RO_0002212> .
  :claim a v:Claim ;
    v:statement "The YAP inhibitor verteporfin reduces nodule area on 40 kPa gels by 22%." ;
    v:subject <https://example.org/np-claim-builder/entity/verteporfin> ;
    v:relation v:decreases ;
    v:object <https://example.org/np-claim-builder/entity/nodule_area> ;
    v:polarity "positive" ;
    v:claimType "finding" ;
    v:condition "40 kPa gels; reduction of 22%" .
}

:provenance {
  :assertion prov:wasDerivedFrom <https://doi.org/10.9999/jib.2024.0042> ;
    v:evidenceType "direct" ;
    v:modality "asserted" ;
    v:confidence "high" ;
    v:confidenceBasis "quote verified verbatim; evidence is direct; numbers present in evidence" ;
    v:attribution "this_paper" ;
    v:extractionStatus "reported" ;
    v:supportedBy :evidence1 .
  :evidence1 a oa:SpecificResource, v:EvidenceSpan ;
    oa:hasSource <https://doi.org/10.9999/jib.2024.0042> ;
    v:evidenceKind "author_quote" ;
    rdf:value "Treatment with the YAP inhibitor verteporfin reduced nodule area on 40 kPa gels by 22%" ;
    v:unit "E008" ;
    v:sentences "2" ;
    v:section "Results > YAP localisation" ;
    v:startInUnit "87"^^xsd:integer ;
    v:endInUnit "173"^^xsd:integer ;
    oa:hasSelector :selector1 .
  :selector1 a oa:TextQuoteSelector ;
    oa:exact "Treatment with the YAP inhibitor verteporfin reduced nodule area on 40 kPa gels by 22%" ;
    oa:prefix "on 10 kPa gels and 58% on 40 kPa gels. " ;
    oa:suffix ", but it did not change nodule area on 1" .
  <https://doi.org/10.9999/jib.2024.0042> a v:Source ;
    dct:title "Soft-Substrate Culture Raises Osteoblast Mineralisation: A Fictional Example Paper" ;
    dct:creator "Mara Lindqvist" ;
    dct:creator "Tomas Okafor" ;
    dct:creator "Yuki Hartmann" ;
    dct:issued "2024"^^xsd:gYear ;
    dct:isPartOf "Journal of Imaginary Biomaterials" ;
    dct:identifier "doi:10.9999/jib.2024.0042" ;
    v:fileSha256 "3e471272bcfe00cceca8340071acfc401d4a2c58ea7e407beb74d2d9b3e3fd10" ;
    v:fileName "mini_paper.md" .
}

:pubinfo {
  : dct:created "2026-11-19T16:28:50Z"^^xsd:dateTime ;
    dct:creator <https://example.org/np-claim-builder/agent/np-claim-builder> ;
    v:toolVersion "1.0.0" ;
    v:reviewStatus "machine-extracted; unreviewed" .
}
```

## What to look at
- `example_output/nanopubs.json`: one record per claim (assertion with subject / relation / object / polarity / conditions, evidence with page / section / bbox / offsets, source, attribution, confidence with basis, checks, review flags).
- `example_output/nanopubs.trig`: the same claims as nanopublications; `claims.csv`: flat table; `review_checklist.md`: what a person must confirm; `check_report.json`: counts and issues; `result.json`: contract-shaped result.
