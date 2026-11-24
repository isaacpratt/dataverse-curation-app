---
page_type: how-to
tgdp_template: How-to
audience: curator
---

# Configure a Dataverse instance

Use Settings to tell Dataverse Docent which [Dataverse instance](../reference/glossary.md) to read and where to keep local files. For the meaning of every setting, see the [configuration reference](../reference/configuration.md).

## Steps

1. Open the top-nav **Settings** page, or press `Ctrl+,`.

2. On the **General** tab, set **Dataverse preset** to **Borealis Demo — demo.borealisdata.ca** for `https://demo.borealisdata.ca`, or **Custom…** to enter your own. The **Base URL** field stays editable after you choose a preset.

3. In the [API token](../reference/glossary.md) field, paste a Dataverse API token, or leave it blank. The token is the credential that lets you read drafts and in-review datasets; with a blank token you can browse public content only. When you save with a token, it is stored in the OS credential store (Windows Credential Manager through `keyring`), keyed by base URL; `config.json` then keeps `api_token_source` set to `keyring` and the `api_token` field blank. If the credential store is unavailable, the token is written to `config.json` with owner-only permissions instead.

4. In the [collection alias](../reference/glossary.md) field, enter the short name of a collection, or leave it empty for the whole repository. On the Borealis demo the root alias is `dv`; the values `root` and `:root` are also treated as empty. A bad alias makes the connection test report "The Dataverse URL or collection looks wrong (404). Check the Base URL and collection alias in Settings (Ctrl+,)." Try an empty alias for the whole repository.

5. In the [Workspace](../reference/glossary.md) field, enter the local folder where Dataverse Docent keeps staged files and records.

6. Select **Test connection**. The app calls `GET /api/info/version` and shows whether the instance answers.

7. Select **Save**. Settings are written to `config.json` and the dashboard reloads with the new instance and collection. Select **Revert** to discard your edits.

8. To switch instances later, open **Settings** (`Ctrl+,`) again, choose another preset or edit the fields, then select **Save**. The last choice is remembered: an installed build keeps `config.json` in `%APPDATA%\Dataverse Docent\`, a portable build creates it in the portable folder's root (the executable's parent), and a source run uses the working directory.
