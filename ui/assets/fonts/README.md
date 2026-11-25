# Bundled fonts

Three variable TrueType fonts ship with the app so the intended faces render
on every machine, including the PyInstaller build (the whole `ui/assets`
directory is added to the bundle).

| File | Family | Used for | Licence |
| --- | --- | --- | --- |
| `Inter.ttf` | Inter | All UI text at 12px and 13px | `OFL-Inter.txt` (SIL OFL 1.1) |
| `Fraunces.ttf` | Fraunces | Display text at 16px and 22px | `OFL-Fraunces.txt` (SIL OFL 1.1) |
| `JetBrainsMono.ttf` | JetBrains Mono | Raw metadata payload (the one opt-in mono field) | `OFL-JetBrainsMono.txt` (SIL OFL 1.1) |

Source: the `ofl/` directories of <https://github.com/google/fonts>. These
are variable fonts: Qt 6 selects the requested weight from the font's axes,
so one file covers 400/500/600/700. The OFL licence permits redistribution
with the licence text, which is kept beside each file.

`ui/theme.py::register_fonts()` loads all three with
`QFontDatabase.addApplicationFont()` before `apply_theme()` sets the app
font and stylesheet; the CSS stacks in `FONT_FAMILY`, `HEADING_FAMILY` and
`MONO_FAMILY` keep system fallbacks if a file fails to load.
