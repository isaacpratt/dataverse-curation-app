---
page_type: governance
tgdp_template: Style guide
audience: contributor
---

# Documentation style guide

This page is the in-repository contract for documentation authors. It applies to every page in `docs/` and to the root contributor and README files. The template shapes come from [The Good Docs Project](https://thegooddocsproject.dev) and its [template repository](https://gitlab.com/tgdp/templates).

## Diátaxis quadrants

Four kinds of documentation exist, each with a different job. Name the job before you write the page.

| Quadrant | Job | Typical page |
| --- | --- | --- |
| Tutorial | Learning-oriented: take a learner from nothing to a working result. | `tutorials/first-review.md` |
| How-to | Goal-oriented: give a competent user a recipe for one task. | `how-to/run-the-gates.md` |
| Reference | Information-oriented: describe the machinery dryly and completely. | `reference/cli.md` |
| Explanation | Understanding-oriented: clarify why the system is the way it is. | `explanation/architecture.md` |

One page serves one quadrant. A tutorial teaches; a how-to is a short recipe with numbered steps; reference is factual and neutral; explanation discusses context and trade-offs. If a page mixes two jobs, split it into two pages and link them. Governance pages (style guide, contributing guide, release notes, landing page) and troubleshooting pages are not quadrant pages; they follow their own templates.

## Front matter

Every page published by Zensical (that is, every `.md` under `docs/` except the `adr/`, `reports/` and `proposals/` folders) begins with exactly five lines of front matter, followed immediately by one H1. Root files such as `README.md` and `CONTRIBUTING.md` are not Zensical pages and carry no front matter:

```yaml
---
page_type: how-to
tgdp_template: How-to
audience: developer
---
```

Use these values:

| Key | Allowed values |
| --- | --- |
| `page_type` | `tutorial`, `how-to`, `reference`, `explanation`, `governance`, `troubleshooting`, `home` |
| `tgdp_template` | `Tutorial`, `How-to`, `Installation guide`, `Reference`, `Glossary`, `Concept`, `Explanation`, `Troubleshooting`, `Style guide`, `Release notes`, `Home` |
| `audience` | `curator`, `developer`, `contributor`, `all` |

The `page_type` matches the quadrant, or `governance` for a governance page. The `tgdp_template` names the template the page follows. Do not invent a value.

## Voice and wording

- Write in second person. Address the reader as "you".
- Use the imperative mood for steps in tutorials and how-to pages: "Run the gate", not "You should run the gate".
- Do not use "just", "simply", "obviously", or "easy". They hide difficulty and slow down expert readers.
- Use active voice and present tense.
- Define a term at first use, then use it consistently. Expand an abbreviation on first use: "application programming interface (API)", "persistent identifier (PID)".
- Keep a how-to to numbered task steps for a competent user. Do not teach background in a how-to; link to explanation or reference instead.
- Keep reference pages dry and factual. A reference page does not instruct or persuade.
- Keep explanation pages focused on meaning and decisions, not step-by-step procedure.

## Code and commands

- Fence every code block with a language, for example `powershell`, `python`, or `yaml`.
- Make every command copy-pasteable and true. Use the exact poe task names in `pyproject.toml` (`uv run poe check`, not an invented alias).
- Mark a placeholder clearly, for example `<format>` or `<staged_dir>`.
- A shown file path must exist. A shown API field must match the report contract.
- Do not repeat stale counts from older prose. Check the source: the engine registry currently has 24 family keys, and reports contain more specific check IDs beneath them.

## Layout and links

- Use ATX headings. Start with one H1; use H2 for sections and H3 for subsections without skipping a level.
- Put a blank line before every list, table, and heading.
- Give every table a separator row.
- Leave no trailing whitespace. End every file with a single newline.
- Use relative Markdown links between pages in `docs/` (for example `../reference/project-layout.md` from `docs/how-to/`). Use an absolute URL only for an external resource, such as the GitHub Releases page.
- Add a new page to the explicit `nav` in `zensical.toml`; an unlisted page will not appear in the published site.

## Linting

- `uv run poe docs-lint` runs `pymarkdown --strict-config --config .pymarkdown.json scan -r docs CONTRIBUTING.md README.md`.
- `uv run poe docs-links` checks internal links in the Markdown tree offline; it makes no network requests.
- `uv run poe docs` runs `zensical build --strict`; a broken relative link or anchor fails the build.
- `uv run poe docs-check` chains Markdown lint, offline link check, both generated-section checks, and the strict build. This is the full docs gate.
- The normal pytest suite adds prose and consistency checks: documented UI labels against `ui/assets/strings.json`, style-guide values against the front-matter gate, `poe` task names, API endpoints, cited repository paths, banned filler words, dated verification claims, and the `--export-record` smoke command.
- Two reference blocks are generated: the Check ID index in `docs/reference/checks.md` comes from `engine.checks.registry` (`poe docs-gen-checks`), and the help text plus flag table in `docs/reference/cli.md` comes from `main.build_parser()` (`poe docs-gen-cli`). Change the source first, then regenerate; never hand-edit a marked block.
- `uv run pre-commit run --all-files` also runs pymarkdown and `codespell` over Markdown, plus whitespace and end-of-file checks. External links are checked on a weekly schedule, not on every pull request.

## Definition of done

- [ ] Front matter is five lines with valid `page_type`, `tgdp_template`, and `audience` values; one H1 follows it.
- [ ] The page stays in one quadrant, or follows its governance/troubleshooting template.
- [ ] Voice rules hold: second person, imperative steps, no "just" or "simply", terms defined at first use.
- [ ] Every code block is fenced and true, and commands match `pyproject.toml`.
- [ ] Internal links are relative and resolve; the page is in the `nav` if it is published.
- [ ] `uv run poe docs-check` passes (Markdown lint, offline links, both generated sections, strict build).
- [ ] `uv run pre-commit run --all-files` passes, including pymarkdown and codespell.
- [ ] `uv run pytest -q` passes the docs prose and consistency suites; generated blocks were regenerated, not hand-edited.
- [ ] No stale counts, retired page names, or references to `docs/html/` as the source of truth.
