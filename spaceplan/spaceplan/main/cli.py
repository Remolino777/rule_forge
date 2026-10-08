"""Bridge module (refactor tanda 2): the code moved to `spaceplan.pipeline.main.cli`.

Kept so existing imports keep working; removed in tanda 4.
"""

from spaceplan.pipeline.main.cli import *

if __name__ == "__main__":
    main()
