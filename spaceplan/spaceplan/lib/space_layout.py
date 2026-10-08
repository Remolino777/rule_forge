"""Bridge module (refactor tanda 2): the code moved to `spaceplan.modules.zoning.lib.space_layout`.

Kept so existing imports keep working; removed in tanda 4.
"""

from spaceplan.modules.zoning.lib.space_layout import *
from spaceplan.modules.zoning.lib.space_layout import (  # noqa: F401  (names the tests import beyond `import *`)
    fit_lengths,
)
