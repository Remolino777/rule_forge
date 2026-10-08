# spaceplan — steps 1–6.6 (step 6.6: area analysis per lot, vertical schemes, IC/IO)

Part of **Municipal Permit Intelligence** (MS-AAI capstone, University of San Diego).
Module design: `03_Modulo_spaceplan_Protodistribucion_v1_1.pdf`. Pilot zone: SDMC RS-1-7, Clairemont–Navajo.

## What this version does

**Step 6.6 — area analysis per lot (new).** `spaceplan areas` crosses the 10 pilot lots (4 new: shallow 50×95,
narrow 40×125, hillside 50×100 with the 50 % coverage limit, flag lot 70×80 behind a 20 ft pole) with the 7
archetypes × 3 cultural profiles and the five program profiles of 6.5d. Each program is split over floors by the
**vertical schemes** V0–V5 (`lib/vertical_split.py`, catalog `vertical_schemes`: single floor, private upstairs,
primary suite down, generations by floor, partial upper floor, social upstairs with a view); the household weighs
the metrics (stair independence, supervision, separation, open area, upper-floor efficiency, frontage, cost)
through catalog multipliers and never excludes a scheme; mobility pins keep a suite together on the ground floor.
**Building indices** as a ratio-rule family in the DSL (`Z15-BUILDING-INDICES`, `lib/building_indices.py`):
construction index IC (= FAR) and occupancy index IO (normative only on hillside lots), per floor, with the
garage-included (default) and garage-excluded readings. Stages: E0 indices, containment and frontage
(`lib/area_budget.py`), E1 measured site per strategy (`site_partition.measure_footprint`), E2 full one-floor zoning
of the best cells. Outputs: decision map, area budget per floor, IC–IO chart per lot, best scheme per household
(`examples/area_matrix/`), CSV tables and `docs/area_analysis.md`. Flag lots: `lib/flag_lot.py` (provisional).
Tests: `tests/test_area_matrix.py` (MR-A1..A7, MR-V1..V5).

**Step 6.5d — program portfolio and review sheets.** `lib/program_profiles.py` builds one **expansion curve**
per household and lot: from the required tier, the greedy step with the best program-quality gain per unit of
relative cost index (add a need instance, apply a substitution such as living-dining → living + dining or bedroom →
suite, upgrade a zone from compact to balanced size, add a car), under the normative (FAR) and budget ceilings.
**Minimum** = start, **maximum** = last point (with the governing ceiling), **optimum** = knee of quality vs cost
(`lib_aux/knee.py`). **Staged** = minimum today + expansion to the next-stage optimum (cost today + later works
factor, staging premium); **accessible** = optimum with a ground-floor bedroom and full bath, larger bath and bedroom
(catalog `accessibility`). Area feasibility per profile (fits one floor / needs two floors / exceeds the code);
`--zone` zones each distinct profile that fits. `plot_review_sheet` draws a scaled review plan (dimensions, doors,
area schedule, legend) with **automatic observations** (`lib/review_notes.py`: weak patio links, private areas
reached through social rooms, kitchen without garden, suite without garden, patio doors from private rooms, areas
below target, circulation, garden, backyard exclusions); `plot_portfolio_sheet` draws the curve with the profiles
and ceilings. Labels and note templates live in the catalog (`display`, es/en). Diagnosis of the anglo profile:
breakfast nook moved to the social zone (catalog 0.10.0) and one bounded **search retry** when zone schemes exist
but no space layout is found (`circulation.search_retry`, off inside the correction search). CLI:
`spaceplan profiles BRIEF|ARCHETYPE [--culture] [--budget] [--zone] [--sheets DIR] [--lang es|en]`.
Tests: `tests/test_profiles.py` (MR-P1..MR-P5). Example sheets: `examples/sheets/`.


**Step 6.5c — cultural layer (new).** The client may choose a cultural profile (`latino`, `anglo`, `mixed`,
`custom`); a profile is only a **preset of nine explicit aspects** (kitchen–living relation, social center,
ventilation, dining capacity, outdoor cooking, entry sequence, laundry location, bath per bedroom, patio use) that
the client sees and edits (`culture_aspects`). Culture rules read the aspects, never the label; without a profile no
culture rule fires. A **kitchen typology** (open with island, semi-open separable, closed ventilated, double with a
`work_kitchen`) is selected from the aspects (or chosen) and applied as a bundle of effects. New culture-only effects:
`type_area_factor`, `relation_override` (D/I/N by matrix role), `anchor_override`, `backyard_element`,
`backyard_green`. `lib/culture.py` merges them into the brief's `relation_overrides`, `zoning_overrides` and
`backyard_program` — **what the brief states explicitly wins**, and the package reports what was overridden.
Culture only adds or raises: it never removes a space required by the household. New backyard elements
`covered_terrace` and `outdoor_kitchen`; placed backyard works enter the cost sheet (class `backyard`). CLI:
`spaceplan household ARCHETYPE --culture latino|anglo`. Tests: `tests/test_culture.py` (MR-K1..MR-K5, ethics).
Validation plan for the hypotheses: `docs/culture_validation_protocol.md`.


**Step 6.5b — relative cost index (new).** Every option becomes a **quantity sheet** (`lib/quantities.py`): gross
area by class (habitable dry, wet, service, circulation, garage), area by floor, footprint, roof, facade perimeter,
stairs, wet cores, exterior paving and deck, footprint form and slope, each item tagged measured / derived /
estimated. Interchangeable **cost models** (`lib/cost_models.py`: `base`, `weighted`, `shape`) read only the sheet;
the index divides by the same model on a synthetic **reference sheet**, so 1 = the lot's normative maximum
(reading `lot`) or the catalog reference dwelling (reading `reference_dwelling`). Coefficients are dimensionless
ranges (min, most likely, max) in `residential_catalog.json` → `cost_index` (catalog 0.8.0, provisional). A relative
**budget** (`tight|medium|ample` or a fraction; brief 0.4) gives the buildable maximum, which ceiling governs, and a
staged-construction suggestion (`lib/budget.py`). A **tornado** (`lib/cost_sensitivity.py`) ranks the parameters by
how much they move the index or the decision between two options and flags those that reverse it. Package 0.9 has a
`cost` block; `spaceplan household` prints the tier indices. CLI: `--budget`, `--cost-model`. No money anywhere
(tested). Tests: `tests/test_cost.py` (MR-C1..MR-C5).


**Step 6.5a — household model and archetypes (new).** The program no longer has to be a fixed typology: a household
block (members with age, mobility and remote work; social life, guests, cooking, vehicles, pets; trajectory events)
or an `archetype_id` preset is turned into **needs per tier** — required (minimum), preferred, desirable — by a
bedroom policy plus 36 declarative rules in `data/catalog/household_catalog.json` (each with source and status).
Each tier becomes a brief program (`program_from_needs`) reviewed against the catalog and the CRC. The household is
advanced by its horizon (aging + events) and the **growth delta** says what the next stage adds. A brief may carry
`household` instead of `program` (brief 0.3); the package gets a privacy-minimized `household` block (package 0.8).
Domain-free predicate/number evaluator in `lib_aux/predicates.py`. New space types `flex_room`, `mudroom`
(catalog 0.7.0). CLI: `spaceplan household ARCHETYPE|FILE.json [--tier] [--no-next]`, `--list`, `--rules-markdown`.
Metamorphic tests MR-H1..MR-H5 and a fair-housing test in `tests/test_household.py`. Rules table:
`docs/household_rules.md`; outputs for the 7 archetypes: `examples/household_archetypes.txt`.


**Step 6 — strategy B, irregular and fan lots (new).** `lib_aux/section.py` integrates over the setback envelope
exactly (strip areas, area-driven cuts, best k-step union). `StrategyB("rectangle")` realizes each band as a step as
wide as the envelope allows over its depth (shoulder facades where a step is wider; wedges kept as polygonal reserve);
`StrategyB("polygonal")` follows the oblique lot lines (trapezoidal edge cells with a governing core rectangle and a
CRC-aware polygonal extension of the spaces, `lib/polygonal.py`). Both widen columns to their minimum (zone minimum,
driveway for the garage) trading area inside the band up to `zoning.max_area_shift`. A joint corridor at the step
junction (`carve_joint`) is the stepped alternative to the full spine. Strategy `auto` (catalog `realization`) keeps A
when its rectangle uses >= 80 % of the envelope. When the one-floor option does not zone, `main/run_corrections.py`
searches strategy x garage layout (as brief / tandem / one car) x front recess by cost (catalog `corrections`),
returns the minimal correction and the Pareto frontier cost vs scheme score. CLI: `--strategy`, `--no-corrections`.
The space level enumerates cell options best-first (`ranked_product`). Package schema 0.7, catalog 0.6.1.

1. **Step 1 — schemas.** `brief.schema.json` (input) and `package.schema.json` (output), JSON Schema 2020-12,
   closed (`additionalProperties: false`), plus semantic checks (ids, streets ↔ frontage edges, relation
   endpoints, alternative groups as "at least k of n" hyperedges, mandatory/forbidden conflicts).
2. **Step 2 — capacity (layer 0).** Polygonal setback envelope (straight or arc edges, concave lots), rule
   variants read from the ruleset (cul-de-sac, front slope, shallow/deep/alley rear, narrow-lot sides, FAR
   table and hillside, hillside coverage, height/overlay map, third floor, angled plane reported),
   strategy A (largest inscribed rectangle aligned to the front), garden-preference bound, floors, three
   feasibility levels, active constraint (normative vs effective) and false-infeasible detection.

3. **Step 3 — catalog.** `data/catalog/residential_catalog.json` (zones, scales, 23 space types,
   profiles, site-zone parameters, 3 typologies), validated by `catalog.schema.json`. Typologies expand
   into a brief program (`spaceplan program t3_standard --garage 2`), satellites get hosts, zone budgets
   are derived. Every package now carries a `program_review` (catalog ranges + CRC 2025 habitability
   minima from `data/rules/crc_2025_habitability.json`). Parameter table with sources:
   `docs/parameter_table.md` (`spaceplan catalog --markdown docs/parameter_table.md`).
   Package schema bumped to 0.2 (new required block `program_review`); brief stays 0.1 with optional
   `space_type` and `host_space_id`.

4. **Step 4 — site protodistribution (layer 1).** For every floor count allowed by height, the lot is
   partitioned (polygon differences in the front frame) into footprint, garden, side yards and the front:
   driveway at the curb cut, entry deck on the front facade, walkway (independent or branching from the
   driveway) and front green. Checks: front paving <= 60 % and vehicle count (131.0447), deck projection
   <= min(6 ft, 50 % of setback) (131.0461(a)(6)), footprint inside the envelope, garden area/depth and
   max floors (preferences), equipment room in a side yard (131.0461(a)(5)). When paving fails, minimal
   corrections are proposed. Orientation: compass azimuth and exposure (sun by latitude, morning light,
   afternoon shade, street exposure) for every lot line and footprint facade, plus a zone-facade affinity
   matrix for step 5. `spaceplan capacity BRIEF --site-plot site.png`. Package schema 0.3.

5. **Step 5 — one-floor zoning (layer 1c) and the realization interface.** `lib/realization.py` defines
   the interchangeable `RealizationStrategy` (same interface for strategies A, B and C) and strategy A:
   the inscribed rectangle sliced into a front and a rear band of columns, each column stacking up to two
   zones (exact areas). `lib/zoning.py` enumerates every topology (band split, column grouping, order,
   private zone joined or split), prunes by required facades, rejects hard violations derived from the
   brief (mandatory/forbidden adjacency, k-of-n groups, garden/deck/driveway facades, catalog minimum
   widths, garage vehicle depth) and ranks the rest by relations, orientation and shape. Output: a
   catalog of up to six distinct schemes per one-floor site option, with failure statistics.
   Multi-floor options are deferred to stacking (step 7). `--zoning-plot zoning.png`. Package schema 0.4.

**Step 5 revision (2026-10).**
- *Dwelling types.* Brief 0.2 has `dwelling_type` (`house` | `apartment`). Apartments describe a `unit`
  (polygon, edge roles `access` / `exterior` / `party_wall`, entrance) instead of a lot; the normative capacity
  layer is out of the pilot scope for them, space planning runs on the unit.
- *Facade roles.* The access side is always the front band (street for houses, corridor for apartments); each
  facade carries roles (main_street, street, garden, side_yard, exterior, access, party_wall). Orientation is
  scored only on exterior facades.
- *Zoning profiles (catalog).* House: living room on the main street (hard), kitchen toward the rear (soft).
  Apartment: entry foyer on the entrance, kitchen reached through the foyer and never on the entrance (hard),
  living room and bedrooms on an exterior facade (hard), kitchen exterior (soft). Any anchor can be set to
  `hard`, `soft` or `off` from the brief (`zoning_overrides`).
- *Zone parts by spaces.* Social splits into living / dining and private into suite / bedrooms following the
  program's spaces; satellites (closets, laundry closet, pantry) count inside their host's cell. All split
  subsets and all compliant footprint candidates are searched.
- *Faster exhaustive search.* Column dimensions depend only on the band, so infeasible columns are removed
  before ordering (same valid set as brute force, tested; ~90 s -> ~0.1 s per lot).
- *No-scheme diagnostics.* When nothing fits, the package reports the frontage the access side needs against the
  footprint width (e.g. living room + 2-car garage + foyer = 36 ft on a 33 ft fan-lot footprint).
- *Backyard program (layer 1d).* Rear deck, pool or spa, barbecue, shed and garden beds enter by priority after
  reserving a minimum green fraction (30 % default, brief override); each has min/target/max area and a minimum
  dimension; one water element; the barbecue needs the deck; clearances to lot lines and to the dwelling come
  from the ruleset (131.0450 verified; pool/spa/accessory values are placeholders). Placed and excluded
  elements are reported with reasons.

**Step 5 revision 2 (2026-10): circulation and the relation matrix.**
- *Relation matrix D/I/N* (`relation_matrix` in the catalog, per dwelling type, brief `relation_overrides`): roles map
  space types (access = entrance door, living, dining, kitchen, social_bath, primary_bedroom, bedroom, private_bath,
  laundry, suite_closet, patio). D = shared door/opening (two open rooms must touch; with a terminal room or the
  entry also through a shared foyer/hall/spine); I = no shared door, one intermediate space. Hard core D pairs plus
  the hard group "dining or kitchen opens to the patio".
- *Circulation is a network* (`lib/circulation.py`): door graph; passable vs terminal spaces; private rooms open only
  onto circulation or en-suite (bedroom -> its bath, never the reverse); every space reachable from the entry through
  passable spaces. Halls from the program are replaced by circulation carved from the cells it serves: a hall along
  a cell side, an optional spine between the bands (its area taken from every zone) and door-to-door strips through
  passable rooms. Design width 3.5 ft vs CRC minimum 3 ft (provisional). Circulation fraction reported.
- *Two-level search*: zones (exhaustive, with cheap front pre-check, early exit and matrix necessary conditions) then
  spaces inside each cell (`lib/space_layout.py`: guillotine subdivision with minimum-dimension-aware spans, optional
  carved hall, capped combinations), checked globally (reachability, net areas, hard D pairs).
- *Strategy A extended*: through column (up to 3 zones, front to rear, e.g. living-dining great room), central
  spine, wet-core partition (apartments), small service zone hosted in the kitchen or garage cell (mudroom),
  every compliant entry-deck position offered by the site layer.

Every magnitude is a `Quantity` with `verified | provisional | undeterminable` status and sources.
No normative number lives in the code: values come from `data/rules/sdmc_rs_1_7_capacity.json`.

## Layout
```
spaceplan/main/     workflow (run_capacity.py) and CLI (cli.py)
spaceplan/lib/      domain: enums, rules, lot, boundaries, lot_metrics, rule_variants, capacity,
                    scope, relation_graph, schema_validation, package, visualize,
                    catalog, program_builder, program_review, catalog_table,
                    orientation, site_partition, realization, zoning,
                    unit, backyard, relation_matrix, circulation, space_layout
spaceplan/lib_aux/  helpers without zoning knowledge: geometry, quantity, hashing, json_io, tolerances
spaceplan/data/     schemas/, rules/ (SDMC RS-1-7, CRC 2025), catalog/, briefs/ (4 houses, 2 apartments)
tests/              291 tests: schemas, geometry, rule variants, capacity, catalog, program, orientation,
                    site partition, scope, architecture, CLI
docs/               parameter_table.md (generated)
examples/           generated packages, debug plots and expanded typology programs
```
Layering is enforced by `tests/test_architecture.py`: `lib_aux` imports nothing from `lib`/`main`,
`lib` never imports `main`, and nothing imports the extractor/verifier packages (`geom`, `vision`,
`engine`, `ruleforge`).

## Usage
```bash
pip install -e ".[dev]"
spaceplan validate spaceplan/data/briefs/interior_50x100.json
spaceplan capacity spaceplan/data/briefs/fan_curve_35_80x100.json -o pkg.json --plot fan.png
spaceplan areas --zone-top 2 --sheets out/figures --tables out          # step 6.6, 10 pilot lots
spaceplan areas fan_cul_de_sac_35_80x100 --households empty_nest.anglo,teens_family.latino --scheme V5
pytest --cov=spaceplan
```

## Provisional assumptions (flagged in every package)
- Height 24 ft (Table 131-04D note 4 offers 24/30; 131.0444(b) and 113.0270 pending) and floor-to-floor 10 ft.
- Lot width/depth on irregular lots: default `mean_width` and `front_rear_midpoints`; all methods are run
  and reported in `sensitivity` (SDMC Ch. 11 pending).
- Setback distance read as euclidean distance to the lot line; checked against the perpendicular reading.
- Angled building envelope (131.0444) reported, not applied geometrically.
- Garden bound uses a front-anchored footprint spanning the envelope; exact partition comes in step 4.
- Entry deck counted as paving (131.0447 treatment pending); deck height <= 15 ft and >= 40 % open are
  deferred to elevations. Footprint is a front-anchored rectangle inside strategy A (equal floors; the
  stair added in step 7 will enlarge it). Front setback lines are taken parallel to the front chord.
- PLACEHOLDERS (verified=false): pool 5 ft / spa 3 ft from lot lines, pool 5 ft from the dwelling, accessory
  structures 3 ft from lot lines; pool safety barrier deferred. Whether a shed counts toward FAR is pending.
- Apartments: no multifamily zoning or CBC R-2 checks; habitability minima only.
- Circulation strips use the L distance between doors; hall width 3.5 ft design (CRC 36 in to verify).
- Level-2 search is capped (zone schemes considered, combinations per scheme): not exhaustive.
- Zone areas = net targets scaled to fill the footprint (walls and circulation spread pro rata); zone parts follow
  their spaces; zone minimum widths and the 3 ft contact are catalog design values.
- Orientation model: sun = w cos(az - equator)+ + (1 - w)|sin az|, w = min(1, |lat|/30) (catalog parameter).
- Catalog ranges, profiles and orientation weights are student-defined (status provisional) until
  calibrated with public pre-approved plans; no weight is learned from ceded plans.
- CRC 2025 values (70 sq ft, 7 ft, 8 % / 4 %) and the kitchen exemption are provisional (section numbers to verify).
- `verified: true` in the ruleset means "transcribed with citation from the pilot-zone document";
  values must be re-checked against the official SDMC before freezing the golden rules (gate G0).

## AI use declaration (USD policy)
Design, code and tests were produced with assistance from Claude (Anthropic) from the student's
specifications and documents; the student reviewed and is responsible for the result. Declare this
in the capstone report.

## License
Code: Apache-2.0. Benchmark data: CC-BY (project decision, plan v3.0).
