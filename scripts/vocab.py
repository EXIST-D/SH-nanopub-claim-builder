#!/usr/bin/env python3
"""vocab.py - controlled vocabularies of the nanopublication claim builder: relation terms, namespaces, identifier prefixes, cue patterns.

Relation terms live in an own namespace (VOCAB_NS, a placeholder you may replace with --vocab-ns). Where an established ontology term is
close in meaning the mapping is given as skos:closeMatch; every OBO Relation Ontology (RO/BFO) id below was looked up in the EBI OLS
service on 2026-11-20 and its label is recorded in `map_label`. Terms without a mapping simply have none - nothing is guessed.
"""
from __future__ import annotations

import re

VOCAB_NS = "https://example.org/np-claim-builder/vocab#"
DEFAULT_BASE = "https://example.org/np-claim-builder/"

PREFIXES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "np": "http://www.nanopub.org/nschema#",
    "prov": "http://www.w3.org/ns/prov#",
    "dct": "http://purl.org/dc/terms/",
    "oa": "http://www.w3.org/ns/oa#",
    "obo": "http://purl.obolibrary.org/obo/",
}

# term -> label, directional (subject acts on object; order matters), definition, close match (OBO id, OLS label), surface patterns (regex on stems)
RELATIONS = {
    "increases": dict(label="increases", directional=True, close="RO_0002213", map_label="positively regulates",
                      definition="subject raises the level / rate / amount / frequency of the object",
                      syn=r"increas|upregulat|up-regulat|elevat|enhanc|boost|rais|amplif|stimulat|promot|induc|augment|improv"),
    "decreases": dict(label="decreases", directional=True, close="RO_0002212", map_label="negatively regulates",
                      definition="subject lowers the level / rate / amount / frequency of the object",
                      syn=r"decreas|reduc|downregulat|down-regulat|lower|attenuat|diminish|suppress|declin|impair|degrad|hurt|harm|worsen|drop|deteriorat|abolish|limit|restrict|constrain"),
    "activates": dict(label="activates", directional=True, close="RO_0002213", map_label="positively regulates",
                      definition="subject switches on or triggers the object (pathway, enzyme, process)", syn=r"activat|trigger|switch(?:es)? on|turn(?:s)? on"),
    "inhibits": dict(label="inhibits", directional=True, close="RO_0002212", map_label="negatively regulates",
                     definition="subject blocks or switches off the object", syn=r"inhibit|block|abolish|silenc|antagoniz|repress|prevent(?:s|ed)? the activity"),
    "regulates": dict(label="regulates", directional=True, close="RO_0002211", map_label="regulates",
                      definition="subject controls the object without a stated direction of effect", syn=r"regulat|modulat|govern|control|mediat|influenc|affect|alter|chang(?:e|es|ed|ing)|direct(?:s|ed)\b"),
    "causes": dict(label="causes", directional=True, close="RO_0002410", map_label="causally related to",
                   definition="subject brings about the object (a causal claim, not a mere association)", syn=r"caus|lead(?:s)? to|result(?:s)? in|drive|driv(?:es|ing)|trigger|contribut"),
    "prevents": dict(label="prevents", directional=True, close=None, map_label=None, definition="subject stops the object from occurring", syn=r"prevent|protect against|avert"),
    "treats": dict(label="treats", directional=True, close="RO_0002606", map_label="is substance that treats",
                   definition="subject (drug, intervention) is used to treat or ameliorate the object (condition)", syn=r"treat|ameliorat|alleviat|cure|therap"),
    "associated_with": dict(label="is associated with", directional=False, close="RO_0002610", map_label="correlated with",
                            definition="subject and object co-occur / covary; no direction or causation claimed", syn=r"associat|correlat|linked to|relat(?:ed|es) to|co-?occur|covary"),
    "interacts_with": dict(label="interacts with", directional=False, close="RO_0002434", map_label="interacts with",
                           definition="subject and object physically or functionally interact", syn=r"interact|bind|bound|complex with|dimeri[sz]|co-?localiz"),
    "part_of": dict(label="is part of", directional=True, close="BFO_0000050", map_label="part of", definition="subject is a component of the object", syn=r"part of|component of|subunit of|consist(?:s)? of|compris"),
    "located_in": dict(label="is located in", directional=True, close="RO_0001025", map_label="located in",
                       definition="subject is found in / localised to the object (place, tissue, compartment, population)", syn=r"located in|localiz|found in|express(?:ed)? in|present in|occur(?:s)? in"),
    "has_phenotype": dict(label="has phenotype", directional=True, close="RO_0002200", map_label="has phenotype", definition="subject (organism, genotype) shows the object phenotype", syn=r"phenotype|exhibit|display"),
    "has_value": dict(label="has value", directional=True, close=None, map_label=None,
                      definition="subject quantity / property has the numeric value or range given as object (add value:/unit:)", syn=r"\bis\b.*\d|equal|amount(?:s)? to|measur|estimat|yield|achiev|reach|report"),
    "outperforms": dict(label="outperforms", directional=True, close=None, map_label=None,
                        definition="subject (method, treatment) does better than the object on a stated measure (condition names the measure and data)", syn=r"outperform|better than|superior to|surpass|exceed|beat|higher than|faster than"),
    "consistent_with": dict(label="is consistent with", directional=False, close=None, map_label=None,
                            definition="subject (observation, result, model) agrees with the object (prediction, theory, earlier result); use polarity=negative for 'inconsistent with'", syn=r"match(?:es|ed)?\b|consistent with|agree(?:s|d)? with|in agreement with|compatible with|reproduc(?:e|es|ed)|conform"),
    "differs_from": dict(label="differs from", directional=False, close=None, map_label=None, definition="subject and object differ on a stated property", syn=r"differ|distinct from|unlike|versus|compared (?:with|to)"),
    "uses": dict(label="uses", directional=True, close=None, map_label=None, definition="subject (study, method) employs the object (tool, dataset, technique, material)", syn=r"\buse[sd]?\b|using|employ|apply|applied|adopt|utili[sz]|based on"),
    "evaluated_on": dict(label="is evaluated on", directional=True, close=None, map_label=None, definition="subject (method, model) is tested on the object (dataset, cohort, benchmark)", syn=r"evaluat|test(?:ed)? on|benchmark|validat"),
    "trained_on": dict(label="is trained on", directional=True, close=None, map_label=None, definition="subject (model) is fitted on the object (data)", syn=r"train|fit(?:ted)? (?:on|to)|learn(?:ed)? from"),
    "produces": dict(label="produces", directional=True, close="RO_0002234", map_label="has output", definition="subject process / device yields the object", syn=r"produc|generat|yield|synthesi[sz]|secret|emit"),
    "requires": dict(label="requires", directional=True, close=None, map_label=None, definition="subject needs the object as condition or input", syn=r"requir|depend(?:s|ed)? on|need|rel(?:y|ies) on"),
    "enables": dict(label="enables", directional=True, close=None, map_label=None, definition="subject makes the object possible", syn=r"enabl|allow|permit|facilitat"),
    "predicts": dict(label="predicts", directional=True, close=None, map_label=None, definition="subject (variable, model) predicts or forecasts the object", syn=r"predict|forecast|prognos|anticipat"),
    "detects": dict(label="detects", directional=True, close=None, map_label=None, definition="subject (instrument, assay, analysis) detects / identifies the object", syn=r"detect|identif|observ|discover|find|found|reveal|show(?:s|ed|n)?|demonstrat"),
    "is_a": dict(label="is a", directional=True, close=None, map_label=None, definition="subject is an instance or subclass of the object (definition / classification)", syn=r"\bis an? \b|\bare\b|defined as|classified as|known as|refers? to"),
    "derived_from": dict(label="is derived from", directional=True, close=None, map_label=None, definition="subject is obtained from / extends the object", syn=r"derived from|extend|builds? on|adapted from|originat"),
    "other": dict(label="other relation", directional=False, close=None, map_label=None,
                  definition="no term above fits; the free-text relation is kept in `p_label` and the claim is flagged for review", syn=r"(?!x)x"),
}
REL_PATTERNS = {k: re.compile(v["syn"], re.I) for k, v in RELATIONS.items() if k != "other"}
REL_ALIASES = {"upregulates": "increases", "enhances": "increases", "promotes": "increases", "downregulates": "decreases", "reduces": "decreases", "lowers": "decreases",
               "suppresses": "decreases", "blocks": "inhibits", "induces": "increases", "leads_to": "causes", "correlates_with": "associated_with", "correlated_with": "associated_with",
               "binds": "interacts_with", "binds_to": "interacts_with", "expressed_in": "located_in", "found_in": "located_in", "improves": "increases", "better_than": "outperforms",
               "superior_to": "outperforms", "equals": "has_value", "measured_as": "has_value", "is_defined_as": "is_a", "defined_as": "is_a", "is": "is_a", "reports": "detects",
               "observes": "detects", "shows": "detects", "tested_on": "evaluated_on", "applies": "uses", "employs": "uses", "generates": "produces", "yields": "produces",
               "matches": "consistent_with", "agrees_with": "consistent_with", "is_consistent_with": "consistent_with", "depends_on": "requires", "needs": "requires", "extends": "derived_from", "builds_on": "derived_from", "composed_of": "part_of", "contains": "part_of"}


def resolve_relation(p):
    """free text -> (term, exact). exact=True when p is (an alias of) a controlled term."""
    key = re.sub(r"[^a-z]+", "_", (p or "").strip().lower()).strip("_")
    if key in RELATIONS:
        return key, True
    if key in REL_ALIASES:
        return REL_ALIASES[key], True
    for k, v in RELATIONS.items():
        if re.sub(r"[^a-z]+", "_", v["label"].lower()).strip("_") == key:
            return k, True
    # a single verb phrase that matches exactly one term's surface pattern
    hits = [k for k, rx in REL_PATTERNS.items() if rx.search(p or "") and k not in ("has_value", "is_a")]
    if len(hits) == 1:
        return hits[0], False
    return "other", False


# identifier prefixes: canonical -> (IRI builder, local-id pattern)
OBO_PREFIXES = {"GO", "CHEBI", "DOID", "HP", "NCBITaxon", "UBERON", "CL", "MONDO", "PR", "SO", "OBI", "EFO"}
ID_PATTERNS = {
    "NCBIGene": r"\d+", "UniProt": r"[A-NR-Z][0-9][A-Z0-9]{3}[0-9]|[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2}", "MESH": r"[CDQ]\d{6,9}",
    "DOI": r"10\.\d{4,9}/\S+", "PMID": r"\d{1,9}", "ORCID": r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", "arXiv": r"\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}", "ROR": r"0[a-z0-9]{6}\d{2}",
    "GO": r"\d{7}", "CHEBI": r"\d+", "DOID": r"\d+", "HP": r"\d{7}", "NCBITaxon": r"\d+", "UBERON": r"\d{7}", "CL": r"\d{7}", "MONDO": r"\d{7}", "PR": r"\d+", "SO": r"\d{7}", "OBI": r"\d{7}", "EFO": r"\d{7}",
    "RRID": r"[A-Za-z_]+:?\w+", "Wikidata": r"Q\d+", "ISBN": r"[\dX-]{10,17}",
}
ID_CANON = {k.lower(): k for k in ID_PATTERNS}


def curie_iri(curie):
    """'NCBIGene:7157' -> IRI string, or None if prefix unknown / local part malformed."""
    m = re.fullmatch(r"([A-Za-z]+):(\S+)", (curie or "").strip())
    if not m:
        return None
    pre = ID_CANON.get(m.group(1).lower())
    loc = m.group(2)
    if not pre or not re.fullmatch(ID_PATTERNS[pre], loc, re.I if pre in ("arXiv", "UniProt") else 0):
        return None
    if pre in OBO_PREFIXES:
        return "http://purl.obolibrary.org/obo/%s_%s" % (pre, loc)
    return {"DOI": "https://doi.org/" + loc, "PMID": "https://pubmed.ncbi.nlm.nih.gov/%s/" % loc, "ORCID": "https://orcid.org/" + loc, "arXiv": "https://arxiv.org/abs/" + loc,
            "ROR": "https://ror.org/" + loc, "Wikidata": "https://www.wikidata.org/entity/" + loc}.get(pre) or "https://identifiers.org/%s:%s" % (pre.lower(), loc)


# ------------------------------------------------------------------------------------------------ cue patterns
HYPOTHESIS = re.compile(r"\b(we\s+(?:hypothes[ie]s?e?|propose|conjecture|speculate|postulate)|hypothes[ie]s|it\s+is\s+(?:possible|conceivable)|one\s+possibility|remains?\s+to\s+be\s+(?:tested|determined|established)|if\b[^.]{3,80}\bthen\b|would\s+(?:imply|suggest))", re.I)
HEDGE_WORD = re.compile(r"\b(may|might|could|possibly|perhaps|probably|likely|unlikely|suggest(?:s|ed|ing)?|appear(?:s|ed|ing)?(?:\s+to)?|seem(?:s|ed|ing)?|tend(?:s|ed)?\s+to|potentially|presumably|indicat(?:e|es|ed|ing)|consistent\s+with|putative|preliminary)\b", re.I)
UNIVERSAL = re.compile(r"\b(all|every|always|never|none|no\s+one|universally|invariably|in\s+general|generally|any|entirely|completely|without\s+exception|consistently|across\s+all)\b", re.I)
SCOPE = re.compile(r"\b(in\s+(?:\w+\s+){0,2}(?:mice|mouse|rats?|patients?|humans?|adults?|children|women|men|participants|volunteers|cells?|vitro|vivo|silico|samples?|cohorts?|populations?|trials?|subjects)"
                   r"|among\s+[^,.;()]{3,60}|under\s+[^,.;()]{3,50}(?:conditions?|settings?|regimes?|protocols?)|at\s+(?:a\s+)?(?:temperatures?|pressures?|concentrations?|doses?)\s+[^,.;()]{2,30}"
                   r"|(?:only|solely|except|unless|provided\s+that|as\s+long\s+as)\s+[^,.;()]{3,60}|(?:on|using|with|across)\s+(?:both\s+)?(?:the\s+)?[A-Z][^,.;()]{2,70}?\s+(?:dataset|data\s+set|benchmark|corpus|cohort|test\s+set|task)s?"
                   r"|for\s+(?:the\s+)?(?:case|range|regime|limit)\s+of\s+[^,.;()]{3,50}|after\s+\d+\s+\w+|(?:during|following)\s+[^,.;()]{3,40}|when\s+[^,.;()]{4,60})", re.I)
PASSIVE = re.compile(r"\b(?:(?:worse|lower|less|smaller|slower|poorer|weaker|inferior|fewer)\s+(?:\w+\s+){0,3}?than|inferior\s+to|below)\b|\b(?:(?:was|were|is|are|been|being|be)\s+(?:\w+ly\s+)?\w+(?:ed|en|wn|nt)\b|caused\s+by|due\s+to|driven\s+by|mediated\s+by|regulated\s+by|induced\s+by|inhibited\s+by|blocked\s+by|followed\s+by)\b.{0,60}?\bby\b|\b(?:caused|driven|mediated|regulated|induced|inhibited|blocked|explained|accounted\s+for|outperformed|exceeded|surpassed)\s+by\b|\bdue\s+to\b", re.I)
CITE_NUM = re.compile(r"\[\s*(\d+(?:\s*[-–,;]\s*\d+)*)\s*\]|\(\s*(\d+(?:\s*[-–,;]\s*\d+)*)\s*\)(?=[\s.,;]|$)|\^(\d+(?:[,-]\d+)*)")
CITE_AUTHOR = re.compile(r"\(?\b([A-Z][A-Za-z'’-]+)(?:\s+(?:et\s+al\.?|and\s+[A-Z][A-Za-z'’-]+|&\s+[A-Z][A-Za-z'’-]+))?,?\s*\(?((?:19|20)\d{2}[a-z]?)\)?")
BACKGROUND = re.compile(r"\b(previous\s+(?:studies|work|works|research|reports?|literature)|prior\s+(?:work|studies|research)|earlier\s+(?:work|studies)|recent(?:ly)?\s+(?:studies|work|reports)|(?:it\s+)?(?:has|have)\s+been\s+(?:shown|reported|demonstrated|suggested)|(?:is|are)\s+(?:known|well[- ]known|widely)|et\s+al\.?|have\s+(?:shown|reported|demonstrated))\b", re.I)
SELF = re.compile(r"\b(we|our|this\s+(?:study|paper|work|article|analysis)|here\s+we|in\s+this\s+(?:study|paper|work)|the\s+present\s+(?:study|work))\b", re.I)

NEG_EXTRA = re.compile(r"\b(contradict(?:s|ed|ing)?|refut(?:e|es|ed)|reject(?:s|ed)?|disprov(?:e|es|ed)|inconsistent|rather\s+than|instead\s+of|in\s+contrast\s+to|no\s+longer|absent|negligible)\b", re.I)
CLAIM_TYPES = ("finding", "method", "data", "definition", "background", "limitation", "hypothesis", "recommendation", "other")
MODALITIES = ("asserted", "hedged", "hypothesis")
POLARITIES = ("positive", "negative")
STATUSES = ("reported", "unsupported", "conflict", "unclear", "not_reported")
