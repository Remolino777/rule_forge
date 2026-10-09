"""Bridge module (refactor tanda 2): the code moved to `spaceplan.modules.household.main.run_program`.

Kept so existing imports keep working; removed in tanda 4. Refactor tanda 3: the names imported below from
spaceplan.pipeline compose several modules and moved to the pipeline (same signature and output).
"""

from spaceplan.modules.household.main.run_program import *
from spaceplan.pipeline.main.run_catalog import (
    parameter_table,  # noqa: F401  (composed by the pipeline, tanda 3)
)
