---
page_type: reference
tgdp_template: Reference     # Reference | Glossary
audience: all                # curator | developer | contributor | all
---
# Entry-correctness rules reference

`looks_correct` is a field-rule handler in the ruleset engine (`curation/review_rules.py:_looks_correct`). Any rule a curator writes for a metadata field can carry it, together with a `params` object of entry checks. The verdict flows through the completeness pipeline: the Metadata check card, the Response draft and the readiness verdict. The built-in McMaster and Minimal rulesets contain zero `looks_correct` rules.

## Entry-check parameters

Any subset can be combined; every failure names the offending field and ends with a bracketed reason that becomes part of the shown value (and of the draft letter sent to the depositor).

| Param | Semantics | Fails when | Verdict shows |
| --- | --- | --- | --- |
| `min_length` | Minimum content length in characters. Multi-entry fields (e.g. `dsDescription`) measure the concatenated text. Dotted compound paths (e.g. `author.authorAffiliation`) measure each entry separately. | Total (or entry) shorter than the minimum | `… [too short: 18 of 50 characters]` |
| `regex` + `regex_mode` | Value must match the pattern; case-sensitive unless the pattern opts out. `search` (default) finds a match anywhere; `full` anchors both ends (`fullmatch`). | No match anywhere / whole value not matched in full mode | `… [does not match '^…$']` |
| `blocklist` | Case-insensitive substring block — a rule-provided refusal list ("draft", "untitled", "lorem"). | Any blocked phrase appears in the text | `… [blocked phrase: 'draft']` |
| `not_common_placeholders` | Built-in blocklist of obvious placeholders: lorem ipsum, todo, tbd, no description, placeholder, sample text, asdf, xxx, and a couple more. English-tuned. | Any built-in phrase appears | `… [placeholder text: 'no description']` |
| `not_all_caps` | Rewrites "OBVIOUS SHOUTED TITLES". Fails only when the value has at least two letters and every cased letter is uppercase. | Value is all caps | `… [all caps]` |
| `controlled_vocabulary` | Inline list of allowed tokens. Every nonempty text leaf must equal one token (case-insensitive). Empty list = the check is off. | A leaf is not in the list | `… [not in vocabulary: 'Quantum Knitting']` |
| `date` | Every text leaf must parse as an ISO-ish date: `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, or an ISO datetime with optional `Z`/offset. Slash dates and locale dates (`13/05/2001`) are not parsed. | A leaf is not ISO-parseable | `… [date not parseable: '2026-13-45']` |
| `date_order` | Only meaningful on compound date fields (`timePeriodCovered`, `dateOfCollection`): per entry, the start-named child must not be after the end-named child; both must parse. With no complete pair anywhere, the rule fails closed (`no complete date range (N one-sided entries)` — or `no checkable value for date range` when there are no partial entries at all); alongside a complete pair, one-sided entries are ignored. | Start after end, an unparseable bound, or no complete pair | `2010 → 2005 [date range reversed: 2010 is after 2005]` |
| `url` | `http(s)` scheme and a dotted hostname ("example.com") — scheme-only checks by design; a bare `alt.org` or `ftp://x.com` fails. | Not http(s), or no dotted host | `… [not a plausible URL: 'not a url']` |

## Failure semantics

| Case | Result |
| --- | --- |
| Empty value | Incomplete ("—"), the same verdict a nonempty check gives when the entry fails |
| Rule with no effective checks | Fails closed with `[no entry checks configured]` — never a silent pass |
| Invalid regex | Fails the rule with `rule error: invalid regex '<pattern>'` instead of raising |
| Unparseable `min_length` or unknown `regex_mode` | Fails with a bracketed rule error instead of being clamped |
| Exception inside a rule | Surfaces as an incomplete row with `[rule error: …]` rather than disappearing from the completeness list |
| Dotted compound paths (e.g. `author.authorIdentifier`) | Each leaf is checked; fails incomplete when any leaf is empty |
| External services | None — all checks are local and deterministic; nothing calls doi.org, Crossref, ORCID, or the Dataverse any differently than nonempty |
| Verdict form | Ordinary completeness results: status `complete`/`incomplete`, level `required`/`optional` from the rule, stable `rule_id` like `field:citation.dsDescription:looks_correct`. Display-only `status="skipped"` rows synthesized by `include_unchecked=True` never reach the verdict or the draft |

## Rule shape

Configuration lives in `requirements_profiles.json` (v2, beside `config.json`: the working directory in a dev run, `%APPDATA%\Dataverse Docent\` when installed, the portable root otherwise). Each field rule carries `block`, `field`, `level` (`required`/`optional`/`unchecked`), `requirement`, `handler`, optional `params`, and a `response_template`.

```json
{ "block": "citation", "field": "dsDescription", "label": "Description",
  "level": "optional", "requirement": "Description is at least 50 characters and not placeholder text",
  "handler": "looks_correct",
  "params": { "min_length": 50, "not_common_placeholders": true },
  "response_template": "Please expand the description — it must be at least 50 characters and not placeholder text. (Current value: {value})" }
```

`_looks_correct` normalizes params tolerantly: numbers as strings, token lists as comma/newline-separated text. The table above groups ten parameter keys into nine checks (`regex` and `regex_mode` are one check). Review configuration exposes them as live controls; every keystroke round-trips into the rule JSON. Removing every knob deletes `params`, so an emptied panel fails closed rather than passing silently.

## Downstream effects

| Consumer | Behaviour |
| --- | --- |
| Metadata check card | One row per rule (icon, bold name, one-line verdict sentence, badge); required versus optional is explained in the row tooltip, and a required incomplete rule counts as a finding for the verdict |
| Response draft | One section per incomplete finding; the template's `{value}` is substituted with the verdict text, bracketed reason included. `wontfix`-dispositioned findings ship excluded until re-included |
| Readiness verdict (`engine/verdict.py`) | Unresolved required-incomplete rules count as reason `required-missing` at level `revisions` (needs changes) — never "blocked" (reserved for error-level file findings and a pending sensitivity review). Dispositions (`acknowledged`/`wontfix`) discount a finding |

## Scope limits

| Limit | Statement |
| --- | --- |
| Plausibility, not truth | Catches "no description yet", "ALL CAPS", reversed date ranges — never whether the content is about the data |
| `min_length` | Counts codepoints including spaces; cannot distinguish a long word salad from a real summary |
| `controlled_vocabulary` | Fails every depositor not on the list; the list is a maintained artifact |
| `date` | ISO-only by design; deposits in other shapes (DD/MM/YYYY, month names) fail the rule |
| `regex` | An invalid pattern fails loudly; a careless-but-valid pattern can flag everything |
| ORCID | Author identifiers keep their dedicated handler; not duplicated as a regex rule |
| Not covered | Live DOI/ISNI resolution, controlled file-content checks for metadata, and negation ("must NOT contain X" as a first-class rule) |

## See also

- [Checks reference](checks.md)
- [Configuration reference](configuration.md)
- [Glossary](glossary.md)
