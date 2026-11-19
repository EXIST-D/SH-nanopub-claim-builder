# Relation vocabulary (`p:`)

Terms live in the namespace `https://example.org/np-claim-builder/vocab#` (a placeholder: replace it with `assemble --vocab-ns`). A closeMatch is given only where an OBO Relation Ontology / BFO term is close in meaning;
each id was looked up in the EBI OLS service on 2026-11-20 and its label is recorded. Terms without a mapping have none - nothing is guessed. `closeMatch` is not `exactMatch`: check the definition.

| term | reads as | direction matters | definition | closeMatch (OBO id, OLS label) |
|---|---|---|---|---|
| `increases` | subject increases object | yes | subject raises the level / rate / amount / frequency of the object | obo:RO_0002213 (positively regulates) |
| `decreases` | subject decreases object | yes | subject lowers the level / rate / amount / frequency of the object | obo:RO_0002212 (negatively regulates) |
| `activates` | subject activates object | yes | subject switches on or triggers the object (pathway, enzyme, process) | obo:RO_0002213 (positively regulates) |
| `inhibits` | subject inhibits object | yes | subject blocks or switches off the object | obo:RO_0002212 (negatively regulates) |
| `regulates` | subject regulates object | yes | subject controls the object without a stated direction of effect | obo:RO_0002211 (regulates) |
| `causes` | subject causes object | yes | subject brings about the object (a causal claim, not a mere association) | obo:RO_0002410 (causally related to) |
| `prevents` | subject prevents object | yes | subject stops the object from occurring | - |
| `treats` | subject treats object | yes | subject (drug, intervention) is used to treat or ameliorate the object (condition) | obo:RO_0002606 (is substance that treats) |
| `associated_with` | subject is associated with object | no | subject and object co-occur / covary; no direction or causation claimed | obo:RO_0002610 (correlated with) |
| `interacts_with` | subject interacts with object | no | subject and object physically or functionally interact | obo:RO_0002434 (interacts with) |
| `part_of` | subject is part of object | yes | subject is a component of the object | obo:BFO_0000050 (part of) |
| `located_in` | subject is located in object | yes | subject is found in / localised to the object (place, tissue, compartment, population) | obo:RO_0001025 (located in) |
| `has_phenotype` | subject has phenotype object | yes | subject (organism, genotype) shows the object phenotype | obo:RO_0002200 (has phenotype) |
| `has_value` | subject has value object | yes | subject quantity / property has the numeric value or range given as object (add value:/unit:) | - |
| `outperforms` | subject outperforms object | yes | subject (method, treatment) does better than the object on a stated measure (condition names the measure and data) | - |
| `consistent_with` | subject is consistent with object | no | subject (observation, result, model) agrees with the object (prediction, theory, earlier result); use polarity=negative for 'inconsistent with' | - |
| `differs_from` | subject differs from object | no | subject and object differ on a stated property | - |
| `uses` | subject uses object | yes | subject (study, method) employs the object (tool, dataset, technique, material) | - |
| `evaluated_on` | subject is evaluated on object | yes | subject (method, model) is tested on the object (dataset, cohort, benchmark) | - |
| `trained_on` | subject is trained on object | yes | subject (model) is fitted on the object (data) | - |
| `produces` | subject produces object | yes | subject process / device yields the object | obo:RO_0002234 (has output) |
| `requires` | subject requires object | yes | subject needs the object as condition or input | - |
| `enables` | subject enables object | yes | subject makes the object possible | - |
| `predicts` | subject predicts object | yes | subject (variable, model) predicts or forecasts the object | - |
| `detects` | subject detects object | yes | subject (instrument, assay, analysis) detects / identifies the object | - |
| `is_a` | subject is a object | yes | subject is an instance or subclass of the object (definition / classification) | - |
| `derived_from` | subject is derived from object | yes | subject is obtained from / extends the object | - |
| `other` | subject other relation object | no | no term above fits; the free-text relation is kept in `p_label` and the claim is flagged for review | - |

## Choosing a term

- **Association is not causation.** `associated_with` for correlations / co-occurrence; `causes`, `prevents`, `treats` only if the evidence states the effect. The checker rejects `causes` when the only wording is an association (`relation_type`).
- **Comparisons**: the subject is the one that is higher / better / faster (`outperforms`); "B is worse than A" is `A outperforms B`. The measure and the data go in `cond:`.
- **Negation** is `polarity: negative` ("did not change" -> `regulates` + negative; "does not differ" -> `differs_from` + negative). The plain triple is then **not** exported, only the claim node with its polarity, so a negative finding is never asserted as positive.
- **Values**: `has_value` with `o:` the number (and `value:` / `unit:`): subject is the measured quantity including its context ("BLEU score of X on dataset Y").
- **Observation vs theory**: `consistent_with` (+ negative for "contradicts"); `detects` for "observed / demonstrated / identified".
- **Methods and data**: `uses`, `evaluated_on`, `trained_on`, `derived_from` (material origin), `part_of`.
- `other` keeps the free text (`v:relationText`) and flags the claim for review. Prefer a controlled term.

Aliases accepted for `p:` (case and punctuation insensitive): agrees_with -> consistent_with, applies -> uses, better_than -> outperforms, binds -> interacts_with, binds_to -> interacts_with, blocks -> inhibits, builds_on -> derived_from, composed_of -> part_of, contains -> part_of, correlated_with -> associated_with, correlates_with -> associated_with, defined_as -> is_a, depends_on -> requires, downregulates -> decreases, employs -> uses, enhances -> increases, equals -> has_value, expressed_in -> located_in, extends -> derived_from, found_in -> located_in, generates -> produces, improves -> increases, induces -> increases, is -> is_a, is_consistent_with -> consistent_with, is_defined_as -> is_a, leads_to -> causes, lowers -> decreases, matches -> consistent_with, measured_as -> has_value, needs -> requires, observes -> detects, promotes -> increases, reduces -> decreases, reports -> detects, shows -> detects, superior_to -> outperforms, suppresses -> decreases, tested_on -> evaluated_on, upregulates -> increases, yields -> produces.
