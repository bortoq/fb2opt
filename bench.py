#!/usr/bin/env python3
"""Reproducible fb2opt benchmark: corpus + timings + md5 determinism.

Default corpus is the in-repo testdata goldens (small, hermetic enough
for a smoke run); pass your own books for a real measurement. Each book
is copied to a temp dir and optimized in place (lossless, then --lossy
when Pillow+ffmpeg are present); the script prints per-book sizes, md5
of the outputs and wall time. Run twice on two revisions and diff the
table: sizes must only shrink on fixes, md5 must match run to run
(determinism across the image/file pools).

Usage: python3 bench.py [--lossy] [BOOK.fb2.zip ...]
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FB2OPT = os.path.join(HERE, "fb2opt")
CORPUS = [os.path.join(HERE, "testdata", "golden.fb2.zip"),
          os.path.join(HERE, "testdata", "golden-photos.fb2.zip")]


def _md5(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.md5(fh.read()).hexdigest()[:12]
    except OSError:
        return "-"


def _run(books, lossy):
    work = tempfile.mkdtemp(prefix="fb2opt-bench-")
    copies = []
    for src in books:
        if not os.path.isfile(src):
            print(f"[skip] not a file: {src}", file=sys.stderr)
            continue
        dst = os.path.join(work, os.path.basename(src))
        shutil.copyfile(src, dst)
        copies.append((src, dst))
    if not copies:
        return []
    cmd = [sys.executable, FB2OPT] + (["--lossy"] if lossy else [])
    cmd += [dst for _, dst in copies]
    start = time.monotonic()
    proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=3600)
    wall = time.monotonic() - start
    rows = []
    for src, dst in copies:
        before = os.path.getsize(src)
        after = os.path.getsize(dst)
        rows.append((os.path.basename(src), before, after,
                     before - after, _md5(dst)))
    sys.stdout.write(proc.stdout.decode("utf-8", "replace"))
    shutil.rmtree(work, ignore_errors=True)
    return rows, wall


def main(argv):
    lossy = "--lossy" in argv
    books = [a for a in argv[1:] if a != "--lossy"] or CORPUS
    missing = [b for b in books if not os.path.isfile(b)]
    if missing:
        for b in missing:
            print(f"[error] missing: {b}", file=sys.stderr)
        return 2
    rows, wall = _run(books, lossy)
    total = sum(r[3] for r in rows)
    print(f"{'book':44} {'before':>9} {'after':>9} {'saved':>9} md5")
    for name, before, after, saved, digest in rows:
        print(f"{name:44.44} {before:9d} {after:9d} {saved:9d} {digest}")
    mode = "lossy" if lossy else "lossless"
    print(f"[{mode}] {len(rows)} books, saved {total} bytes, "
          f"wall {wall:.1f}s, {os.cpu_count()} cpus")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
