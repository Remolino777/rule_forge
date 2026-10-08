# spaceplan parameter table — spaceplan-residential-catalog v0.11.0

Catalog SHA-256 `450545922efa135daa6dbbaa4be83de38705801976a09bf632285072631b034e`. Default source: Student-defined design ranges v0.1 (spaceplan v1.1, section 8); calibrate with public pre-approved plans before G1 (status **provisional**). CRC ruleset `crc-2025-habitability` v0.2.0.

## Scales

| Scale | Area min | Area max | Facade | Topology | Placement order |
|---|---|---|---|---|---|
| large | 250 | 450 | required | node | 1 |
| normal | 110 | 250 | required_if_habitable | node | 2 |
| intermediate | 35 | 110 | desirable | node | 3 |
| support | 0 | 35 | none | satellite | 4 |
| intermediate_exterior | 40 | 120 | exterior | site | — |
| large_exterior | — | — | exterior | site | — |

## Zones

| Zone | Dominant scale | Floor | Sun | Morning light | Street privacy | Content |
|---|---|---|---|---|---|---|
| social | large | ground (soft) | 1 | 0.3 | 0.3 | living, dining, open study |
| private | large | upper (soft) | 0.3 | 1 | 1 | bedrooms and baths; may be split |
| kitchen | normal | ground (soft) | 0.5 | 0.7 | 0.3 | kitchen, pantry, breakfast nook |
| service | intermediate | ground (soft) | 0 | 0 | 0 | laundry, storage, equipment |
| circulation | intermediate | any (soft) | 0 | 0 | 0 | foyer, halls, stair |
| garage | normal | ground (hard) | 0 | 0 | 0 | 1- or 2-car garage |

## Space types (sq ft)

| Space type | Zone | Scale | Habitable | Wet | Min | Target | Max | Hosts | Scale exception | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| living_dining | social | large | yes | no | 250 | 360 | 450 | — | — | provisional |
| living_room | social | large | yes | no | 200 | 280 | 400 | — | living room separated from dining may drop below the large-scale floor | provisional |
| dining_room | social | normal | yes | no | 110 | 150 | 220 | — | — | provisional |
| family_room | social | large | yes | no | 220 | 300 | 420 | — | secondary living space | provisional |
| study | social | normal | yes | no | 110 | 130 | 180 | — | — | provisional |
| kitchen | kitchen | normal | yes | yes | 110 | 170 | 250 | — | — | provisional |
| breakfast_nook | social | intermediate | yes | no | 70 | 80 | 110 | — | — | provisional |
| pantry | kitchen | support | no | no | 12 | 20 | 35 | kitchen | — | provisional |
| primary_suite | private | large | yes | no | 250 | 290 | 420 | — | — | provisional |
| bedroom | private | normal | yes | no | 110 | 140 | 200 | — | — | provisional |
| social_bath | social | intermediate | no | yes | 35 | 40 | 60 | — | — | provisional |
| primary_bath | private | intermediate | no | yes | 60 | 80 | 110 | — | — | provisional |
| bathroom | private | intermediate | no | yes | 40 | 55 | 90 | — | — | provisional |
| walk_in_closet | private | intermediate | no | no | 35 | 50 | 80 | — | — | provisional |
| closet | private | support | no | no | 6 | 12 | 30 | bedroom, primary_suite | — | provisional |
| half_bath | circulation | support | no | yes | 18 | 24 | 35 | foyer, hall | — | provisional |
| laundry | service | intermediate | no | yes | 35 | 50 | 80 | — | — | provisional |
| storage | service | support | no | no | 10 | 20 | 35 | laundry, garage_2car, garage_1car, hall | — | provisional |
| mechanical | service | support | no | no | 10 | 15 | 30 | garage_2car, garage_1car, laundry, hall | — | provisional |
| foyer | circulation | intermediate | no | no | 35 | 50 | 90 | — | — | provisional |
| hall | circulation | intermediate | no | no | 40 | 90 | 180 | — | halls grow with the number of rooms they serve | provisional |
| stair | circulation | intermediate | no | no | 40 | 60 | 90 | — | — | provisional |
| garage_1car | garage | normal | no | no | 220 | 250 | 300 | — | vehicle clearance governs, not room scale | provisional |
| garage_2car | garage | normal | no | no | 380 | 420 | 500 | — | vehicle clearance governs, not room scale | provisional |
| garage_2car_tandem | garage | normal | no | no | 400 | 440 | 520 | — | vehicle clearance governs, not room scale | provisional |
| laundry_closet | service | support | no | yes | 12 | 20 | 35 | hall, foyer | — | provisional |
| flex_room | social | normal | yes | no | 110 | 120 | 160 | — | — | provisional |
| mudroom | service | intermediate | no | no | 35 | 45 | 80 | — | — | provisional |
| work_kitchen | kitchen | intermediate | no | yes | 45 | 65 | 110 | — | — | provisional |

## Profiles (target multipliers by zone)

| Profile | social | private | kitchen | service | circulation | garage |
|---|---|---|---|---|---|---|
| balanced | 1 | 1 | 1 | 1 | 1 | 1 |
| compact | 0.85 | 0.85 | 0.85 | 0.85 | 0.85 | 1 |
| social | 1.2 | 0.95 | 1.1 | 1 | 1 | 1 |
| private | 0.95 | 1.2 | 1 | 1 | 1 | 1 |

## Typologies (garage for 2 cars, balanced profile)

| Typology | Dwelling | Label | Spaces | Net min | Net target | Net max | Gross factor | Gross estimate |
|---|---|---|---|---|---|---|---|---|
| t2_compact | house | 2 bedrooms, 1 bath | 11 | 1262 | 1645 | 2320 | 1.15 | 1892 |
| t3_standard | house | 3 bedrooms, 2 baths | 17 | 1549 | 2025 | 2950 | 1.15 | 2329 |
| t4_family | house | 4 bedrooms, 3 baths | 24 | 2023 | 2650 | 3865 | 1.12 | 2968 |
| apt_1br | apartment | apartment, 1 bedroom | 7 | 703 | 955 | 1365 | 1.08 | 1031 |
| apt_2br | apartment | apartment, 2 bedrooms | 10 | 913 | 1265 | 1855 | 1.08 | 1366 |

## Zone parts (zones split by their spaces)

| Zone | Scheme | Dwelling | Part | Space types | Min width ft |
|---|---|---|---|---|---|
| social | living_dining | house, apartment | living | living_room, living_dining, family_room | 12 |
| social | living_dining | house, apartment | dining | dining_room, study, breakfast_nook, social_bath | 9 |
| private | by_bedroom | house, apartment | suite | primary_suite, primary_bath, walk_in_closet | 11 |
| private | by_bedroom | house, apartment | bedrooms | bedroom, bathroom, closet | 9 |
| private | wet_core | apartment | suiteroom | primary_suite, walk_in_closet | 11 |
| private | wet_core | apartment | bedroomwing | bedroom, closet | 9 |
| private | wet_core | apartment | wetcore | primary_bath, bathroom | 5 |

## Space relation matrix (D direct, I indirect, absent = N)

Roles: **access** = @entry; **living** = living_room, living_dining, family_room; **dining** = dining_room, living_dining; **kitchen** = kitchen; **social_bath** = social_bath, half_bath; **primary_bedroom** = primary_suite; **bedroom** = bedroom; **private_bath** = primary_bath, bathroom; **laundry** = laundry, laundry_closet; **suite_closet** = walk_in_closet; **patio** = @patio; **work_kitchen** = work_kitchen; **mudroom** = mudroom

| Dwelling | A | B | Type | Kind | Weight | Source |
|---|---|---|---|---|---|---|
| house | access | living | D | hard | 1 | Student relation matrix D/I/N 2026-10 |
| house | access | dining | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| house | access | social_bath | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| house | living | dining | D | hard | 1 | Student relation matrix D/I/N 2026-10 |
| house | living | kitchen | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| house | living | social_bath | D | soft | 1 | Student relation matrix D/I/N 2026-10 |
| house | living | primary_bedroom | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| house | living | patio | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| house | dining | kitchen | D | hard | 1 | Student relation matrix D/I/N 2026-10 |
| house | dining | social_bath | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| house | dining | laundry | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| house | dining | patio | D | soft | 1.5 | Student relation matrix D/I/N 2026-10 |
| house | kitchen | social_bath | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| house | kitchen | laundry | D | hard | 1 | Student relation matrix D/I/N 2026-10 |
| house | kitchen | patio | D | soft | 1.5 | Student relation matrix D/I/N 2026-10 |
| house | primary_bedroom | private_bath | D | hard | 1 | Student relation matrix D/I/N 2026-10 |
| house | primary_bedroom | patio | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| house | bedroom | private_bath | D | hard | 1 | Student relation matrix D/I/N 2026-10 |
| house | bedroom | bedroom | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| house | laundry | patio | D | soft | 1 | Student relation matrix D/I/N 2026-10 |
| house | primary_bedroom | suite_closet | D | soft | 1 | Added by spaceplan (walk-in closet off the suite) |
| house | group patio_from_dining_or_kitchen | at least 1 of D:dining-patio, D:kitchen-patio | D | hard | — | Student relation matrix D/I/N 2026-10 (comedor/cocina - patio) |
| apartment | access | living | D | hard | 1 | Student relation matrix D/I/N 2026-10 |
| apartment | access | dining | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| apartment | access | social_bath | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| apartment | living | dining | D | hard | 1 | Student relation matrix D/I/N 2026-10 |
| apartment | living | kitchen | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| apartment | living | social_bath | D | soft | 1 | Student relation matrix D/I/N 2026-10 |
| apartment | living | primary_bedroom | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| apartment | dining | kitchen | D | hard | 1 | Student relation matrix D/I/N 2026-10 |
| apartment | dining | social_bath | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| apartment | dining | laundry | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| apartment | kitchen | social_bath | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| apartment | kitchen | laundry | D | hard | 1 | Student relation matrix D/I/N 2026-10 |
| apartment | primary_bedroom | private_bath | D | hard | 1 | Student relation matrix D/I/N 2026-10 |
| apartment | bedroom | private_bath | D | hard | 1 | Student relation matrix D/I/N 2026-10 |
| apartment | bedroom | bedroom | I | soft | 0.5 | Student relation matrix D/I/N 2026-10 |
| apartment | primary_bedroom | suite_closet | D | soft | 1 | Added by spaceplan (walk-in closet off the suite) |
| apartment | access | kitchen | I | soft | 0.5 | Student brief 2026-10 (kitchen via foyer in apartments) |

Semantics: D: shared door or opening; for pairs with a terminal room or the entry, also both opening onto the same foyer/hall/spine; two open rooms must touch; I: no shared door, reachable through exactly one intermediate space; N: no constraint; access: the entrance door; the foyer is circulation (transparent for D)

## Circulation network

Design width 3.5 ft (normative minimum: rule C06-HALLWAY-WIDTH); door contact 3 ft; target 15% of the footprint, warning above 20%; derived (replaced by the network): hall; private roles open only onto circulation: primary_bedroom, bedroom, private_bath, suite_closet.

| Space type | Passable | Min side ft |
|---|---|---|
| living_dining | yes | 11 |
| living_room | yes | 11 |
| dining_room | yes | 9 |
| family_room | yes | 11 |
| study | no | 8 |
| kitchen | yes | 7 |
| breakfast_nook | yes | 7 |
| pantry | no | 3 |
| primary_suite | no | 11 |
| bedroom | no | 9 |
| social_bath | no | 4 |
| primary_bath | no | 5 |
| bathroom | no | 5 |
| walk_in_closet | no | 4 |
| closet | no | 2 |
| half_bath | no | 3 |
| laundry | no | 5 |
| storage | no | 3 |
| mechanical | no | 3 |
| foyer | yes | 4 |
| hall | yes | 3.5 |
| stair | yes | 3.5 |
| garage_1car | no | 10 |
| garage_2car | no | 19 |
| garage_2car_tandem | no | 10.5 |
| laundry_closet | no | 3 |
| flex_room | no | 8 |
| mudroom | yes | 5 |
| work_kitchen | no | 5 |

## Zoning profiles by dwelling type

| Dwelling | Rule | Kind | Target | Facade role / sequence | Min contact ft | Source |
|---|---|---|---|---|---|---|
| house | entry | hard | circulation | on entry_deck | 3 | catalog |
| house | living_faces_main_street | hard | living_room, living_dining | main_street | 8 | Student design brief 2026-10 (house zoning profile) |
| house | kitchen_faces_rear | soft | kitchen | garden | 3 | Student design brief 2026-10 (house zoning profile) |
| apartment | entry | hard | circulation | on entrance | 3 | catalog |
| apartment | living_faces_exterior | hard | living_room, living_dining | exterior | 8 | Student design brief 2026-10 (apartment zoning profile) |
| apartment | bedrooms_face_exterior | hard | primary_suite, bedroom | exterior | 4 | Student design brief 2026-10 (apartment zoning profile) |
| apartment | kitchen_faces_exterior | soft | kitchen | exterior | 3 | Student design brief 2026-10 (apartment zoning profile) |
| apartment | kitchen_via_foyer | hard | kitchen | entrance -> circulation -> kitchen (never on the entrance) | — | Student design brief 2026-10 (apartment zoning profile) |

## Backyard elements (minimum green 30% of the yard reserved first)

| Element | Priority | Min | Target | Max | Min dim ft | Placement | Group | Requires | Clearances |
|---|---|---|---|---|---|---|---|---|---|
| rear_deck | 1 | 80 | 150 | 300 | 8 | attach_rear | — | — | — |
| pool | 2 | 200 | 300 | 450 | 10 | visible_center | water | — | lot_line: Z13-POOL-SPA.pool_min_to_lot_line_ft, dwelling: Z13-POOL-SPA.pool_min_to_dwelling_ft |
| spa | 3 | 40 | 64 | 100 | 6 | near_deck | water | — | lot_line: Z13-POOL-SPA.spa_min_to_lot_line_ft |
| bbq | 4 | 20 | 32 | 48 | 4 | touch_deck | — | rear_deck | — |
| shed | 5 | 30 | 64 | 120 | 5 | rear_corner | — | — | lot_line: Z14-ACCESSORY-STRUCTURE.min_to_lot_line_ft, dwelling: Z12-BUILDING-SEPARATION.to_nonhabitable_accessory_ft |
| garden_beds | 6 | 20 | 40 | 100 | 3 | along_side | — | — | — |
| covered_terrace | 7 | 120 | 200 | 320 | 10 | attach_rear | — | — | — |
| outdoor_kitchen | 8 | 30 | 48 | 80 | 5 | touch_deck | — | covered_terrace | — |

## Normative minima used by the review (CRC 2025)

| Rule | Magnitude | Value | Unit | Status | Source |
|---|---|---|---|---|---|
| C01-HABITABLE-AREA | habitable_room_area | >= 70 | sq_ft | provisional | CRC 2025 habitable room area (R304 in prior editions; verify) |
| C01-HABITABLE-DIMENSION | habitable_room_min_dimension | >= 7 | ft | provisional | CRC 2025 minimum horizontal dimension (R304 in prior editions; verify) |
| C03-GLAZING | glazing_to_floor_area | >= 0.08 | ratio | provisional | CRC 2025 natural light (R303 in prior editions; verify) |
| C03-VENTILATION | openable_to_floor_area | >= 0.04 | ratio | provisional | CRC 2025 natural ventilation (R303 in prior editions; verify) |
| C06-HALLWAY-WIDTH | hallway_clear_width | >= 3 | ft | provisional | CRC 2025 hallways (R311.6 in prior editions; verify) |

# Relative cost index — spaceplan-residential-catalog 0.11.0

Relative, dimensionless index. 1 = building 100% of the lot's normative maximum gross area with the reference mix and form. Comparative, never a quote.

Status: provisional. Source: Student-defined relative cost hypothesis, spaceplan step 6.5b (2026-10); dimensionless, never a price; validate ratios with local builders and public data before use.

| Parameter | Kind | Min | Most likely | Max |
|---|---|---|---|---|
| habitable_dry | area class coefficient | 1 | 1 | 1 |
| wet | area class coefficient | 1.3 | 1.6 | 2 |
| service | area class coefficient | 0.8 | 0.9 | 1 |
| circulation | area class coefficient | 0.8 | 0.9 | 1 |
| garage | area class coefficient | 0.45 | 0.6 | 0.75 |
| paving | area class coefficient | 0.05 | 0.1 | 0.15 |
| deck | area class coefficient | 0.2 | 0.3 | 0.45 |
| backyard | area class coefficient | 0.25 | 0.4 | 0.6 |
| stepped_footprint | form factor | 1.01 | 1.04 | 1.08 |
| polygonal_footprint | form factor | 1.03 | 1.08 | 1.15 |
| two_floors | form factor | 0.9 | 0.95 | 1.02 |
| three_floors | form factor | 0.92 | 0.97 | 1.05 |
| hillside | form factor | 1.05 | 1.12 | 1.25 |

| Reference mix class | Fraction |
|---|---|
| habitable_dry | 0.58 |
| wet | 0.12 |
| service | 0.04 |
| circulation | 0.08 |
| garage | 0.18 |

Reference dwelling: 2000 sq ft gross; hillside factor from mean slope 0.25.

| Budget level | Fraction of the lot maximum |
|---|---|
| tight | 0.45 |
| medium | 0.65 |
| ample | 0.85 |
