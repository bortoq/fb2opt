# fb2opt

Lossless optimizer for FB2 books packed as `.fb2.zip`. One Python script, no install needed.

What it does:

- recompresses embedded images without quality loss (PNG via `ect`, JPEG via `jpegoptim`);
- minifies XML markup (drops comments and extra whitespace);
- repacks the ZIP at max compression and runs `ect -zip` over it.

The original file is replaced **only** if the new file is smaller
(`old_size - new_size > 0`). Otherwise it is left untouched.

Two extra modes live in the same file: `--extract` pulls images out of
a book, `--pack` puts images from a folder back into it.

## Requirements

- Python 3 (standard library only).
- Optional but recommended: `ect` and `jpegoptim`. Without them only
  XML and ZIP still shrink. Run `fb2opt` with no arguments to see
  what was found.

## Install

```sh
cp fb2opt ~/bin/fb2opt
chmod +x ~/bin/fb2opt
```

## Usage

```sh
fb2opt BOOK.fb2.zip [BOOK2.fb2.zip ...]   # optimize (replace only if smaller)
fb2opt BOOK.fb2 [...]                     # pack raw .fb2 into .fb2.zip next to it
fb2opt --extract SRC [--dir OUT]          # pull images (SRC: file or folder)
fb2opt --pack BOOK.fb2 [--dir IMGDIR]     # put images from IMGDIR into the book
fb2opt --deps                             # show dependencies
fb2opt -h                                 # full help
```

Result line:

```text
BOOK.fb2.zip: saved 126112 bytes (xml: 59555, png: 0, jpg: 74415)
```

The first number is real saved bytes on disk. In brackets — the
unpacked-FB2 breakdown by type: `xml` (markup), `png`, `jpg`
(`other` appears only if such images exist). The bracket numbers
always sum to the unpacked FB2 delta.

## License

MIT, see LICENSE.
