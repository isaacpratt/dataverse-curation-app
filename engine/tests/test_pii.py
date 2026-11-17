"""PII helper: piigex detectors + Canadian pack + truncation copy."""

from engine.checks._util import find_emails, find_pii, pii_result


def test_email_detected() -> None:
    found = find_pii("Contact: jane.doe@example.com for details")
    assert any(f["type"] == "intl_email" for f in found)
    assert any(f["value"] == "jane.doe@example.com" for f in found)


def test_credit_card_luhn_ok() -> None:
    found = find_pii("card 4111 1111 1111 1111")
    cards = [f for f in found if f["type"] == "intl_credit_card"]
    assert cards
    assert cards[0].get("valid", True)


def test_credit_card_luhn_fail_excluded() -> None:
    # Fails Luhn — should not appear as intl_credit_card
    found = find_pii("card 4111 1111 1111 1112")
    cards = [f for f in found if f["type"] == "intl_credit_card"]
    assert not cards


def test_canada_postal_code() -> None:
    found = find_pii("Ottawa ON K1A 0B1 and Toronto M5V3L9")
    postals = [f for f in found if f["type"] == "ca_postal_code"]
    values = {p["value"].replace(" ", "") for p in postals}
    assert "K1A0B1" in values
    assert "M5V3L9" in values


def test_canada_postal_rejects_invalid_province_letter() -> None:
    # D is not a valid Canadian forward sortation area first letter
    found = find_pii("bad D1A 0B1")
    postals = [f for f in found if f["type"] == "ca_postal_code"]
    assert not any(p["value"].upper().startswith("D") for p in postals)


def test_canada_sin_luhn_valid() -> None:
    # 046454286 is the classic valid test SIN
    found = find_pii("SIN 046 454 286")
    sins = [f for f in found if f["type"] == "ca_sin"]
    assert sins
    assert sins[0]["value"] == "046 454 286"


def test_canada_sin_luhn_invalid_excluded() -> None:
    # 123456789 fails Luhn (sum check)
    found = find_pii("SIN 123 456 789")
    sins = [f for f in found if f["type"] == "ca_sin"]
    assert not sins


def test_find_emails_backward_compat() -> None:
    assert find_emails("a@b.co") == ["a@b.co"]


def test_foreign_national_ids_disabled() -> None:
    # be_eid / es_nss style detectors are region-specific and off by policy;
    # only region="intl" piigex detectors run alongside the CA pack.
    found = find_pii("Belgian eID 74060416628 · Spanish NSS 12345678Z · US SSN 078-05-1120")
    types = {f["type"] for f in found}
    assert not any(t.startswith(("be_", "es_", "us_")) for t in types)


def test_intl_detectors_still_run() -> None:
    found = find_pii("contact jane@example.com card 4111 1111 1111 1111")
    types = {f["type"] for f in found}
    assert "intl_email" in types
    assert "intl_credit_card" in types


def test_pii_result_clean() -> None:
    r = pii_result("format.csv.pii", "a.csv", [], scope="in first 1000 rows")
    assert r.passed is True
    assert r.level == "info"
    assert r.details["count"] == 0
    assert "no PII values detected" in r.message
    assert "in first 1000 rows" in r.message


def test_pii_result_truncation_message() -> None:
    findings = [{"type": "intl_email", "value": f"user{i}@example.com"} for i in range(15)]
    r = pii_result("format.csv.pii", "a.csv", findings)
    assert r.passed is False
    assert r.details["count"] == 15
    assert r.details["samples_listed"] == 10
    assert len(r.details["samples"]) == 10
    assert "showing first 10 of 15" in r.message
    assert r.details["types"]["intl_email"] == 15


def test_pii_result_no_truncation_when_under_cap() -> None:
    findings = [{"type": "ca_sin", "value": "046 454 286"}]
    r = pii_result("format.csv.pii", "a.csv", findings)
    assert "showing first" not in r.message
