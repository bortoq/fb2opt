# fb2opt

Lossless optimizer for FB2 books packed as `.fb2.zip`. One Python script, no install needed.

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
- Optional but recommended: `ect`. Without it only XML and ZIP
  still shrink. Run `fb2opt` with no arguments to see
  what was found.

## Install

```sh
cp fb2opt ~/bin/fb2opt
chmod +x ~/bin/fb2opt
```

## Usage

```sh
fb2opt BOOK.fb2.zip [BOOK2.fb2.zip ...]   # optimize (replace only if smaller)
fb2opt -r LIBRARY [...]                   # walk folders, optimize every book
fb2opt BOOK.fb2 [...]                     # pack raw .fb2 into .fb2.zip next to it
fb2opt --extract SRC [--dir OUT]          # pull images (SRC: file or folder)
fb2opt --pack BOOK.fb2 [--dir IMGDIR]     # put images from IMGDIR into the book
fb2opt --deps                             # show dependencies
fb2opt --version                          # show version
fb2opt -h                                 # full help
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

- The tool is lossless by design, but keep backups of books you care about.
- Originals are replaced only when the new file is smaller; replacement
  is atomic (`os.replace`), so a crash never leaves a half-written book.
- Temp-file cleanup only ever deletes `fb2opt`'s own `.fb2opt-*.zip`
  candidates, and after every batch the tool verifies that all inputs
  are still in place (a missing file is reported as an error).
- Symlinks are skipped, never followed or replaced.
- In-place optimization breaks hardlinks (the replaced file gets a new inode).
- ZIP dates, permissions and comments are preserved. If an archive (or any
  member) carries a comment, the final `ect -zip` pass is skipped so the
  comments survive — at the cost of a few bytes of extra squeezing.

## License

MIT, see LICENSE.
