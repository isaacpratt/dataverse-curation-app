---
page_type: how-to
tgdp_template: How-to
audience: curator
---

# Respond to a dataset and export the record

Use these steps after you have [run the checks](run-checks.md) on a dataset.

## Steps

1. Choose the [ruleset](../reference/glossary.md) for the dataset. In the metadata check, pick **McMaster**, **Minimal**, or a custom profile. The results re-evaluate as soon as you change the profile.

2. To edit the rules themselves, open **Configure Rules** from the top nav (its page is titled **Review configuration**). Set each metadata field to **Required**, **Optional**, or **Not checked**, and manage text-search rules under **Content-based Rules**. A **Required** rule blocks approval under the active ruleset; an **Optional** rule is a recommendation and never blocks. Rulesets apply per Dataverse (`*` means all instances) and are stored in `requirements_profiles.json` beside `config.json`. Select **Save** to apply your edits or **Revert** to discard them.

3. Open the **Response** page. It assembles standard text from the incomplete rules and failed checks. Clear the checkbox on any line you do not want to send, and edit the text as needed — edits are saved automatically.

4. Use the Response page actions.

   - **Regenerate** rebuilds the draft from the findings you left checked and discards your edits.
   - **Copy** copies the draft text to the clipboard.
   - **Export** in the draft actions saves the draft as Markdown.

5. Complete the **Sensitivity & ethics review** on the Response page. Answer the five judgment calls: human subjects, consent/IRB documentation, small-cell risk, Indigenous data (CARE), and restricted files under terms of access. The two machine-derivable answers are prefilled with a **Suggested:** value from the scans. Answers persist per dataset. If the active ruleset has `requires_sensitivity` set to `true`, selecting **Approve & Publish** stays blocked until every answer is filled in. When the instance supplies curation labels, those labels replace the generic decision options and this particular gate does not apply.

6. Record your decision and curation label in the Assessment controls. Choose a decision — the generic set is **Approve & Publish**, **Contact Author (Revisions Required)**, **Reject Submission**, and **Hold for Internal Review** — and select a [curation label](../reference/glossary.md) from the instance's own set when one is available. A decision that asks for revisions puts the dataset into a waiting state; when the depositor updates the draft, re-run the checks and continue from there. Any later decision closes the follow-up.

7. Select **Export record** in the dataset header. Dataverse Docent writes a dated `curation-record` folder beside the dataset's workspace folder. It contains the checks report in JSON and Markdown, the depositor response, the curation timeline, per-finding dispositions with notes, the sensitivity questionnaire, the recorded decision and curation label, and a `sha256sums.txt` manifest of the staged files. An `index.json` binds the artifacts together with their hashes.

8. Re-export as often as you need: a later record does not overwrite an earlier one.
