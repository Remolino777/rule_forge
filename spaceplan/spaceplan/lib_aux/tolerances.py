"""Numeric tolerances shared by the helpers. Units: feet and square feet."""

ARC_CHORD_TOL_FT = 0.05          # max sagitta between a discretized arc and the true arc
BUFFER_QUAD_SEGS = 32            # segments per quarter circle in round buffers
COVER_TOL_FT = 1e-6              # slack used when testing rectangle containment
RECT_GRID_STEP_FT = 0.25         # grid step for the inscribed-rectangle search
RECT_REFINE_ROUNDS = 3           # continuous refinement rounds after the grid search
BISECTION_ITERS = 40             # bisection iterations (40 -> ~1e-12 of the search span)
AREA_TIE_TOL_SQFT = 1.0          # two areas closer than this are treated as a tie
SENSITIVITY_AREA_TOL_SQFT = 0.01 # envelope areas closer than this are the same result
SEMANTICS_AREA_TOL_SQFT = 0.5    # tolerance when comparing setback distance semantics
LENGTH_EQ_TOL_FT = 1e-9          # strict threshold comparisons in rule predicates
REAR_PARALLEL_TOL_DEG = 45.0     # max deviation from the front direction for a rear edge
REAR_CLEAR_TOL_DEG = 10.0        # rear inference is "clear" below this deviation
ROUND_DECIMALS = 4               # decimals kept in the serialized package
