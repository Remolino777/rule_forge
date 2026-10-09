"""Bridge module (refactor tanda 2): the code moved to `spaceplan.modules.areas.main.run_area_matrix`.

Kept so existing imports keep working; removed in tanda 4. Refactor tanda 3: the names imported below from
spaceplan.pipeline compose several modules and moved to the pipeline (same signature and output).
"""

from spaceplan.modules.areas.main.run_area_matrix import *
from spaceplan.pipeline.main.run_area_analysis import (
    run_area_matrix,  # noqa: F401  (composed by the pipeline, tanda 3)
)
