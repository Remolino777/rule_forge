"""Closed vocabularies shared by the brief, the package and the code.

The JSON schemas repeat these values; tests/test_schemas.py checks that both stay in sync.
"""

from enum import StrEnum

BRIEF_SCHEMA_VERSION = "0.5"  # 0.3 household block; 0.4 optional relative budget; 0.5 flag lot, view side
PACKAGE_SCHEMA_VERSION = "0.9"  # 0.2 review; 0.3 site; 0.4 zoning; 0.5 dwellings/backyard; 0.6 spaces + circulation;
#                                0.7 strategy B (stepped / polygonal), shoulders, wedges, multivariable corrections;
#                                0.8 household block (step 6.5a); 0.9 relative cost index (6.5b)
DEFAULT_FLOOR_TO_FLOOR_FT = 10.0  # design assumption, overridable in brief.massing_assumptions
DEFAULT_GROSS_FACTOR = 1.15       # walls + circulation over net program, overridable in the brief


class Scale(StrEnum):
    LARGE = "large"
    NORMAL = "normal"
    INTERMEDIATE = "intermediate"
    SUPPORT = "support"
    INTERMEDIATE_EXTERIOR = "intermediate_exterior"
    LARGE_EXTERIOR = "large_exterior"


class NodeKind(StrEnum):
    ZONE = "zone"
    SITE_ZONE = "site_zone"
    CONTEXT = "context"
    BOUNDARY = "boundary"
    SPACE = "space"


class Zone(StrEnum):
    SOCIAL = "social"
    PRIVATE = "private"
    KITCHEN = "kitchen"
    SERVICE = "service"
    CIRCULATION = "circulation"
    GARAGE = "garage"


class SiteZone(StrEnum):
    GARDEN = "garden"
    FRONT_GREEN = "front_green"
    WALKWAY = "walkway"
    ENTRY_DECK = "entry_deck"
    DRIVEWAY = "driveway"
    SIDE_YARD = "side_yard"


class RelationType(StrEnum):
    MANDATORY = "mandatory"
    ALTERNATIVE = "alternative"
    DESIRED = "desired"
    FORBIDDEN = "forbidden"
    VISUAL = "visual"
    CONTEXT = "context"
    VERTICAL = "vertical"


class BoundaryClass(StrEnum):
    FRONT = "front"
    SIDE = "side"
    STREET_SIDE = "street_side"
    REAR = "rear"


class StreetType(StrEnum):
    LOCAL = "local"
    CUL_DE_SAC = "cul_de_sac"
    COLLECTOR = "collector"


class StreetRole(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class WidthMethod(StrEnum):
    MEAN_WIDTH = "mean_width"
    FRONTAGE = "frontage"
    AT_FRONT_SETBACK = "at_front_setback"


class DepthMethod(StrEnum):
    FRONT_REAR_MIDPOINTS = "front_rear_midpoints"
    MAX_EXTENT = "max_extent"


class Constraint(StrEnum):
    FAR = "far"
    ENVELOPE = "envelope"
    OCCUPANCY_HILLSIDE = "occupancy_hillside"
    GARDEN_PREFERENCE = "garden_preference"
    REALIZATION = "realization"


class Strategy(StrEnum):
    A_INSCRIBED_RECTANGLE = "A_inscribed_rectangle"
    B_STEPPED_FOOTPRINT = "B_stepped_footprint"        # one rectangle per band, each as wide as its slab allows
    B_POLYGONAL_FOOTPRINT = "B_polygonal_footprint"    # bands follow the oblique lot lines (polygonal edge cells)


class FeasibilityLevel(StrEnum):
    NORMATIVE = "normative"
    NORMATIVE_WITH_PREFERENCES = "normative_with_preferences"
    STRATEGY_A_WITH_PREFERENCES = "strategy_A_with_preferences"


# Household model (step 6.5a)
HOUSEHOLD_TIERS = ("required", "preferred", "desirable")
HOUSEHOLD_DIMENSIONS = ("social_life", "guests", "cooking", "vehicles", "pets", "shared_rooms_ok", "cultural_profile")
HOUSEHOLD_FACTS = (
    "members", "adults", "seniors", "children_0_5", "children_6_12", "teens", "minors", "couples",
    "unpartnered_adults", "wfh_count", "bedrooms_required", "bedrooms_preferred", "primary_rooms",
    "non_primary_bedrooms_required", "non_primary_bedrooms_preferred", "secondary_bedrooms_required",
    "secondary_bedrooms_preferred", "accessible_rooms_reduced", "accessible_rooms_any", "primary_accessible",
    *HOUSEHOLD_DIMENSIONS,
)
# Cultural layer (step 6.5c): explicit, client-editable aspects; a profile is only a preset of them.
CULTURE_ASPECTS = (
    "kitchen_living_relation", "social_center", "ventilation_priority", "dining_capacity", "outdoor_cooking",
    "entry_sequence", "laundry_location", "bath_per_bedroom", "patio_use",
)
UNSPECIFIED = "unspecified"
CULTURE_FACTS = ("cultural_profile", "kitchen_typology", *CULTURE_ASPECTS)  # never read by household-layer rules
