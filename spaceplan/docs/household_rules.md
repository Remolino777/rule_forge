# Household rules — mpi-household-model 0.2.0

Tiers: R = required (minimum), P = preferred, D = desirable. Every value is a design hypothesis with its status; none is an occupancy limit.

| Rule | Layer | When | Effects | Status | Source |
|---|---|---|---|---|---|
| H01-KITCHEN | household | always | kitchen x 1 [R/P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H02-SOCIAL-COMBINED | household | always | living_dining x 1 [R] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H03-SOCIAL-SMALL | household | members le 3 and social_life eq intimate | living_dining x 1 [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H04-SOCIAL-SPLIT | household | not (members le 3 and social_life eq intimate) | living_room x 1 [P/D]; dining_room x 1 [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H05-FAMILY-ROOM | household | minors ge 1 and members ge 4 | family_room x 1 [D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H06-FAMILY-ROOM-GATHERINGS | household | social_life eq large_gatherings | family_room x 1 [P/D]; social area x1.15 [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H07-PANTRY | household | always | pantry x 1 [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H08-PANTRY-INTENSIVE | household | cooking eq intensive | pantry x 1 [R]; kitchen area x1.1 [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H09-BREAKFAST-NOOK | household | cooking in ['daily', 'intensive'] and members ge 3 | breakfast_nook x 1 [D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H10-ENTRY | household | always | foyer x 1 [R/P/D]; hall x 1 [R/P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H11-BATH-MINIMUM | household | always | bathroom x 1 [R] | provisional | CRC 2025 sanitation (one water closet, lavatory and bathtub or shower per dwelling; R306 in previous editions; verify 2025 numbering) |
| H12-BATH-SHARED | household | always | bathroom x secondary_bedrooms_preferred divide_by=2 round=ceil min=1 [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H13-BATH-SHARED-ADULTS | household | unpartnered_adults ge 3 | bathroom x secondary_bedrooms_required divide_by=2 round=ceil min=1 [R]; bathroom x secondary_bedrooms_preferred min=1 [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H14-PRIMARY-BATH | household | primary_rooms ge 1 | primary_bath:primary x 1 [P/D]; walk_in_closet:primary x 1 [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H15-PRIMARY-ACCESSIBLE-REDUCED | household | primary_accessible eq reduced | primary_bath:primary x 1 [R/P/D] ground | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H16-PRIMARY-ACCESSIBLE-ANTICIPATED | household | primary_accessible eq anticipated | primary_bath:primary x 1 [P/D] ground | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H17-ACCESSIBLE-BATH-REDUCED | household | accessible_rooms_reduced ge 1 | bathroom:accessible x accessible_rooms_reduced [R/P/D] ground; bedroom:accessible en_suite bathroom:accessible [R/P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H18-ACCESSIBLE-BATH-ANTICIPATED | household | accessible_rooms_any ge 1 | bathroom:accessible x accessible_rooms_any [P/D] ground; bedroom:accessible en_suite bathroom:accessible [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H19-HALF-BATH-SOCIAL | household | social_life in ['frequent', 'large_gatherings'] | half_bath x 1 [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H20-HALF-BATH | household | always | half_bath x 1 [D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H21-WORK-MINIMUM | household | wfh_count ge 1 | flex_room:work x 1 [R]; flex_room:work near @entry [R] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H22-WORK-STUDY | household | wfh_count ge 1 | study:work x wfh_count [P/D]; study:work near @entry [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H23-GUESTS-RARE | household | guests eq rare | flex_room:guest x 1 [D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H24-GUESTS-FREQUENT | household | guests eq frequent | flex_room:guest x 1 [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H25-GUESTS-RESIDENT | household | guests eq temporary_residents | bedroom:guest x 1 [P/D]; bathroom:guest x 1 [D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H26-LAUNDRY-MINIMUM | household | always | laundry_closet x 1 [R] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H27-LAUNDRY-ROOM | household | (members ge 3 or minors ge 1) | laundry x 1 [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H28-LAUNDRY-CLOSET | household | not ((members ge 3 or minors ge 1)) | laundry_closet x 1 [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H29-STORAGE | household | always | storage x 1 [P/D]; mechanical x 1 [D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H30-MUDROOM-PETS | household | pets ge 1 and vehicles ge 1 | mudroom x 1 [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H31-MUDROOM-CHILDREN | household | minors ge 2 and vehicles ge 1 | mudroom x 1 [D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H32-CLOSETS | household | always | closet x bedrooms_required [R]; closet x non_primary_bedrooms_preferred [P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H33-GARAGE | household | vehicles ge 1 | garage cars {'fact': 'vehicles', 'max': 1} [R]; garage cars {'fact': 'vehicles', 'max': 2} [P/D] | provisional | Design default; off-street parking requirement for single dwelling units to verify (SDMC Ch. 14, Art. 2, Div. 5) |
| H34-OUTDOOR-PETS | household | pets ge 1 | weight garden_access x1.2 [R/P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H35-PRIVACY-TEENS | household | teens ge 1 | weight private_depth x1.2 [R/P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| H36-SUPERVISION | household | children_0_5 ge 1 | weight kitchen_garden_view x1.3 [R/P/D] | provisional | Student-defined household model, spaceplan step 6.5a (2026-10); design hypothesis to validate with pilot pre-approved plans and local practitioners |
| C01-DINING-EXTENDED | culture | dining_capacity eq extended_family | dining_room x 1 [P/D]; dining_room area x1.3 [P/D]; matrix dining-patio D soft w2 [R/P/D] | provisional | Student-defined cultural-layer hypothesis, spaceplan step 6.5c (2026-10); tendency used as an editable starting point, not a characterization of any group; validate with pilot pre-approved plans and local practitioners |
| C02-RECEIVING-ROOM | culture | social_center eq dining_table and members ge 4 | family_room x 1 [D] | provisional | Student-defined cultural-layer hypothesis, spaceplan step 6.5c (2026-10); tendency used as an editable starting point, not a characterization of any group; validate with pilot pre-approved plans and local practitioners |
| C03-ISLAND-CENTER | culture | social_center eq kitchen_island | breakfast_nook x 1 [P/D]; dining_room area x0.9 [P/D] | provisional | Student-defined cultural-layer hypothesis, spaceplan step 6.5c (2026-10); tendency used as an editable starting point, not a characterization of any group; validate with pilot pre-approved plans and local practitioners |
| C04-VENTILATION | culture | ventilation_priority eq high | weight kitchen_ventilation x1.3 [R/P/D] | provisional | Student-defined cultural-layer hypothesis, spaceplan step 6.5c (2026-10); tendency used as an editable starting point, not a characterization of any group; validate with pilot pre-approved plans and local practitioners |
| C05-INTENSIVE-WORK-AREA | culture | cooking eq intensive and ventilation_priority eq high | kitchen area x1.1 [P/D] | provisional | Student-defined cultural-layer hypothesis, spaceplan step 6.5c (2026-10); tendency used as an editable starting point, not a characterization of any group; validate with pilot pre-approved plans and local practitioners |
| C06-SERVICE-YARD | culture | laundry_location eq service_yard | matrix kitchen-laundry D hard w1 [R/P/D]; matrix laundry-patio D soft w1.5 [R/P/D] | provisional | Student-defined cultural-layer hypothesis, spaceplan step 6.5c (2026-10); tendency used as an editable starting point, not a characterization of any group; validate with pilot pre-approved plans and local practitioners |
| C07-LAUNDRY-BEDROOMS | culture | laundry_location eq near_bedrooms | matrix kitchen-laundry I soft w0.5 [R/P/D]; matrix dining-laundry N [R/P/D]; laundry near bedroom [R/P/D] | provisional | Student-defined cultural-layer hypothesis, spaceplan step 6.5c (2026-10); tendency used as an editable starting point, not a characterization of any group; validate with pilot pre-approved plans and local practitioners |
| C08-EN-SUITE | culture | bath_per_bedroom eq en_suite_preferred | bathroom x secondary_bedrooms_preferred min=1 [D] | provisional | Student-defined cultural-layer hypothesis, spaceplan step 6.5c (2026-10); tendency used as an editable starting point, not a characterization of any group; validate with pilot pre-approved plans and local practitioners |
| C09-MUDROOM-SEQUENCE | culture | entry_sequence eq garage_mudroom_kitchen and vehicles ge 1 | mudroom x 1 [P/D]; matrix mudroom-kitchen D soft w1 [P/D]; garage adjacent mudroom [P/D]; weight entry_sequence x1.2 [R/P/D] | provisional | Student-defined cultural-layer hypothesis, spaceplan step 6.5c (2026-10); tendency used as an editable starting point, not a characterization of any group; validate with pilot pre-approved plans and local practitioners |
| C10-OUTDOOR-GATHERING | culture | outdoor_cooking eq gathering | backyard covered_terrace #1 (add) [R/P/D]; backyard outdoor_kitchen #2 (add) [R/P/D] | provisional | Student-defined cultural-layer hypothesis, spaceplan step 6.5c (2026-10); tendency used as an editable starting point, not a characterization of any group; validate with pilot pre-approved plans and local practitioners |
| C11-OUTDOOR-AMENITY | culture | outdoor_cooking eq amenity | backyard rear_deck #1 [R/P/D]; backyard bbq #3 [R/P/D] | provisional | Student-defined cultural-layer hypothesis, spaceplan step 6.5c (2026-10); tendency used as an editable starting point, not a characterization of any group; validate with pilot pre-approved plans and local practitioners |
| C12-PATIO-GATHERING | culture | patio_use eq gathering | backyard covered_terrace #1 (add) [R/P/D]; backyard pool #6 [R/P/D]; backyard rear_deck #6 [R/P/D] | provisional | Student-defined cultural-layer hypothesis, spaceplan step 6.5c (2026-10); tendency used as an editable starting point, not a characterization of any group; validate with pilot pre-approved plans and local practitioners |
| C13-PATIO-LAWN | culture | patio_use eq lawn_play | backyard green >= 50% [R/P/D]; backyard pool #2 [R/P/D]; backyard garden_beds #7 [R/P/D] | provisional | Student-defined cultural-layer hypothesis, spaceplan step 6.5c (2026-10); tendency used as an editable starting point, not a characterization of any group; validate with pilot pre-approved plans and local practitioners |

## Cultural layer (6.5c)

A profile is only a preset of explicit aspects the client sees and edits; culture rules read the aspects, never the label. Without a profile or aspects, no culture rule fires.

| Aspect | Values | Latino (tendency) | Anglo suburban (tendency) | Effect |
|---|---|---|---|---|
| kitchen_living_relation | open, separable, closed | separable | open | Kitchen typology and kitchen-living relation |
| social_center | dining_table, kitchen_island, living | dining_table | kitchen_island | Dining or breakfast nook weight; receiving room |
| ventilation_priority | normal, high | high | normal | Kitchen ventilation weight, larger work area |
| dining_capacity | household, extended_family | extended_family | household | Dining room size and relation to the patio |
| outdoor_cooking | none, amenity, gathering | gathering | amenity | Covered terrace, outdoor kitchen or barbecue priority |
| entry_sequence | front, garage_mudroom_kitchen | front | garage_mudroom_kitchen | Mudroom between garage and kitchen |
| laundry_location | service_yard, near_bedrooms | service_yard | near_bedrooms | Laundry with kitchen and service yard, or near bedrooms |
| bath_per_bedroom | shared_ok, en_suite_preferred | shared_ok | en_suite_preferred | One bath per bedroom as desirable |
| patio_use | gathering, lawn_play | gathering | lawn_play | Backyard element priorities and green reserve |

| Kitchen typology | Effects |
|---|---|
| open_island (Open kitchen with island) | kitchen area x1.1 [P/D]; matrix living-kitchen D soft w1 [R/P/D]; weight kitchen_garden_view x1.2 [R/P/D] |
| semi_open_separable (Semi-open, separable kitchen) | matrix living-kitchen I soft w1 [R/P/D]; weight kitchen_ventilation x1.2 [R/P/D] |
| closed_ventilated (Closed kitchen with cross ventilation) | matrix living-kitchen I soft w1.5 [R/P/D]; anchor kitchen_faces_rear hard [R/P/D]; weight kitchen_ventilation x1.5 [R/P/D] |
| double_kitchen (Double kitchen: clean (open) + work (closed)) | work_kitchen x 1 [P/D]; matrix kitchen-work_kitchen D hard w1 [P/D]; matrix work_kitchen-laundry D soft w1 [P/D]; matrix living-kitchen D soft w1 [R/P/D] |

Selection (first match; an explicit client choice wins):

1. kitchen_living_relation eq closed -> closed_ventilated
2. kitchen_living_relation eq open and cooking eq intensive -> double_kitchen
3. (kitchen_living_relation eq open or social_center eq kitchen_island) -> open_island
4. (kitchen_living_relation eq separable or ventilation_priority eq high) -> semi_open_separable

## Reference archetypes

| Archetype | Members (age) | Dimensions | Trajectory |
|---|---|---|---|
| Young couple | 30 (WFH), 31 | social_life=frequent, guests=frequent, cooking=daily, vehicles=2, pets=1 | child_expected in 2 y |
| Early childhood | 34, 35, 2, 4 | social_life=frequent, guests=rare, cooking=daily, vehicles=2, pets=0 | - |
| Family with teenagers | 45, 47, 14, 16 | social_life=large_gatherings, guests=rare, cooking=daily, vehicles=3, pets=1 | member_leaves in 3 y |
| Multigenerational | 40, 42, 8, 11, 74 (reduced) | social_life=large_gatherings, guests=rare, cooking=intensive, vehicles=2, pets=0 | - |
| Empty nest / retirement | 63 (anticipated), 66 (anticipated) | social_life=frequent, guests=frequent, cooking=daily, vehicles=2, pets=0 | mobility_change in 5 y |
| Remote work | 38 (WFH), 36 (WFH) | social_life=intimate, guests=rare, cooking=light, vehicles=1, pets=1 | - |
| Adults sharing | 27, 29, 31 | social_life=frequent, guests=rare, cooking=daily, vehicles=3, pets=0 | - |
