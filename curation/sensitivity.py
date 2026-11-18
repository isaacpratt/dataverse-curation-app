"""Structured sensitivity & ethics review (dv-3c2).

A short per-dataset questionnaire records the human judgments no regex
can make — the automated PII/secret scans catch patterns; a curator
decides what they mean. Answers persist per dataset in state.db and,
when the active ruleset carries ``"requires_sensitivity": true``, an
incomplete review blocks committing an Approve decision.

Pure module: no Qt, no I/O. storage.py owns persistence; the Response
page renders the questions.
"""

from __future__ import annotations

from typing import Any

# Answer tokens (storage-stable).
UNANSWERED = ""
YES = "yes"
NO = "no"

ANSWER_TOKENS = (UNANSWERED, YES, NO)

# The questionnaire. Prompts/help are curator-facing copy; this module is
# outside ui/ so the string-catalogue guard does not scan it (same as
# response_draft.py). Each question is a judgment call — suggestions only
# prefill what the machine can actually know.
QUESTIONS: tuple[dict[str, str], ...] = (
    {
        "id": "human-subjects",
        "prompt": "Do the data contain information collected from human subjects?",
        "help": "Trial data, survey responses, interview transcripts, "
        "health records — anything about identifiable people.",
        "type": "yes-no",
    },
    {
        "id": "consent-irb",
        "prompt": "Is consent / ethics approval documentation referenced?",
        "help": "A dataset description, README, or terms statement covering "
        "consent and IRB/REB approval for the human-subjects data.",
        "type": "yes-no",
    },
    {
        "id": "identifiers",
        "prompt": "Any direct-identifier or small-cell risk beyond the PII scan?",
        "help": "Judgment beyond the automated scan: rare combinations, "
        "small populations, re-identification risk.",
        "type": "yes-no",
    },
    {
        "id": "indigenous-care",
        "prompt": "Do the data involve Indigenous communities (CARE considerations)?",
        "help": "CARE principles: collective benefit, authority to control, "
        "responsibility, ethics — including data governance rights.",
        "type": "yes-no",
    },
    {
        "id": "restricted-terms",
        "prompt": "Are restricted files covered by terms of access?",
        "help": "Every restricted file should sit under the dataset's terms "
        "of access (the automated access check lists restricted files).",
        "type": "yes-no",
    },
)

QUESTION_IDS = tuple(q["id"] for q in QUESTIONS)


def is_complete(answers: dict[str, str] | None) -> bool:
    """Return True when every question carries an explicit yes/no answer."""
    if not isinstance(answers, dict):
        return False
    return all(str(answers.get(qid) or "") in (YES, NO) for qid in QUESTION_IDS)


def answered_count(answers: dict[str, str] | None) -> int:
    """How many questions carry an explicit answer (for the log line)."""
    if not isinstance(answers, dict):
        return 0
    return sum(1 for qid in QUESTION_IDS if str(answers.get(qid) or "") in (YES, NO))


def _pii_findings(report: Any) -> list[Any]:
    """Failed PII-flavored check results from a report (never raises)."""
    out: list[Any] = []
    try:
        entries = list(getattr(report, "dataset_checks", None) or []) + [
            c
            for f in list(getattr(report, "files", None) or [])
            for c in list(getattr(f, "checks", None) or [])
        ]
        for c in entries:
            cid = str(getattr(c, "check_id", "") or "")
            if "pii" in cid.lower() and not getattr(c, "passed", True):
                out.append(c)
    except Exception:
        return []
    return out


def _restricted_paths(inventory: list[dict[str, Any]] | None) -> list[str]:
    out: list[str] = []
    try:
        for entry in inventory or []:
            if isinstance(entry, dict) and entry.get("restricted"):
                out.append(str(entry.get("path") or ""))
    except Exception:
        return []
    return out


def suggested_answers(
    report: Any = None, inventory: list[dict[str, Any]] | None = None
) -> dict[str, str | None]:
    """Machine-suggested answers, keyed by question id (None = human call).

    Only what the data can support is suggested, and only when the data is
    actually known: a None report means the PII scan has not run, so the
    direct-identifier question stays a human call; a None inventory means
    the access picture is unknown. The genuinely human questions (human
    subjects, consent, CARE) always stay unanswered.
    """
    pii_known = report is not None
    restricted_known = isinstance(inventory, list)
    pii = _pii_findings(report) if pii_known else []
    restricted = _restricted_paths(inventory) if restricted_known else []
    return {
        "human-subjects": None,
        "consent-irb": None,
        "identifiers": (NO if not pii else None) if pii_known else None,
        "indigenous-care": None,
        "restricted-terms": (YES if not restricted else None) if restricted_known else None,
    }


def ruleset_requires(ruleset: dict[str, Any] | None) -> bool:
    """Whether a ruleset flags its collections as requiring this review."""
    try:
        return bool((ruleset or {}).get("requires_sensitivity") is True)
    except Exception:
        return False
