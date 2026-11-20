# Entry-correctness rules (looks_correct)

How the app checks whether a depositor's metadata entry is plausible, not merely present — what checks exist, how they are wired in, and how to enroll them safely.

## The one-line summary

handler looks_correct is a field-rule handler in the ruleset engine. Any rule a curator writes for a metadata field can carry it, together with a small params object of entry checks; the verdict flows through the exact same completeness pipeline as everything else — the Metadata check card, the Response draft, and the readiness verdict. Nothing is enrolled today: the built-in McMaster and Minimal rulesets contain zero looks_correct rules, so enabling it is a deliberate, per-instance, reversible decision.

## What it checks

Each sub-shape is a param on the rule. Any subset can be combined; every failure names the offending field and ends with a bracketed reason that becomes part of the shown value (and of the draft letter sent to the depositor).

| Param | Semantics | Fails when | Verdict shows |
| --- | --- | --- | --- |
| min_length | Minimum content length in characters. Multi-entry fields (e.g. dsDescription) measure the concatenated text — "Description is at least 50 characters" is one knob. Dotted compound paths (e.g. author.authorAffiliation) measure each entry separately — a one-character affiliation fails on its own. | Total (or entry) shorter than the minimum | … [too short: 18 of 50 characters] |

| regexregex_mode | Value must match the pattern; case-sensitive unless the pattern opts out. search (default) finds a match anywhere; full anchors both ends (fullmatch). | No match anywhere / whole value not matched in full mode | … [does not match '^…$'] |
| blocklist | Case-insensitive substring block — a rule-provided refusal list ("draft", "untitled", "lorem"). | Any blocked phrase appears in the text | … [blocked phrase: 'draft'] |
| not_common_placeholders | Built-in blocklist of obvious placeholders: lorem ipsum, todo, tbd, no description, placeholder, sample text, asdf, xxx, and a couple more. English-tuned; use your own blocklist to extend it. | Any built-in phrase appears | … [placeholder text: 'no description'] |
| not_all_caps | Rewrites "OBVIOUS SHOUTED TITLES". Fails only when the value has at least two letters and every cased letter is uppercase. | Value is all caps | … [all caps] |

| controlled_vocabularycontrolled_vocabulary | Inline list of allowed tokens. Every nonempty text leaf must equal one token (case-insensitive). Empty list = the check is off. A token list you invent that the depositors never use will fail 100% of deposits — see the enrollment advice below. | A leaf is not in the list | … [not in vocabulary: 'Quantum Knitting'] |
| date | Every text leaf must parse as an ISO-ish date: YYYY, YYYY-MM, YYYY-MM-DD, or an ISO datetime with optional Z/offset. Slash dates and locale dates (13/05/2001) are not parsed and will fail — deliberately: Borealis emits ISO. | A leaf is not ISO-parseable | … [date not parseable: '2026-13-45'] |
| date_order | Only meaningful on compound date fields (timePeriodCovered, dateOfCollection): per entry, the start-named child must not be after the end-named child; both must parse. One-sided entries are never silently accepted: with no complete pair anywhere, the rule fails closed ([no complete date range: n one-sided entries]); alongside a complete pair they are ignored | Start after end, an unparseable bound, or no complete pair | 2010 → 2005 [date range reversed: 2010 is after 2005] |
| url | http(s) scheme and a dotted hostname ("example.com") — scheme-only checks by design; a bare alt.org or ftp://x.com fails. | Not http(s), or no dotted host | … [not a plausible URL: 'not a url'] |

### Failure semantics you can rely on

- Empty value → incomplete ("—"), exactly like a nonempty rule.
- A rule with no effective checks fails closed with [no entry checks configured] — it can never be a silent pass. (Same spirit: an invalid regex fails the rule with [rule error: invalid regex] instead of raising; an unparseable min_length or unknown regex_mode fails with a bracketed rule error instead of being clamped.)
- A failing handler emits a finding, never nothing. An exception inside a rule surfaces as an incomplete row with [rule error: …] rather than disappearing from the completeness list.
- Dotted compound paths (author.authorIdentifier) check each leaf and fail incomplete when any leaf is empty — matching the default dotted-nonempty behavior.
- No external services, ever. Everything above is a local, deterministic text check. Nothing leaves the machine; nothing calls doi.org, Crossref, ORCID, or the Dataverse any differently than nonempty does.
- Verdicts are ordinary completeness results — they flow through evaluate_ruleset unchanged: status complete/incomplete, level required/optional from the rule, and a stable rule_id like field:citation.dsDescription:looks_correct. The display-only status="skipped" rows synthesized by include_unchecked=True never reach the verdict or the draft.

## How it is wired in today
The configuration page writes the same rule JSON the engine reads (dashed line). There is no second code path: enabling a rule is editing data, not installing a check.

### The path in five steps

1. Ruleset — requirements_profiles.json (v2, beside config.json: the working directory in a dev run, %APPDATA%\Dataverse Docent\ when installed, the portable root otherwise) holds field_rules per ruleset; each rule carries block, field, level (required/optional/unchecked), requirement, handler, optional params, and a response_template (the depositor letter).
1. Engine — review_rules.evaluate_ruleset iterates the rules, dispatches on handler; _looks_correct normalizes params tolerantly (numbers as strings, token lists as comma/newline-separated text), runs the checks, and returns (ok, value-with-bracketed-reason).
1. Metadata check — metadata_check.check_with_ruleset returns the results; the Metadata check card renders one row per rule (icon, bold name, one-line verdict sentence, badge); a required incomplete rule shows a left bar and counts as a finding for the verdict.
1. Response — response_draft.collect_metadata_sections emits one section per incomplete finding; the template's {value} is substituted with the same verdict text, bracketed reason included. wontfix-dispositioned findings ship excluded from the letter until re-included.
1. Readiness verdict — engine/verdict.py counts unresolved required-incomplete rules as reason required-missing at level revisions (needs changes) — never "blocked" (blocked is reserved for error-level file findings and a pending sensitivity review). Dispositions (acknowledged/wontfix) discount a finding.

### Configuring it without JSON

In Review configuration every field rule in the table carries a level combo (Required / Optional / Not checked). Selecting one shows a Check picker in the response panel: Must be non-empty (the historical test) or Looks plausibly correct. Picking the latter seeds not_common_placeholders: true and reveals the Entry checks panel — the nine params above as live controls (length, pattern, blocked phrases, allowed values, the five flags). Every keystroke round-trips into the rule JSON; Save writes the file instance-wide; Revert discards; rulesets apply per Dataverse (* = all). Removing every knob deletes params — deliberately, so an emptied panel fails closed ([no entry checks configured]) rather than passing silently.

## What is enrolled right now

Nothing. The built-in mcmaster-default and minimal rulesets contain zero looks_correct rules; existing installs behave exactly as before. The checks ship as an engine capability and a UI affordance, and become real the moment a ruleset opts in — by a curator editing their instance's ruleset (Review configuration or the JSON file). There is no telemetry and no central flag; each Dataverse instance decides for itself.

## Limits, stated plainly

- Plausibility, not truth. These checks catch "no description yet", "ALL CAPS", reversed date ranges — never the content being about the data. A convincing wrong answer passes.
- Counting characters is crude. min_length counts codepoints including spaces; it cannot tell a 60-character word salad from a real summary. Pair it with the placeholder list, not as a sole gate.
- Vocabulary is a maintained artifact. controlled_vocabulary fails every depositor not on your list. Enroll it only with a list your discipline actually teaches, and expect to revise it termly.
- Dates are ISO-only by design. Deposits in other shapes (DD/MM/YYYY, month names) fail the date rule. That is a curation statement, not a culture statement — text this strict will mis-flag genuinely multilingual deposits.
- Regex is yours to get wrong. An invalid pattern fails the rule loudly, never the deposit silently; but a careless-but-valid pattern (e.g. ^10) flags everything. Test inside Review configuration's panel against real deposits before promoting.
- ORCID stays special. Author identifiers keep their dedicated handler; do not duplicate it as a regex rule.
- Not covered yet: live DOI/ISNI resolution, controlled file-content checks for metadata, and negation ("must NOT contain X" as a first-class rule) — each would be a new handler, not a new param.

## Enrolling it: a phased recommendation

### Phase 0 — measure before you enable 1 hour

Do not enable anything in production yet. Take the last ten deposits your team curated. For each, imagine dsDescription with min_length: 50 + not_common_placeholders: true, and title with not_all_caps: true + not_common_placeholders: true. Would any of the ten have failed? That is your noise rate. If it is more than one in ten, fix the placeholder list before enrolling anything.

### Phase 1 — pilot as Optional 2–4 weeks

Create a copy of the McMaster ruleset for one Dataverse (or one curator cohort) and enable both rules at Optional. Watch three things, for a few weeks:

- how often the flag fires (spot-check via the Log page or the response draft — every finding appears there),
- how often it is right (false positives erode trust faster than misses),
- how the depositors respond (do the letters produce fixed metadata?).

### Phase 2 — promote to Required after evidence

When the false-positive rate is unremarkable (subjective, but under ~1 in 20 flagged deposits), promote dsDescription and title to Required on that ruleset. Keep everything else Optional indefinitely. Add timePeriodCovered: date_order as Optional first — reversed ranges are a high-signal, low-noise find for longitudinal data.

### What to never enroll, or enroll last

- Controlled vocabulary for subject/topic until your group has actually agreed on and published the list, and deposits consistently source it from a dropdown — this is the one check that can fail 100% of deposits.
- DOI regex as a gate for optional rules until you are sure deposits reliably carry a DOI; as a required check it would flag entire valid deposit classes.
- Blocklist words common in your discipline ("draft" is a substring of "draft legislation"). Anchor with spaces or use a stricter pattern.

### A starter you can paste

Drop this into your ruleset's field_rules (JSON shown; the Review configuration panel writes exactly this):

```
{ "block": "citation", "field": "dsDescription", "label": "Description",
"level": "optional", "requirement": "Description is at least 50 characters and not placeholder text",
"handler": "looks_correct",
"params": { "min_length": 50, "not_common_placeholders": true },
"response_template": "Please expand the description — it must be at least 50 characters and not placeholder text. (Current value: {value})" },
{ "block": "citation", "field": "title", "label": "Title",
"level": "optional",
"requirement": "Title is real text: not all caps, not a placeholder",
"handler": "looks_correct",
"params": { "not_all_caps": true, "not_common_placeholders": true },
"response_template": "Please give the dataset a real title — not all caps and not a placeholder. (Current value: {value})" },
{ "block": "citation", "field": "timePeriodCovered", "label": "Time Period",
"level": "optional",
"requirement": "The start date must not be after the end date",
"handler": "looks_correct",
"params": { "date_order": true },
"response_template": "The Time Period looks reversed. (Current value: {value})" }
```

Roll back in seconds. Review configuration → revert the ruleset, or delete the params (the rule silently stops checking entry plausibility and returns to presence-only — nonempty), or set the level back to Not checked to drop the rule entirely. Nothing is migrated, nothing is locked in.

## How to know it is working

- Field-found rate — incomplete rows attributable to looks_correct per week (the Response draft header shows the count); expect it to start above zero and settle once deposits learn.
- Fix rate — of letters that mention an entry-correctness finding, fraction where the deposits return a conforming value. Below ~half, your wording is wrong, not the depositors.
- False-positive anecdotes — one vocal curator noticing "a good deposit flagged" outweighs a thousand quiet passes; keep a note.
