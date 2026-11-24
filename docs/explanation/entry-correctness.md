---
page_type: explanation
tgdp_template: Concept       # Concept | Explanation
audience: developer          # curator | developer | contributor | all
---
# Why entry-correctness rules exist

Presence checks answer "did the depositor fill this field?". They cannot answer "does the value look like a real description, a real title, a plausible date?". The `looks_correct` rule handler closes that gap by checking the *text* of a metadata entry while remaining an ordinary field rule in the completeness engine. This page explains why it is shaped that way, how its failures are handled, and what enrolling it responsibly looks like. The parameter-by-parameter semantics and the starter JSON live in the [entry checks reference](../reference/entry-checks.md).

## Why it is a handler, not a second pipeline

`looks_correct` is dispatched by `review_rules.evaluate_ruleset` like any other field-rule handler. A curator writes a rule in the ruleset, gives it `handler: "looks_correct"` and a small `params` object, and the verdict travels through the same completeness path as a nonempty check: the Metadata check card, the depositor response draft and the readiness verdict. The rule ID is stable — `field:citation.dsDescription:looks_correct` — so a disposition attached to a finding survives a re-run.

That decision has a large payoff and one constraint. There is no second code path to maintain, no parallel display model and no special case in the letter generator; enabling a check is editing data, not installing code. The constraint is that plausibility must be expressed as a completeness result — complete or incomplete, at a required or optional level — because that is all the pipeline understands. The checks are designed around that contract rather than fighting it.

## The design intent behind the nine checks

The nine sub-checks are `min_length`, `regex` (with `regex_mode`), `blocklist`, `not_common_placeholders`, `not_all_caps`, `controlled_vocabulary`, `date`, `date_order` and `url`. They can be combined on one rule; each catches a distinct failure mode of deposited text, and each is local and deterministic. Their exact parameters and messages are in the [entry checks reference](../reference/entry-checks.md).

Length and text-shape checks handle the "clearly unfinished" class. `min_length` measures content — concatenated for a plain multi-entry field such as `dsDescription`, per entry for a dotted compound path such as `author.authorAffiliation` — because "the description is at least 50 characters" is a single knob a curator can reason about. `regex` with `regex_mode` expresses discipline-specific shapes when a pattern is genuinely known. `blocklist` and the built-in `not_common_placeholders` catch the refusal list and the usual filler words; `not_all_caps` catches shouted titles and only fires when the value actually has cased letters. The intent is to flag low-effort entries, not to judge prose quality.

`controlled_vocabulary` answers a different question: is the value drawn from an agreed set? It is deliberately an inline list on the rule, because a vocabulary without an owner is worse than none — a list the depositors were never taught will fail every deposit. `date` and `date_order` encode the repository's ISO convention and the high-signal case of a reversed range on a compound date field. `url` is a scheme-and-host sanity check by design, not a network probe.

Together they cover plausibility at the level a curator can act on in a letter. What each param accepts, the exact bracketed reason it emits and a paste-ready rule are in [Entry checks reference](../reference/entry-checks.md); duplicating them here would turn this page into a lookup table.

## Failure philosophy: fail closed

The most important property of the handler is what it does when something is wrong. An empty value is incomplete, exactly as it is for a nonempty rule. A rule with no effective checks fails closed with `[no entry checks configured]`, so deleting the last param cannot silently convert a strict rule into a pass. An invalid regex fails the rule with `[rule error: invalid regex]` instead of raising out of the evaluation; an unparseable length or an unknown mode fails with a bracketed rule error instead of being clamped to a convenient value. An exception anywhere inside a rule surfaces as an incomplete row with a reason, never as a missing row.

A failing handler emits a finding. It never emits nothing. Dotted compound paths are checked leaf by leaf, and an empty leaf fails incomplete, matching the default behaviour for nonempty rules. Every bracketed reason becomes part of the displayed value and of the text substituted into the depositor letter, so the curator and the depositor see the same diagnosis.

Nothing leaves the machine. There are no external services, no DOI, Crossref or ORCID resolution and no different Dataverse call than a presence check would make. That is both a privacy property and a determinism one: the same rule and the same value always produce the same verdict. The display-only `skipped` rows used when a curator asks to see unchecked rules never reach the verdict or the draft.

## What ships enrolled

Nothing. The built-in `mcmaster-default` and `minimal` rulesets contain zero `looks_correct` rules, and existing installs behave exactly as before. The engine capability and the Review configuration affordance ship; they become real only when a ruleset opts in. There is no telemetry and no central flag, so each Dataverse instance decides for itself, and a curator can revert a rule or delete its params to return to presence-only checking.

This is a deliberate rollout posture. A plausibility rule that fires on valid deposits erodes trust faster than a miss does, so the default is silence and the decision to enroll is visible in the ruleset rather than hidden in an application setting.

## Why plausibility is not truth

These checks catch "no description yet", an all-caps title or a reversed date range. They cannot tell whether the text is about the data; a convincing wrong answer passes. Character counting is crude and includes spaces, so a long word salad can clear `min_length` — which is why the placeholder and blocker checks are meant to accompany it, not be replaced by it.

A vocabulary is a maintained artifact that fails depositors who were never given the list. ISO-only dates are a curation statement about the repository's convention, and they will mis-flag a deposit written in another date shape or language. A regex is yours to get wrong: an invalid pattern fails loudly, but a careless valid one can flag an entire valid class. Author identifiers keep their dedicated ORCID handler rather than being duplicated as a regex. Live identifier resolution, controlled file-content checks and first-class negation would each be a new handler, not a new param.

## The three phases of enrollment

Enrollment is a change in curation policy, so the recommendation is evidence-led and reversible. The phases below are a way of thinking about that evidence, not commands to run.

**Measure before enabling.** Take the last ten deposits your team curated and imagine `dsDescription` with a 50-character minimum plus the placeholder list, and `title` with the all-caps and placeholder checks. Would any of those ten have failed? That is your noise rate. If more than one in ten would have been flagged, refine the placeholder list before enrolling anything.

**Pilot as Optional.** Copy the McMaster ruleset for one Dataverse or one curator cohort and enable the candidate rules at Optional for a few weeks. Watch how often the flag fires, how often it is right, and whether the letters produce corrected metadata. False positives cost more trust than misses, so the second measure matters most.

**Promote after evidence.** When the false-positive rate is unremarkable — under roughly one in twenty flagged deposits — promote the description and title rules to Required on that ruleset and leave everything else Optional. Reversed date ranges are a good Optional candidate first, because they are high-signal and low-noise for longitudinal data.

Some enrollments belong last or never. A controlled vocabulary for subject or topic needs an agreed, published list and a deposit workflow that sources it from a dropdown. A DOI regex should not gate a required rule until you know deposits reliably carry a DOI. Blocklist words that are ordinary in your discipline need anchoring or a stricter pattern — "draft", for instance, is a substring of "draft legislation".

## How you know it is working

The app has no telemetry or built-in dashboard for these signals; track them from your own review log or a spreadsheet. Three signals are worth keeping. The field-found rate — incomplete rows attributable to `looks_correct` — should start above zero and then settle. The fix rate is the fraction of letters mentioning an entry-correctness finding that come back with a conforming value; below about half, the wording is the problem, not the depositors. False-positive anecdotes deserve more weight than their count suggests: one curator remembering a good deposit that was flagged outweighs a thousand quiet passes.
