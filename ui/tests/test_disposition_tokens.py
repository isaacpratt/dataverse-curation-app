"""Disposition tokens: the kit and the storage layer must agree (dv-32x).

``ui/widgets.py`` declares the tuple again on purpose (the kit stays
free of the storage layer), so the agreement is enforced by this test
instead of by an import — the engine test suite deliberately carries
no Qt imports.
"""

from curation.storage import DISPOSITION_TOKENS as STORAGE_TOKENS
from ui.widgets import DISPOSITION_TOKENS as KIT_TOKENS


def test_kit_and_storage_share_the_same_disposition_tokens():
    assert KIT_TOKENS == STORAGE_TOKENS
