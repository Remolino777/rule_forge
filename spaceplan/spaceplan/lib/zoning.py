"""Bridge module (refactor tanda 2): the code moved to `spaceplan.modules.zoning.lib.zoning`.

Kept so existing imports keep working; removed in tanda 4.
"""

from spaceplan.modules.zoning.lib.zoning import *
from spaceplan.modules.zoning.lib.zoning import (  # noqa: F401  (names the tests import beyond `import *`)
    BandGeometry,
    _column_ok,
    _compositions,
    _set_partitions,
    first_violation,
    front_precheck,
    merge_options,
)
