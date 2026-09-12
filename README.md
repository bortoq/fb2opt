# fb2opt

Optimization of FB2 books packed as `.fb2.zip`. One Python script, no install needed.
Uses all CPU cores (books and images in parallel) and caches repeated images within a run.

What it does:

- recompresses embedded images without quality loss (`ect`: PNG via `-9`, JPEG via `-9 -strip -progressive`;
  with `oxipng` installed its reductions run first and `ect --reuse` follows only their output, tiny PNGs try both modes;
  with `jpegtran` installed JPEGs get one extra entropy pass);
- minifies XML markup (drops comments and extra whitespace);
- stores byte-identical images once (references remapped); pays off when
  copies are large or far apart — nearby small copies deflate packs
  almost for free (32 KB window);
- repacks the ZIP at max compression and runs `ect -zip` over it.

The original file is replaced **only** if the new file is smaller
(`old_size - new_size > 0`). Otherwise it is left untouched.

Two extra modes live in the same file: `--extract` pulls images out of
a book, `--pack` puts images from a folder back into it.

## Requirements

- Python 3 (standard library only).
- Optional but recommended: `ect` **with `-progressive` support**
  (0.9.x — verify with `ect | grep -i progressive`). Without it only
  XML and ZIP still shrink; with an older `ect` that lacks
  `-progressive`, JPEGs are silently left untouched. Run `fb2opt`
  with no arguments to see what was found.
- Optional image chain: `oxipng` (PNG reductions before `ect`) and
  `jpegtran` (extra JPEG entropy pass, best from mozjpeg builds).
  Both are used only when they produce strictly smaller output.
- For `--lossy` only: `Pillow` and `ffmpeg`.

| Tool    | Get it | Direct download / install |
|---------|--------|---------------------------|
| `ect` 0.9.x | https://github.com/fhanau/Efficient-Compression-Tool | `curl -L -o ect.tar.gz https://github.com/fhanau/Efficient-Compression-Tool/archive/refs/tags/v0.9.5.tar.gz` (then `cmake` + `make`; needs submodules) |
| `oxipng` | https://github.com/oxipng/oxipng | `cargo install oxipng` (or distro package, e.g. `apt install oxipng`) |
| `jpegtran` / mozjpeg | https://github.com/mozilla/mozjpeg | stock: `apt install libjpeg-turbo-progs`; mozjpeg: build from the repo above |
| `Pillow` | https://pypi.org/project/pillow/ | `pip install pillow` |
| `ffmpeg` | https://ffmpeg.org/download.html | `apt install ffmpeg`, or static builds: https://johnvansickle.com/ffmpeg/ |

## Install

```sh
cp fb2opt ~/bin/fb2opt
chmod +x ~/bin/fb2opt
```

## Usage

```sh
fb2opt BOOK.fb2.zip [BOOK2.fb2.zip ...]   # optimize (replace only if smaller)
fb2opt --lossy                             # same, images also lossy
fb2opt -r                                 # walk current folder (nested)
fb2opt BOOK.fb2 [...]                     # pack raw .fb2 into .fb2.zip next to it
fb2opt --extract BOOK.fb2                 # pull images into current folder
fb2opt --pack BOOK.fb2                    # put images from current folder into the book
fb2opt -h                                 # full help + dependencies
```

Result line:

```text
BOOK.fb2.zip: saved 126112 bytes (xml: 59555, jpg: 74415)
```

The first number is real saved bytes on disk. In brackets — the
unpacked-FB2 breakdown by type: `xml` (markup), `png`, `jpg`
(`other` appears only if such images exist). Only types with
nonzero savings are shown. The bracket numbers always sum to
the unpacked FB2 delta. Rewritten bodies are always single-line
base64, and counters compare against the flattened original — so no
wrapping style ever leaks into the numbers (a negative `png:`/`jpg:`
only means the bytes genuinely grew while packing smaller —
keeping the original would enlarge the archive).

## Safety notes

- "Lossless" means pixels: default mode never changes a decoded pixel
  (every re-encoding is verified identical before it is kept). PNG text
  chunks and ICC profiles survive re-encoding; JPEG metadata (EXIF/ICC)
  is stripped by design. Project rule, enforced by tests: default mode
  ships pixel-exact bytes or keeps the original — anything that cannot
  be proven identical requires `--lossy`. Keep backups of books you
  care about.
- Originals are replaced only when the new file is smaller; replacement
  is atomic (`os.replace`), so a crash never leaves a half-written book.
- Temp-file cleanup only ever deletes `fb2opt`'s own `.fb2opt-*.zip`
  candidates, and after every batch the tool verifies that all inputs
  are still in place (a missing file is reported as an error).
- JPEGs are re-encoded as **progressive** (`ect -9 -strip -progressive`).
  Pixels stay lossless, but metadata (EXIF/ICC) is stripped, and very old
  readers (early PocketBook/ONYX firmware, cheap hardware decoders) may
  open progressive JPEGs slowly or not at all. If you read on such
  a device, check one book first and keep a backup.
- Uses all CPU cores automatically (books and images in parallel, no
  flag); result bytes are identical to a sequential run. A parallel
  batch holds several books in RAM at once.
- Symlinks are skipped, never followed or replaced.
- In-place optimization breaks hardlinks (the replaced file gets a new inode).
- ZIP dates, permissions and comments are preserved. The final `ect -zip`
  pass always runs; comments it strips (archive and member alike) are
  restored afterwards, so nothing is sacrificed for the extra squeezing.

## Lossy mode (`--lossy`)

Opt-in: images are recompressed with losses when it pays off. The program
knows nothing about a book's origin, so every decision is made from the
file itself and guarded by a metric — nothing is taken on faith.

- **Format crossover.** A photo stored as PNG is tried as JPEG; a flat
  graphic stored as JPEG is tried as PNG. Native format goes first and
  the crossover runs only if it didn't win (speed + fewer surprises).
- **Downscale.** Anything larger than 1920 px on the long side is
  resampled (Lanczos) — reader screens end there. The metric compares
  against the downscaled original, i.e. what the reader would show.
- **Gray.** Exactly-gray RGB goes L directly; near-gray images get one
  extra L-mode probe at the winning quality (chroma costs bytes).
- **Meta-strip (documented).** `--lossy` also drops curator-tech
  metadata: `publish-info`, `src-title-info`, `custom-info`, `output`,
  `src-url`/`src-ocr`/`history`/`program-used`/`publisher`, extra authors,
  `keywords`, title `date`, `translator`, author contacts, root
  `stylesheet`. Required `id`/`version`/`date`, reader-visible fields,
  `body` and images always stay (XSD-checked, rollback on surprise).
  Keep a backup: this step is irreversible.
- **Quality ladders.** Near-gray scans go 1-bit PNG first (Otsu, no dither;
  a tile prefilter rejects gradients SSIM would miss, one full-resolution
  retry if the metric fails); then JPEG 60→95
  (progressive, source chroma subsampling kept when the source is
  a JPEG); PNG palette 64→128→192 (no alpha images). Each candidate
  is scored against the original with **SSIM via
  ffmpeg**; the first candidate with SSIM ≥ threshold wins (default 0.92,
  `--lossy-ssim` overrides). Ladders walk upward instead of bisecting
  because quality is *not* monotonic under re-compression. SSIM (not
  Butteraugli) is a deliberate trade-off: ~25 ms per check keeps a book
  in the seconds-to-minutes range; the 0.92 default is tuned for books
  (see presets below).
- The winner is squeezed losslessly (`ect`, same as above) and kept
  **only if strictly smaller** than the lossless result — otherwise
  the pixels stay bit-exact.
- Needs `Pillow` (encoding) and `ffmpeg` (metric); without them `--lossy`
  refuses to run. Transparency and exotic modes (CMYK…) stay lossless.
- No silent re-lossy: images `--lossy` compresses carry one marker byte
  after the image trailer (`target*100`, e.g. 92), so `<binary>` tags stay
  schema-clean and no markup is spent. A re-run skips stamped images (only
  a strictly lower target re-opens them), so quality never ratchets
  down run after run. Old token/tag stamps migrate to bytes on the next
  `--lossy` run. The `marks:` entry is the freed annotation bytes.
  Note: strict validators may flag the trailing byte (PNG/JPEG themselves
  allow data after the trailer, and readers ignore it) — keep a backup.
- Presets (measured on painterly cover scans): `0.99` (conservative,
  safe everywhere) ≈ −10 % over lossless; `0.95` (balanced);
  `0.92` (default: ≈ −70 % on covers, SSIM ≈ 0.93 / PSNR ≈ 30 dB —
  smooth gradients show banding on zoom, invisible on e-ink gray).
  Text scans need higher qualities for the same score — the metric,
  not a fixed `-m70`, decides per image. For scanned books pass
  `--lossy-ssim 0.85`: at the default 0.92 only very light pages go
  1-bit, denser ones stay grayscale JPEG.
- Escape hatch caveat: re-running with a strictly lower target
  re-compresses from the already-lossy pixels (originals are not kept),
  so the true quality to the original ends up below the new target.
  The run prints how many stamped images it re-opened — for critical
  books, compress once from the original instead.

Even the default lossless mode re-encodes when it can prove
pixel-identity: exact gray → L, palette slack trim, RGB→palette,
few-color JPEG → PNG, and stray BMP/PPM/TIFF/GIF from sloppy converters
→ PNG (animation and extra pages always stay as is).
A format change rewrites the `content-type`
of the `<binary>` block, so the markup stays honest.

Embedded SVG (XML text in base64) is minified like the FB2 markup
itself — comments and inter-tag gaps go, tags/attributes/text are
verified unchanged — and its tags are padded to 3-byte boundaries so
repeated fragments encode identically in base64 and deflate finds them.
The format is never converted: SVG stays SVG.

## Text safety

Markup minification never touches rendered text: whitespace between tags
collapses (a single space survives between two inline tags), comments
outside CDATA are dropped, CDATA returns byte-exact. Unlike some
optimizers, fb2opt never glues words together (`one` + `two` stays
two words, not `onetwo`).

## License

MIT, see LICENSE.
