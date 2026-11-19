# Review checklist

Machine-extracted nanopublications: nothing here has been reviewed by a person. Tick each item after comparing with the paper (page / bbox / quote are in `nanopubs.json`).

## Source S1
- file: `mini_paper.md` (sha256 3e471272bcfe00cc)
- title: Soft-Substrate Culture Raises Osteoblast Mineralisation: A Fictional Example Paper | authors: Mara Lindqvist; Tomas Okafor; Yuki Hartmann | year: 2024 | venue: Journal of Imaginary Biomaterials | doi: 10.9999/jib.2024.0042
- origin of the values: doi=front-matter/header text (high); title=title block (high); authors=front matter of page 1 (medium); year=most frequent year in the front matter (low); venue=header/footer/front text of page 1-2 (low)
- [ ] confirm bibliographic fields against the first page

## Claims

| id | conf | modality | origin | claim | evidence | to check |
|---|---|---|---|---|---|---|
| npbfd9b15e4dcf | high | asserted | this_paper | Mineralised nodule area on 10 kPa gels is higher than on 40 kPa gels (2.3-fold). | E007.1 pNone | - |
| np37d1ca11716b | medium | asserted | this_paper | Mineralised nodule area on 1 kPa gels does not differ significantly from that on 40 kPa gels. | E007.2 pNone | - |
| np2dbe9bf36381 | high | asserted | this_paper | Nodule area does not correlate with cell density at day 21. | E007.3 pNone | - |
| np6014ebf52a44 | high | asserted | this_paper | The fraction of nuclei with nuclear YAP is 31% on 10 kPa gels. | E008.1 pNone | - |
| np52d767d901bc | high | asserted | this_paper | The fraction of nuclei with nuclear YAP is 58% on 40 kPa gels. | E008.1 pNone | - |
| np2dd75a0c2921 | medium | asserted | this_paper | YAP signalling mediates part of the stiffness response of osteoblasts. | E008.3 pNone | identifier_origin |
| npddcff292cf62 | high | asserted | this_paper | The YAP inhibitor verteporfin reduces nodule area on 40 kPa gels by 22%. | E008.2 pNone | - |
| np53595a39b370 | high | asserted | this_paper | Verteporfin does not change nodule area on 10 kPa gels. | E008.2 pNone | - |
| np564fb57682bd | high | asserted | this_paper | In the human osteosarcoma line Saos-2, nodule area does not differ between 10 kPa and 40 kPa gels. | E009.1 pNone | - |
| npcfa20edd8d35 | medium | asserted | this_paper | Osteoblasts were cultured on polyacrylamide gels with Young's modulus of 1, 10 or 40 kPa. | E006.2 pNone | - |
| np41f8f07dea83 | high | asserted | this_paper | The primary osteoblasts were isolated from the calvaria of neonatal Sprague-Dawley rats. | E006.1 pNone | - |
| np008af33d9d49 | high | asserted | this_paper | YAP localisation was scored by immunofluorescence in at least 200 nuclei per gel. | E006.4 pNone | - |
| npd9a1a26e75a0 | medium | asserted | this_paper | Donor variability was not assessed because all experiments used cells from a single litter. | E010.2 pNone | relation_free_text |
| np92da0b759a08 | medium | hypothesis | this_paper | Gel stiffening during culture may contribute to the observed result. | E010.4 pNone; E007.1 pNone | - |
| npa19659fc2153 | high | asserted | cited | Substrate stiffness influences stem cell fate (cited background). | E005.1 pNone | - |
| np355f3f85edc0 | high | asserted | cited | Matrix elasticity directs lineage specification of mesenchymal stem cells (Engler et al.). | E005.2 pNone | - |
| np64b69cfe6903 | high | hypothesis | background | It has been proposed that stiffer matrices promote osteogenic differentiation. | E005.3 pNone | - |
| npf461e370f3db | high | asserted | this_paper | The findings of this study contradict the view that stiffer matrices always promote osteogenic differentiation. | E010.1 pNone | - |
| np800edf4676ae | low | asserted | this_paper | The effect of substrate stiffness on mineralisation is mediated by integrin beta-1. |  | low_confidence, unsupported |

## Always verify by hand
- relation direction and polarity of every `low`/`medium` claim (the checker is lexical and cannot prove meaning)
- that the quote really supports the whole claim, including conditions
- identifiers marked `asserted by the claim author`
- claims attributed to cited work: open the cited reference
