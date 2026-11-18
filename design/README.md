# Design sources

Editable source material for the app's artwork, kept out of the runtime
package. Nothing here is imported by the app; the shipped icons live in
`ui/assets/` (generated from these files, not read at runtime).

## `sprites/`

Piskel sprite projects and their exported PNGs, in kebab-case file names:

| File | What it is |
|---|---|
| `icon-32x32.piskel` | 32x32 sprite source (app icon work-in-progress) |
| `new-piskel.piskel` | Latest sprite project (layers embedded in the file) |
| `new-piskel-20261006-163600.piskel` | Dated snapshot of the sprite project |
| `new-piskel-20261007-142602.piskel` | Dated snapshot of the sprite project |
| `new-piskel.png` | Exported PNG of the sprite project |
| `new-piskel-1.png` | Second exported PNG |

The `.piskel` files are opaque editor project files (kept byte-identical via
`.gitattributes`); their layers are embedded, so renaming the files does not
break them.

Edit these in Piskel (https://www.piskelapp.com), then export into
`ui/assets/` and update the icons the app ships
(`ui/assets/docent-mark.ico`, `ui/assets/docent.png`).
