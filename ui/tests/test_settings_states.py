"""P2 named states for Settings identity + collection role (checked= branches).

Promoted from probe33/34_p2_states*.py — every row reads a named state
("Not checked yet" / "No user returned" / "Couldn't check" / "No direct
role"), never a bare dash, and checked=False never implies a failed check.
All three renderers are pure local code; the network path in
_refresh_user_info only runs when URL *and* token are set, so the
empty-token refresh below is synchronous and offline.
"""

DASH = "\u2014"


def _identity_rows(pane):
    return [
        pane._user_identifier.text(),
        pane._user_display.text(),
        pane._user_super.text(),
        pane._user_affil.text(),
        pane._user_role.text(),
    ]


def test_initial_rows_are_named(win):
    rows = _identity_rows(win._settings)
    assert all(t and t != DASH for t in rows), rows


def test_checked_but_empty_reads_no_user_returned(win):
    pane = win._settings
    pane._set_user_info(
        None, "Could not verify identity - check the URL/token (see log).", checked=True
    )
    rows = _identity_rows(pane)
    assert rows[:4] == ["No user returned"] * 4, rows


def test_unchecked_reads_not_checked_yet(win):
    pane = win._settings
    pane._set_user_info(None, "", checked=False)
    rows = _identity_rows(pane)
    assert rows[:4] == ["Not checked yet"] * 4, rows


def test_profile_payload_renders_fields(win):
    pane = win._settings
    pane._set_user_info(
        {"identifier": "curator1", "displayName": "Ada Curator", "superuser": True,
         "affiliation": "Example U"},
        "Connected.",
        checked=True,
    )
    assert pane._user_identifier.text() == "curator1"
    assert pane._user_display.text() == "Ada Curator"
    assert pane._user_super.text() == "Yes"
    assert pane._user_affil.text() == "Example U"
    assert pane._user_status.text() == "Connected."


def test_absent_profile_fields_read_not_set(win):
    pane = win._settings
    pane._set_user_info({"identifier": "curator1"}, "", checked=True)
    assert pane._user_identifier.text() == "curator1"
    assert pane._user_display.text() == "Not set"
    assert pane._user_super.text() == "No"
    assert pane._user_affil.text() == "Not set"


def test_role_checked_failure_reads_couldnt_check(win):
    pane = win._settings
    pane._set_collection_role(None, "mcmaster", checked=True)
    assert pane._user_role.text() == "Couldn't check"


def test_role_checked_empty_list_reads_no_direct_role(win):
    pane = win._settings
    pane._set_collection_role([], "mcmaster", checked=True)
    assert pane._user_role.text() == "No direct role"


def test_role_checked_without_alias_reads_not_checked(win):
    pane = win._settings
    pane._set_collection_role(None, "", checked=True)
    assert pane._user_role.text() == "Not checked yet"


def test_role_unchecked_keeps_named_state(win):
    pane = win._settings
    pane._set_collection_role(None, "mcmaster", checked=False)
    assert pane._user_role.text() == "Not checked yet"


def test_empty_token_refresh_stays_offline_and_named(win):
    pane = win._settings
    saved = pane.token_edit.text()
    pane.token_edit.clear()
    try:
        pane._refresh_user_info()  # short-circuits locally: no token
        rows = _identity_rows(pane)
        assert rows == ["Not checked yet"] * 5, rows
    finally:
        pane.token_edit.setText(saved)
