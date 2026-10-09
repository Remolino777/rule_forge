"""Bridge module (refactor tanda 2): the code moved to `spaceplan.modules.household.main.run_household`.

Kept so existing imports keep working; removed in tanda 4. Refactor tanda 3: the names imported below from
spaceplan.pipeline compose several modules and moved to the pipeline (same signature and output).
"""

from spaceplan.modules.household.main.run_household import *
from spaceplan.pipeline.main.run_household_report import (
    derive_household,  # noqa: F401  (composed by the pipeline, tanda 3)
)
