#!/usr/bin/env python3
"""Unit + edge-case tests for fb2opt. Stdlib only: python3 test_fb2opt.py"""
import base64
import importlib.util
import io
import os
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

MOD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fb2opt")
import importlib.machinery as _mach
_loader = _mach.SourceFileLoader("fb2opt_mod", MOD_PATH)
_spec = importlib.util.spec_from_loader("fb2opt_mod", _loader)
mod = importlib.util.module_from_spec(_spec)
sys.modules["fb2opt_mod"] = mod
_loader.exec_module(mod)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
JPG_MIN = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCAAQABADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD4/wDBfwh/1f7j9K958F/CH/V/uP0r2PwX8If9X+4/SvefBfwh/wBX+4/SjB4zbUPDzxD+D3z/2Q==")


def make_fb2(png_b64=None, extra_binaries="", body_text="<p>Hello</p>"):
    png_b64 = png_b64 or base64.b64encode(PNG_1X1).decode()
    return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<FictionBook><description><title-info><genre>sf</genre>"
            "<author><first-name>A</first-name><last-name>B</last-name></author>"
            "<book-title>T</book-title></title-info></description>"
            "<body><!-- a comment -->\n<section>\n"
            f"<title><p>  {body_text}  </p></title>"
            "<p>Keep   spaces   here</p>"
            "</section></body>"
            f"<binary id=\"cover\" content-type=\"image/png\">{png_b64}</binary>"
            f"{extra_binaries}</FictionBook>").encode("utf-8")


def _write(path, data, mode="w"):
    with open(path, mode) as fh:
        fh.write(data)


def _read(path, mode="r"):
    with open(path, mode) as fh:
        return fh.read()


def make_zip(path, fb2_bytes, name="book.fb2", extra=None, comment=b""):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, fb2_bytes)
        for ename, edata in (extra or []):
            z.writestr(ename, edata)
        z.comment = comment


def shrink_file(path, keep=20):
    # Keep both magic and the longest trailer (PNG, 12 bytes) intact.
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) <= keep + 12:
        return False
    with open(path, "wb") as fh:
        fh.write(data[:keep] + data[-12:])
    return True


class TestPureHelpers(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(mod.sanitize_filename("cover"), "cover")
        self.assertEqual(mod.sanitize_filename(""), "img")
        self.assertEqual(mod.sanitize_filename(None), "img")
        self.assertEqual(mod.sanitize_filename(123), "img")
        self.assertEqual(mod.sanitize_filename("   "), "img")
        self.assertEqual(mod.sanitize_filename("a/b\\c:d"), "a_b_c_d")

    def test_tag_name(self):
        self.assertEqual(mod._tag_name("<p>"), "p")
        self.assertEqual(mod._tag_name("</strong>"), "strong")
        self.assertEqual(mod._tag_name("<fb:emphasis>"), "emphasis")
        self.assertEqual(mod._tag_name("</fb:strong>"), "strong")
        self.assertEqual(mod._tag_name("<image xlink:href='#a'/>"), "image")
        self.assertEqual(mod._tag_name(""), "")
        self.assertEqual(mod._tag_name("not a tag"), "")

    def test_minify_inline_keeps_space(self):
        self.assertEqual(mod.minify_skeleton("</emphasis>\n<strong>x"),
                         "</emphasis> <strong>x")

    def test_minify_ns_inline_keeps_space(self):
        self.assertEqual(mod.minify_skeleton("</fb:emphasis>\n<fb:strong>x"),
                         "</fb:emphasis> <fb:strong>x")

    def test_minify_block_removes_gap(self):
        self.assertEqual(mod.minify_skeleton("</p>\n<p>"), "</p><p>")

    def test_minify_chained_gaps_fixpoint(self):
        self.assertEqual(mod.minify_skeleton("<a>\n<b>\n<c>"), "<a><b><c>")

    def test_minify_text_spaces_untouched(self):
        self.assertEqual(mod.minify_skeleton("<p>Keep   spaces</p>"),
                         "<p>Keep   spaces</p>")

    def test_minify_comment_and_cdata(self):
        src = "<p>a</p><!-- drop --><![CDATA[ keep <!-- x --> this ]]><p>b</p>"
        out = mod.minify_skeleton(src)
        self.assertNotIn("drop", out)
        self.assertIn("<![CDATA[ keep <!-- x --> this ]]>", out)

    def test_minify_empty(self):
        self.assertEqual(mod.minify_skeleton(""), "")

    def test_detect_kind(self):
        self.assertEqual(mod.detect_kind(b"", ""), "other")
        self.assertEqual(mod.detect_kind(PNG_1X1, ""), "png")
        self.assertEqual(mod.detect_kind(JPG_MIN, ""), "jpg")
        self.assertEqual(mod.detect_kind(b"GIF89a...", ""), "gif")
        self.assertEqual(mod.detect_kind(b"??", 'content-type="image/png"'), "png")
        self.assertEqual(mod.detect_kind(b"??", 'image/jpeg'), "jpg")
        self.assertEqual(mod.detect_kind(b"??", "no hint"), "other")

    def test_decode_body(self):
        self.assertIsNone(mod.decode_body(None))
        self.assertIsNone(mod.decode_body(""))
        self.assertIsNone(mod.decode_body("   "))
        self.assertIsNone(mod.decode_body("!!!not-base64!!!"))
        self.assertEqual(mod.decode_body(base64.b64encode(b"abc").decode()), b"abc")

    def test_encode_roundtrip(self):
        body = mod.encode_body(b"hello world" * 10)
        self.assertEqual(mod.decode_body(body), b"hello world" * 10)

    def test_stats(self):
        s = mod.Fb2Stats()
        self.assertIn("repack only", s.breakdown())
        s.xml_saved = 5
        o = mod.Fb2Stats(png_saved=3)
        s.add(o)
        self.assertEqual(s.breakdown(), "xml: 5, png: 3")

    def test_decode_payload_encodings(self):
        t, enc = mod.decode_fb2_payload("привет".encode("utf-8"))
        self.assertEqual((t, enc), ("привет", "utf-8"))
        t, enc = mod.decode_fb2_payload("привет".encode("cp1251"))
        self.assertEqual(enc, "cp1251")
        with self.assertRaises(mod.Fb2OptError):
            mod.decode_fb2_payload(None)

    def test_unique_path(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.txt")
            self.assertEqual(mod.unique_path(p), p)
            _write(p, "x")
            self.assertEqual(mod.unique_path(p), os.path.join(d, "a_2.txt"))


class TestOptimizeImages(unittest.TestCase):
    def _img(self, raw, kind, idx=0):
        return mod._Image(idx=idx, img_id="cover", kind=kind, raw=raw,
                          orig_b64_len=100, attrs="", orig_body="BODY")

    def test_empty_list(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(mod.optimize_images([], d, True), {})

    def test_no_tool_keeps(self):
        with tempfile.TemporaryDirectory() as d:
            r = mod.optimize_images([self._img(PNG_1X1, "png")], d, False)
            self.assertEqual(r[0], PNG_1X1)

    def test_gif_needs_no_tool(self):
        with tempfile.TemporaryDirectory() as d:
            r = mod.optimize_images([self._img(b"GIF89a..", "gif")], d, True)
            self.assertEqual(r[0], b"GIF89a..")

    def test_jpeg_uses_progressive_flag(self):
        seen = []

        def fake_run(cmd, **kw):
            seen.append(cmd)
            class R: returncode = 0
            return R()
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod.subprocess, "run", fake_run):
                mod.optimize_images([self._img(JPG_MIN, "jpg")], d, True)
        self.assertTrue(seen)
        self.assertIn("-progressive", seen[0])
        self.assertIn("-strip", seen[0])

    def test_png_no_progressive_flag(self):
        seen = []

        def fake_run(cmd, **kw):
            seen.append(cmd)
            class R: returncode = 0
            return R()
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod.subprocess, "run", fake_run):
                mod.optimize_images([self._img(PNG_1X1, "png")], d, True)
        self.assertTrue(seen)
        self.assertNotIn("-progressive", seen[0])

    def test_smaller_wins_and_broken_output_rejected(self):
        def fake_shrink(cmd, **kw):
            shrink_file(cmd[-1])
            class R: returncode = 0
            return R()

        def fake_truncate(cmd, **kw):
            _write(cmd[-1], b"junk", "wb")
            class R: returncode = 0
            return R()
        big_png = mod.PNG_MAGIC + b"x" * 500 + mod.PNG_TRAILER
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod.subprocess, "run", fake_shrink):
                r = mod.optimize_images([self._img(big_png, "png")], d, True)
                self.assertLess(len(r[0]), len(big_png))
                self.assertTrue(r[0].endswith(mod.PNG_TRAILER))
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod.subprocess, "run", fake_truncate):
                with redirect_stderr(io.StringIO()):
                    r = mod.optimize_images([self._img(big_png, "png")], d, True)
                self.assertEqual(r[0], big_png)


class TestPayloadAndZip(unittest.TestCase):
    def test_payload_breakdown_sums(self):
        big_png = mod.PNG_MAGIC + b"y" * 1000 + mod.PNG_TRAILER
        fb2 = make_fb2(base64.b64encode(big_png).decode())

        def fake(cmd, **kw):
            shrink_file(cmd[-1])
            class R: returncode = 0
            return R()
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod.subprocess, "run", fake):
                with redirect_stderr(io.StringIO()):
                    new, stats = mod.optimize_fb2_payload(fb2, d, True)
        self.assertEqual(len(fb2) - len(new),
                         stats.png_saved + stats.jpg_saved +
                         stats.other_saved + stats.xml_saved)
        self.assertGreater(stats.png_saved, 0)

    def test_payload_skips_bad_blocks(self):
        fb2 = make_fb2(extra_binaries=(
            "<binary>!!!broken!!!</binary>"
            "<binary>xxxx</binary>"))
        with tempfile.TemporaryDirectory() as d:
            new, stats = mod.optimize_fb2_payload(fb2, d, False)
        self.assertEqual(stats.skipped, 2)
        self.assertIn(b"!!!broken!!!", new)

    def test_zip_end_to_end_and_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "book.fb2.zip")
            make_zip(zp, make_fb2(), extra=[("readme.txt", b"keep me")])
            tmp_root = tempfile.mkdtemp(dir=d)
            saved, line = mod.optimize_zip_file(zp, tmp_root, False, [])
            self.assertGreaterEqual(saved, 0)
            self.assertIn("book.fb2.zip", line)
            with zipfile.ZipFile(zp) as z:
                self.assertEqual(z.read("readme.txt"), b"keep me")
            saved2, line2 = mod.optimize_zip_file(zp, tmp_root, False, [])
            self.assertEqual(saved2, 0)
            self.assertEqual(line2, "book.fb2.zip: already optimal")

    def test_zip_without_fb2_errors(self):
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "x.zip")
            with zipfile.ZipFile(zp, "w") as z:
                z.writestr("a.txt", b"hi")
            with self.assertRaises(mod.Fb2OptError):
                mod.optimize_zip_file(zp, tempfile.mkdtemp(dir=d), False, [])

    def test_zip_broken_archive_errors(self):
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "bad.fb2.zip")
            _write(zp, b"not a zip", "wb")
            with self.assertRaises(mod.Fb2OptError):
                mod.optimize_zip_file(zp, tempfile.mkdtemp(dir=d), False, [])

    def test_pack_raw_fb2(self):
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "book.fb2")
            _write(fp, make_fb2(), "wb")
            saved, line = mod.optimize_fb2_file(fp, tempfile.mkdtemp(dir=d),
                                                False, [])
            target = fp + ".zip"
            if os.path.exists(target):
                self.assertIn("saved", line)
            else:
                self.assertIn("not created", line)


class TestTempSafety(unittest.TestCase):
    def test_drop_tmp_removes_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            t = os.path.join(d, ".fb2opt-abc.zip")
            _write(t, "x")
            reg = [t]
            with redirect_stderr(io.StringIO()):
                mod._drop_tmp(t, reg)
            self.assertFalse(os.path.exists(t))
            self.assertEqual(reg, [])

    def test_drop_tmp_refuses_book(self):
        with tempfile.TemporaryDirectory() as d:
            book = os.path.join(d, "book.fb2.zip")
            _write(book, "precious")
            reg = [book]
            err = io.StringIO()
            with redirect_stderr(err):
                mod._drop_tmp(book, reg)
            self.assertTrue(os.path.exists(book))
            self.assertEqual(_read(book), "precious")
            self.assertIn("refusing", err.getvalue())

    def test_drop_tmp_bad_type_safe(self):
        with redirect_stderr(io.StringIO()):
            mod._drop_tmp(None, [])
            mod._drop_tmp("", [])

    def test_sweep_cleans_only_registry(self):
        with tempfile.TemporaryDirectory() as d:
            t = os.path.join(d, ".fb2opt-s.zip")
            _write(t, "x")
            book = os.path.join(d, "b.fb2.zip")
            _write(book, "y")
            with redirect_stderr(io.StringIO()):
                mod._sweep_temps([t, book])
            self.assertFalse(os.path.exists(t))
            self.assertTrue(os.path.exists(book))

    def test_place_smaller_replaces(self):
        with tempfile.TemporaryDirectory() as d:
            final = os.path.join(d, "f.fb2.zip")
            _write(final, b"1" * 100, "wb")
            tmp = os.path.join(d, ".fb2opt-n.zip")
            _write(tmp, b"2" * 10, "wb")
            ok, _ = mod._place_if_smaller(tmp, final, 100, [tmp])
            self.assertTrue(ok)
            self.assertEqual(os.path.getsize(final), 10)

    def test_place_bigger_keeps(self):
        with tempfile.TemporaryDirectory() as d:
            final = os.path.join(d, "f.fb2.zip")
            open(final, "wb").write(b"1" * 10)
            tmp = os.path.join(d, ".fb2opt-n.zip")
            _write(tmp, b"2" * 100, "wb")
            ok, _ = mod._place_if_smaller(tmp, final, 10, [tmp])
            self.assertFalse(ok)
            self.assertEqual(os.path.getsize(final), 10)
            self.assertFalse(os.path.exists(tmp))

    def test_place_refuses_empty(self):
        with tempfile.TemporaryDirectory() as d:
            final = os.path.join(d, "f.fb2.zip")
            open(final, "wb").write(b"1" * 10)
            tmp = os.path.join(d, ".fb2opt-n.zip")
            _write(tmp, b"", "wb")
            with self.assertRaises(mod.Fb2OptError):
                mod._place_if_smaller(tmp, final, 10, [tmp])
            self.assertEqual(os.path.getsize(final), 10)

    def test_place_missing_tmp(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(mod.Fb2OptError):
                mod._place_if_smaller(os.path.join(d, ".fb2opt-no.zip"),
                                      os.path.join(d, "f"), 10, [])


class TestBatch(unittest.TestCase):
    def test_expand_recursive_only_fb2zip(self):
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "sub")
            os.makedirs(sub)
            for name in ("a.fb2.zip", "b.zip", "c.fb2", "d.txt", "e.FB2.ZIP"):
                open(os.path.join(sub, name), "w").write("x")
            out = mod._expand_sources([d], True)
            self.assertEqual(sorted(os.path.basename(p) for p in out),
                             ["a.fb2.zip", "e.FB2.ZIP"])

    def test_expand_nonrecursive_passthrough(self):
        self.assertEqual(mod._expand_sources(["a", "b"], False), ["a", "b"])
        self.assertEqual(mod._expand_sources([], True), [])

    def test_find_vanished(self):
        self.assertEqual(mod._find_vanished({}), [])
        self.assertEqual(mod._find_vanished({"a": True, "b": False}), ["a"]
                         if not os.path.lexists("a") else [])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x")
            _write(p, "1")
            before = {p: os.path.lexists(p)}
            os.unlink(p)
            self.assertEqual(mod._find_vanished(before), [p])

    def test_optimize_one_guards(self):
        with tempfile.TemporaryDirectory() as d:
            link = os.path.join(d, "l.fb2.zip")
            real = os.path.join(d, "r.fb2.zip")
            make_zip(real, make_fb2())
            os.symlink(real, link)
            saved, line = mod._optimize_one(link, tempfile.mkdtemp(dir=d),
                                            False, [])
            self.assertEqual(saved, 0)
            self.assertIn("symlink", line)
            self.assertTrue(os.path.islink(link))
            with self.assertRaises(mod.Fb2OptError):
                mod._optimize_one(d, tempfile.mkdtemp(dir=d), False, [])
            with self.assertRaises(mod.Fb2OptError):
                mod._optimize_one(os.path.join(d, "x.txt"),
                                  tempfile.mkdtemp(dir=d), False, [])

    def test_batch_census_reports_vanished(self):
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "book.fb2.zip")
            make_zip(zp, make_fb2())
            real_one = mod._optimize_one

            def deleting_one(path, tmp_root, have_ect, registry,
                             lossy=None):
                if path == zp:
                    os.unlink(path)
                    return 0, "x: already optimal"
                return real_one(path, tmp_root, have_ect, registry, lossy)
            with mock.patch.object(mod, "_optimize_one", deleting_one):
                err = io.StringIO()
                with redirect_stderr(err):
                    with redirect_stdout(io.StringIO()):
                        rc = mod._run_optimize_batch([zp], True, False, False)
            self.assertEqual(rc, 1)
            self.assertIn("disappeared", err.getvalue())

    def test_batch_ok(self):
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "book.fb2.zip")
            make_zip(zp, make_fb2())
            out = io.StringIO()
            with redirect_stdout(out):
                rc = mod._run_optimize_batch([zp], False, False, False)
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(zp))


class TestExtractPack(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "book.fb2.zip")
            make_zip(zp, make_fb2())
            imgdir = os.path.join(d, "img")
            self.assertEqual(mod.cmd_extract([zp], imgdir, True), 0)
            self.assertTrue(any(f.endswith(".png") for f in os.listdir(imgdir)))
            raw = os.path.join(d, "plain.fb2")
            _write(raw, make_fb2(), "wb")
            self.assertEqual(mod.cmd_pack([raw], imgdir, True), 0)
            self.assertTrue(any(f.startswith("packed_") for f in os.listdir(d)))

    def test_pack_rejects_zip(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(mod.cmd_pack(["b.zip"], "/tmp", True), 1)


HAS_PIL = mod.Image is not None


def _gradient(w=128, h=128):
    from PIL import Image as _I
    im = _I.new("RGB", (w, h))
    px = im.load()
    for x in range(w):
        for y in range(h):
            px[x, y] = ((x * 2) % 256, (y * 2) % 256, (x + y) % 256)
    return im


def _jpeg_bytes(im, q=95):
    import io as _io
    buf = _io.BytesIO()
    im.save(buf, "JPEG", quality=q)
    return buf.getvalue()


def _fake_run(stdout=b"", stderr=b"", rc=0):
    def _run(cmd, **kw):
        class _R:
            returncode = rc
        _R.stdout = stdout
        _R.stderr = stderr
        return _R()
    return _run


class TestSsimScore(unittest.TestCase):
    def test_parse_ok(self):
        err = (b"[Parsed_ssim_0 @ 0x1] SSIM R:0.99 (20.1) G:0.99 (20.2) "
               b"B:0.99 (20.0) All:0.99234 (21.1)\n")
        with mock.patch.object(mod.subprocess, "run", _fake_run(stderr=err)):
            self.assertAlmostEqual(mod._ssim_score("a.png", "b.png"), 0.99234)

    def test_parse_failures(self):
        with mock.patch.object(mod.subprocess, "run", _fake_run(rc=1)):
            self.assertIsNone(mod._ssim_score("a.png", "b.png"))
        with mock.patch.object(mod.subprocess, "run",
                               _fake_run(stderr=b"no metric here\n")):
            self.assertIsNone(mod._ssim_score("a.png", "b.png"))
        with mock.patch.object(mod.subprocess, "run",
                               _fake_run(stderr=b"SSIM All:xyz\n")):
            self.assertIsNone(mod._ssim_score("a.png", "b.png"))
        def _boom(cmd, **kw):
            raise OSError("no ffmpeg")
        with mock.patch.object(mod.subprocess, "run", _boom):
            self.assertIsNone(mod._ssim_score("a.png", "b.png"))
        self.assertIsNone(mod._ssim_score("", "b.png"))

    def test_same_dims(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        raw = _jpeg_bytes(_gradient(32, 32))
        self.assertTrue(mod._same_dims(raw, (32, 32)))
        self.assertFalse(mod._same_dims(raw, (16, 16)))
        self.assertFalse(mod._same_dims(b"junk", (32, 32)))


@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestLossySearch(unittest.TestCase):
    def _img(self, raw, kind):
        return mod._Image(idx=0, img_id="x", kind=kind, raw=raw,
                          orig_b64_len=10, attrs="", orig_body="")

    def test_jpeg_picks_first_passing_rung(self):
        raw = _jpeg_bytes(_gradient(), 95)
        img = self._img(raw, "jpg")
        with tempfile.TemporaryDirectory() as d:
            scores = [0.5, 0.5, 0.999, 0.999]
            with mock.patch.object(mod, "_ssim_score",
                                   side_effect=scores) as m:
                out = mod._lossy_jpeg(mod._pil_open(raw), img, d, 0.99)
            self.assertIsNotNone(out)
            self.assertEqual(m.call_count, 3)  # early stop, Q=70
            self.assertTrue(mod._same_dims(out[0], (128, 128)))

    def test_jpeg_nothing_passes(self):
        raw = _jpeg_bytes(_gradient(), 95)
        img = self._img(raw, "jpg")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", return_value=0.5):
                self.assertIsNone(
                    mod._lossy_jpeg(mod._pil_open(raw), img, d, 0.99))

    def test_jpeg_skips_cmyk(self):
        from PIL import Image as _I
        raw = _jpeg_bytes(_gradient().convert("CMYK"))
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(mod._lossy_variant(self._img(raw, "jpg"), d, 0.9))

    def test_png_skips_alpha(self):
        from PIL import Image as _I
        import io as _io
        for mode in ("RGBA", "LA"):
            buf = _io.BytesIO()
            _I.new(mode, (16, 16)).save(buf, "PNG")
            with tempfile.TemporaryDirectory() as d:
                self.assertIsNone(
                    mod._lossy_variant(self._img(buf.getvalue(), "png"), d, 0.9))

    def test_png_picks_first_passing(self):
        import io as _io
        buf = _io.BytesIO()
        _gradient().save(buf, "PNG")
        raw = buf.getvalue()
        img = self._img(raw, "png")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score",
                                   side_effect=[0.5, 0.999]) as m:
                out = mod._lossy_png(mod._pil_open(raw), img, d, 0.99)
            self.assertIsNotNone(out)
            self.assertEqual(m.call_count, 2)  # 64 fails, 128 wins
            self.assertTrue(mod._same_dims(out[0], (128, 128)))

    def test_variant_skips_gif(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(
                mod._lossy_variant(self._img(b"GIF89a..", "gif"), d, 0.9))

    def test_try_lossy_smaller_wins(self):
        import io as _io
        small = _io.BytesIO()
        _gradient(8, 8).save(small, "PNG")
        small_png = small.getvalue()
        big = mod.PNG_MAGIC + b"z" * 5000 + mod.PNG_TRAILER
        img = self._img(big, "png")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_lossy_variant",
                                   return_value=(small_png, (8, 8))):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    self.assertEqual(mod._try_lossy(img, d, 0.9, big), small_png)

    def test_try_lossy_rejects_bigger(self):
        big = mod.PNG_MAGIC + b"z" * 5000 + mod.PNG_TRAILER
        img = self._img(b"tiny", "png")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_lossy_variant",
                                   return_value=(big, (8, 8))):
                self.assertEqual(mod._try_lossy(img, d, 0.9, b"tiny"), b"tiny")

    def test_no_pil_no_lossy(self):
        with mock.patch.object(mod, "Image", None):
            self.assertFalse(mod.have_pil())
            self.assertIsNone(mod._pil_open(b"abc"))
            with tempfile.TemporaryDirectory() as d:
                self.assertIsNone(
                    mod._lossy_variant(self._img(b"abc", "jpg"), d, 0.9))

    def test_images_end_to_end_without_ect(self):
        raw = _jpeg_bytes(_gradient(200, 200), 95)
        img = self._img(raw, "jpg")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", return_value=0.999):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    r = mod.optimize_images([img], d, False, 0.99)
        self.assertLessEqual(len(r[0]), len(raw))
        self.assertTrue(mod._pil_open(r[0]) is not None)


class TestLossyBatchAndCli(unittest.TestCase):
    def test_batch_refuses_without_tools(self):
        with mock.patch.object(mod, "_lossy_tools_ok", return_value=False):
            with mock.patch.object(mod, "have_pil", return_value=False):
                err = io.StringIO()
                with redirect_stderr(err):
                    rc = mod._run_optimize_batch(["x"], True, False, False, 0.99)
        self.assertEqual(rc, 2)
        self.assertIn("--lossy needs", err.getvalue())

    def test_cli_lossy_flags(self):
        a = mod.parse_args(["--lossy", "b.fb2.zip"])
        self.assertTrue(a.lossy)
        self.assertAlmostEqual(a.lossy_ssim, mod.LOSSY_DEFAULT_SSIM)
        a = mod.parse_args(["--lossy", "--lossy-ssim", "0.995", "b.fb2.zip"])
        self.assertAlmostEqual(a.lossy_ssim, 0.995)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(mod.main(["--lossy-ssim", "2.0", "x"]), 2)
            self.assertEqual(mod.main(["--lossy-ssim", "0", "x"]), 2)

    def test_main_codes(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(mod.main(["--deps"]), 0)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(mod.main(["--extract", "--pack"]), 2)
            self.assertEqual(mod.main([]), 2)

    def test_batch_survives_unexpected_exception(self):
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "a.fb2.zip")
            make_zip(zp, make_fb2())
            calls = {"n": 0}

            def flaky(path, tmp_root, have_ect, registry, lossy=None):
                calls["n"] += 1
                if "a.fb2" in path:
                    raise RuntimeError("boom")
                return 0, "ok"
            with mock.patch.object(mod, "_optimize_one", flaky):
                err = io.StringIO()
                with redirect_stderr(err):
                    with redirect_stdout(io.StringIO()):
                        rc = mod._run_optimize_batch([zp, zp + ".nope"],
                                                     True, False, False)
        self.assertEqual(rc, 1)
        self.assertIn("unexpected RuntimeError", err.getvalue())
        self.assertEqual(calls["n"], 2)


class TestZipComments(unittest.TestCase):
    def _commented_zip(self, path):
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            zi = zipfile.ZipInfo("book.fb2")
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.comment = b"inner comment"
            z.writestr(zi, b"<fb>" + b"y" * 3000 + b"</fb>")
            z.comment = b"ARCHIVE COMMENT"

    def test_restore_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "c.zip")
            self._commented_zip(zp)
            # simulate ect: rewrite same data without comments, smaller
            with zipfile.ZipFile(zp) as z:
                data = z.read("book.fb2")
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED,
                                 compresslevel=9) as z:
                z.writestr("book.fb2", data)
            self.assertTrue(mod._restore_member_comments(
                zp, {"book.fb2": b"inner comment"}))
            with zipfile.ZipFile(zp) as z:
                infos = z.infolist()
                self.assertEqual(infos[0].comment, b"inner comment")
                self.assertIsNone(z.testzip())
                self.assertEqual(z.read("book.fb2"), data)

    def test_restore_noop_and_garbage(self):
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "c.zip")
            _write(zp, b"junk", "wb")
            self.assertFalse(mod._restore_member_comments(
                zp, {"f": b"comment"}))
            self.assertTrue(mod._restore_member_comments(zp, {}))
            self.assertTrue(mod._restore_member_comments(zp, {"f": b""}))
            zp2 = os.path.join(d, "ok.zip")
            with zipfile.ZipFile(zp2, "w") as z:
                z.writestr("a", b"data")
            self.assertTrue(mod._restore_member_comments(
                zp2, {"a": b"new comment"}))
            with zipfile.ZipFile(zp2) as z:
                self.assertEqual(z.infolist()[0].comment, b"new comment")

    def test_write_candidate_restores_after_ect(self):
        with tempfile.TemporaryDirectory() as d:
            info = zipfile.ZipInfo("book.fb2")
            info.compress_type = zipfile.ZIP_DEFLATED
            info.comment = b"inner comment"
            entries = [(info, b"<fb>" + b"z" * 4000 + b"</fb>")]

            def fake_ect(cmd):
                path = cmd[-1]
                with zipfile.ZipFile(path) as z:
                    data = z.read("book.fb2")
                with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED,
                                     compresslevel=9) as z:
                    z.writestr("book.fb2", data[:2000])  # smaller, no comments
                return True
            with mock.patch.object(mod, "run_tool", fake_ect):
                tmp = mod._write_candidate(entries, b"ARCH", d, True, [])
            with zipfile.ZipFile(tmp) as z:
                self.assertEqual(z.infolist()[0].comment, b"inner comment")
                self.assertEqual(z.comment, b"ARCH")
                self.assertIsNone(z.testzip())

    def test_write_candidate_restore_failure_keeps_original(self):
        with tempfile.TemporaryDirectory() as d:
            info = zipfile.ZipInfo("book.fb2")
            info.compress_type = zipfile.ZIP_DEFLATED
            info.comment = b"inner comment"
            with mock.patch.object(mod, "run_tool", lambda cmd: True):
                with mock.patch.object(mod, "_restore_member_comments",
                                       return_value=False):
                    with self.assertRaises(mod.Fb2OptError):
                        mod._write_candidate([(info, b"data")], b"", d,
                                             True, [])

    def test_clone_info_preserves(self):
        src = zipfile.ZipInfo("f.fb2", date_time=(2011, 5, 17, 12, 0, 0))
        src.compress_type = zipfile.ZIP_STORED
        src.comment = b"c"
        src.external_attr = 0o644 << 16
        dst = mod._clone_info(src)
        self.assertEqual(dst.date_time, (2011, 5, 17, 12, 0, 0))
        self.assertEqual(dst.comment, b"c")
        self.assertEqual(dst.external_attr, 0o644 << 16)
        self.assertEqual(dst.compress_type, zipfile.ZIP_STORED)
        dst2 = mod._clone_info(src, zipfile.ZIP_DEFLATED)
        self.assertEqual(dst2.compress_type, zipfile.ZIP_DEFLATED)

    def test_verify_candidate_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, ".fb2opt-v.zip")
            with zipfile.ZipFile(zp, "w") as z:
                z.writestr("a", b"1")
                z.writestr("extra", b"2")
            with self.assertRaises(mod.Fb2OptError):
                mod._verify_candidate(zp, ["a"], [])
            self.assertFalse(os.path.exists(zp))  # dropped, registry clean


class TestExoticEncodings(unittest.TestCase):
    def test_utf16_passthrough_byte_exact(self):
        text = ("<?xml version='1.0' encoding='utf-16'?>"
                "<FictionBook><description><title-info><book-title>T"
                "</book-title></title-info></description><body><section>"
                "<p>Text</p></section></body></FictionBook>")
        payload = text.encode("utf-16")
        with tempfile.TemporaryDirectory() as d:
            new, _ = mod.optimize_fb2_payload(payload, d, False)
        self.assertEqual(new, payload)

    def test_koi8_single_line_byte_exact(self):
        body = ("<?xml version='1.0' encoding='koi8-r'?>"
                "<FictionBook><description><title-info><book-title>"
                "Привет</book-title></title-info></description><body>"
                "<section><p>Текст без разрывов</p></section></body>"
                "</FictionBook>").encode("koi8-r")
        with tempfile.TemporaryDirectory() as d:
            new, _ = mod.optimize_fb2_payload(body, d, False)
        self.assertEqual(new, body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
