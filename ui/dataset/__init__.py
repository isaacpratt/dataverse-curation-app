"""The dataset detail page, split into focused sections.

`DatasetDetailView` is the facade: it owns the layout and assembles
the sections that own the behaviour (metadata, files, checks,
versions, the dataset log, the response draft, the actions and the
header).
"""

from ui.dataset.page import DatasetDetailView

__all__ = ["DatasetDetailView"]
