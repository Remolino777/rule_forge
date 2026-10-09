"""Bridge module (refactor tanda 2): the code moved to `spaceplan.modules.profiles.main.run_profiles`.

Kept so existing imports keep working; removed in tanda 4. Refactor tanda 3: the names imported below from
spaceplan.pipeline compose several modules and moved to the pipeline (same signature and output).
"""

from spaceplan.modules.profiles.main.run_profiles import *
from spaceplan.pipeline.main.run_portfolio import (  # noqa: F401  (composed by the pipeline, tanda 3)
    run_profiles,
    run_profiles_file,
)
