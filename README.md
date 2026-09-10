# fb2opt

Optimization of FB2 books packed as `.fb2.zip`. One Python script, no install needed.

What it does:

- recompresses embedded images without quality loss (`ect`: PNG via `-9`, JPEG via `-9 -strip -progressive`);
- minifies XML markup (drops comments and extra whitespace);
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
the unpacked FB2 delta.

## Safety notes

- "Lossless" means pixels: default mode never changes a decoded pixel
  (every re-encoding is verified identical before it is kept). PNG text
  chunks and ICC profiles survive re-encoding; JPEG metadata (EXIF/ICC)
  is stripped by design. Keep backups of books you care about.
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
- **Quality ladders.** JPEG 60→95 (progressive, source chroma subsampling
  kept when the source is a JPEG); PNG palette 64→128→192 (no alpha
  images). Each candidate is scored against the original with **SSIM via
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
- No silent re-lossy: images `--lossy` compresses are recorded in the
  `<program-used>` field as `fb2opt-lossy[0.92:id1,id2]` (schema-valid,
  unlike a tag attribute). A re-run skips stamped images (only
  a strictly lower target re-opens them), so quality never ratchets
  down run after run. Old-style tag stamps migrate there on the next
  `--lossy` run. The `marks:` entry in the result line is the stamp
  overhead in bytes (usually negative and tiny — e.g. 19 stamps show
  as `xml: -380` without it); `xml` itself stays honest.
- Presets (measured on painterly cover scans): `0.99` (conservative,
  safe everywhere) ≈ −10 % over lossless; `0.95` (balanced);
  `0.92` (default: ≈ −70 % on covers, SSIM ≈ 0.93 / PSNR ≈ 30 dB —
  smooth gradients show banding on zoom, invisible on e-ink gray).
  Text scans need higher qualities for the same score — the metric,
  not a fixed `-m70`, decides per image.

Even the default lossless mode re-encodes when it can prove
pixel-identity: exact gray → L, palette slack trim, RGB→palette,
few-color JPEG → PNG. A format change rewrites the `content-type`
of the `<binary>` block, so the markup stays honest.

## Text safety

Markup minification never touches rendered text: whitespace between tags
collapses (a single space survives between two inline tags), comments
outside CDATA are dropped, CDATA returns byte-exact. Unlike some
optimizers, fb2opt never glues words together (`one` + `two` stays
two words, not `onetwo`).

## License

MIT, see LICENSE.
