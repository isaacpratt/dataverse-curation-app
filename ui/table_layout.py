"""Persisted column layouts: one owner for save, restore and reset.

The contract
------------
* **Only user gestures are persisted.** A programmatic resize (a content
  fit, a viewport refit, a state restore) must never overwrite the
  layout the user chose. Programmatic changes run inside
  ``layout.suppressed()`` — the controller then ignores the signals they
  emit. Four copies of "wire ``sectionResized`` straight to a save" is
  how the file manifest lost the user's widths on every refresh.

* **One controller per header.** It owns the construction snapshot, the
  restore, the persistence and the reset, so no view repeats that wiring.

* **Restores are validated.** A layout saved for a different column count
  (an older table shape) is ignored instead of squeezing the columns
  (see ``curation.storage.table_layout_entry_valid``).

Usage::

    self._layout = TableLayout(workspace, "dataset_files", tree.header())
    self._layout.restore()

    # a programmatic change: not the user's doing, so not persisted
    with self._layout.suppressed():
        tree.fit_columns_to_contents()

    # a user gesture: persisted
    self._layout.save()
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import Qt

from curation.storage import (
    apply_table_view,
    clear_table_state,
    restore_table_state,
    save_table_state,
    snapshot_table_view,
)

__all__ = ["TableLayout"]


def _qt_sort_order(raw: int) -> Qt.SortOrder:
    """Convert the persisted sort direction (an int) to the enum Qt wants.

    The curation core stores plain ints and knows nothing about Qt; the
    view layer owns this conversion (dv-hcg.24).
    """
    try:
        return Qt.SortOrder(int(raw))
    except Exception:
        return Qt.SortOrder.AscendingOrder


class TableLayout:
    """Owns one header's persisted layout (widths, order, visibility, sort).

    The controller listens to the header's own signals, so it sees every
    change — user or programmatic. Programmatic changes are told apart by
    the ``suppressed()`` scope, not by guessing from the signal.
    """

    def __init__(
        self,
        workspace: Path | str,
        key: str,
        header,
        *,
        view=None,
        persist_sort: bool = True,
        autosave: bool = True,
    ) -> None:
        self.workspace = Path(workspace)
        self.key = key
        self.header = header
        self.view = view
        self.autosave = autosave
        self._depth = 0
        # The construction view: what "reset" restores to.
        self.snapshot = snapshot_table_view(header)
        # Keep the controller alive as long as the header: a view that
        # forgets to store it would otherwise lose the connection -- and
        # with it the persistence.
        try:
            header.setProperty("tableLayout", self)
        except Exception:
            pass
        # The view's own user-gesture signal is the best source (AppTable
        # and AppTree know a drag from a programmatic resize). Plain
        # headers have no such signal, so the header's own signals are
        # used instead -- and the suppressed() scope tells the two apart.
        if view is not None and hasattr(view, "user_layout_changed"):
            try:
                view.user_layout_changed.connect(self._on_layout_changed)
            except Exception:
                pass
        else:
            try:
                header.sectionResized.connect(self._on_layout_changed)
                header.sectionMoved.connect(self._on_layout_changed)
            except Exception:
                pass
        if persist_sort:
            try:
                header.sortIndicatorChanged.connect(self._on_layout_changed)
            except Exception:
                pass

    # -- user gestures -----------------------------------------------------
    def _on_layout_changed(self, *_args) -> None:
        """Persist the layout: a column was resized, moved or re-sorted."""
        if self._depth or not self.autosave:
            return
        self.save()

    def save(self) -> None:
        """Persist the current layout (best-effort, never raises)."""
        try:
            save_table_state(self.workspace, self.key, self.header)
        except Exception:
            pass

    # -- programmatic changes ---------------------------------------------
    @contextmanager
    def suppressed(self):
        """Scope for programmatic changes: they are not persisted.

        Use it around content fits, viewport refits and any other resize
        the app performs on its own. The header's signals still fire, but
        the controller ignores them until the scope ends.
        """
        self._depth += 1
        try:
            yield self
        finally:
            self._depth -= 1

    # -- lifecycle ---------------------------------------------------------
    def restore(self) -> bool:
        """Apply the saved layout, if one matches this table's shape.

        Returns True when a saved layout was applied — the caller then
        skips its content auto-fit so the user's layout wins.
        """
        with self.suppressed():
            try:
                return bool(
                    restore_table_state(self.workspace, self.key, self.header, _qt_sort_order)
                )
            except Exception:
                return False

    def reset(self) -> bool:
        """Drop the saved layout and re-apply the construction view.

        Returns True when the construction view was applied. The saved
        entry is cleared, so the reset survives a restart; the next user
        gesture persists the new layout again.
        """
        with self.suppressed():
            try:
                clear_table_state(self.workspace, self.key)
            except Exception:
                pass
            snap = self.snapshot
            if not isinstance(snap, dict):
                return False
            try:
                apply_table_view(self.header, snap, _qt_sort_order)
            except Exception:
                return False
        return True
