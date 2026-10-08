# Validation protocol for the cultural layer (spaceplan step 6.5c)

Every cultural aspect, preset value, kitchen typology and culture rule in
`spaceplan/data/catalog/household_catalog.json` is a **provisional hypothesis**: an editable starting
point, never a characterization of any group. This protocol turns them into measured findings before
the capstone report cites them.

## 1. What is being tested

| Hypothesis | Catalog element | Observable in a plan |
|---|---|---|
| Kitchen area share is larger with intensive cooking and high ventilation priority | C05, `kitchen` area factor | Kitchen net area / total net area |
| Kitchen–living relation varies (open, separable, closed) | `kitchen_living_relation`, kitchen typologies | Wall or door between kitchen and living; opening width |
| Dining room sized for extended family | C01 | Dining net area; seats drawn |
| Laundry next to the kitchen and a service yard vs. near the bedrooms | C06, C07 | Door graph distance laundry–kitchen and laundry–bedrooms |
| Garage → mudroom → kitchen sequence | C09 | Door path garage → kitchen through a drop zone |
| Covered terrace / outdoor kitchen vs. lawn and pool | C10–C13 | Site plan elements and their areas |

## 2. Data

1. **Pre-approved plans** of the pilot region (licence verified) — compliant, real controls.
2. **Donated plans** with the signed cession form (plan v3.0, F0) — never used to train models.
3. **Short structured interviews** (5–8) with local architects and builders: rank the aspects by how
   often clients ask for them; no personal data of clients is recorded.

No plan is labelled with the ethnicity of its owner. Plans are labelled only with the **observable
aspects** of section 1; the hypothesis tested is whether those aspects co-occur as the presets assume,
not who lives there.

## 3. Procedure

1. Measure the observables of section 1 in every plan (manual, with the extractor when available).
2. For each aspect, report the distribution of values and the co-occurrence matrix between aspects.
3. A preset is **supported** when its aspects co-occur above chance (permutation test, Benjamini–Hochberg
   across aspects); otherwise its values are reported as unsupported and kept only as client options.
4. Calibrate area factors (C01, C05) to the observed medians with bootstrap intervals; narrow the
   cost coefficient ranges the tornado flagged first.
5. Record source, date and status change (`provisional` → `verified`) in the catalog for each value.

## 4. Reporting language

"Tendency used as an editable starting point" — never "Latino families want…" or "Anglo households
need…". The report shows the aspect table, the evidence for each aspect, and states that the presets
are a proof of concept for preference-driven programming.
