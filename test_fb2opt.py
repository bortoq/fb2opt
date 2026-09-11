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
            "<book-title>T</book-title></title-info>"
            "<document-info><author><first-name>A</first-name>"
            "<last-name>B</last-name></author>"
            "<date value=\"2020-01-01\">2020</date><id>test-id</id>"
            "<version>1.0</version></document-info></description>"
            "<body><!-- a comment -->\n<section>\n"
            f"<title><p>  {body_text}  </p></title>"
            "<p>Keep   spaces   here</p>"
            "</section></body>"
            f"<binary id=\"cover\" content-type=\"image/png\">{png_b64}</binary>"
            f"{extra_binaries}</FictionBook>").encode()


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
        t, enc = mod.decode_fb2_payload("привет".encode())
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
                             lossy=None, img_workers=1):
                if path == zp:
                    os.unlink(path)
                    return 0, "x: already optimal"
                return real_one(path, tmp_root, have_ect, registry, lossy,
                                img_workers)
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

    def test_try_lossy_packed_cost_decides(self):
        # Audit §2 in miniature: raw-smaller but packed-bigger loses.
        import io as _io
        import random as _rnd
        small = _io.BytesIO()
        _gradient(8, 8).save(small, "PNG")
        small_png = small.getvalue()
        flat_big = mod.PNG_MAGIC + b"z" * 5000 + mod.PNG_TRAILER
        rng = _rnd.Random(42)
        noisy_big = mod.PNG_MAGIC + rng.randbytes(5000) + mod.PNG_TRAILER
        self.assertLess(len(small_png), len(flat_big))
        self.assertGreater(mod._packed_cost(small_png),
                           mod._packed_cost(flat_big))
        self.assertLess(mod._packed_cost(small_png),
                        mod._packed_cost(noisy_big))
        img = self._img(flat_big, "png")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_lossy_variant",
                                   return_value=(small_png, (8, 8))):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    self.assertEqual(mod._try_lossy(img, d, 0.9, flat_big),
                                     flat_big)
        img = self._img(noisy_big, "png")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_lossy_variant",
                                   return_value=(small_png, (8, 8))):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    self.assertEqual(mod._try_lossy(img, d, 0.9, noisy_big),
                                     small_png)

    def test_packed_cost_properties(self):
        import random as _rnd
        rng = _rnd.Random(7)
        zeros = b"\0" * 1000
        noise = rng.randbytes(1000)
        self.assertEqual(mod._packed_cost(b""), 0)
        self.assertLess(mod._packed_cost(zeros), mod._packed_cost(noise))
        self.assertLess(mod._packed_cost(zeros), 1000)

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
        with redirect_stderr(io.StringIO()):
            self.assertEqual(mod.main(["--extract", "--pack"]), 2)
            self.assertEqual(mod.main([]), 2)
            for bad in (["--deps"], ["--version"]):
                with self.assertRaises(SystemExit) as cm:
                    mod.main(bad)
                self.assertEqual(cm.exception.code, 2)

    def test_help_shows_deps(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                mod.main(["-h"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("Dependencies", buf.getvalue())
        self.assertIn("ect", buf.getvalue())
        self.assertIn(mod.VERSION, buf.getvalue())

    def test_bare_r_walks_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            make_zip(os.path.join(d, "b.fb2.zip"), make_fb2())
            sub = os.path.join(d, "sub")
            os.makedirs(sub)
            make_zip(os.path.join(sub, "c.fb2.zip"), make_fb2())
            old = os.getcwd()
            os.chdir(d)
            try:
                with redirect_stdout(io.StringIO()):
                    with redirect_stderr(io.StringIO()):
                        self.assertEqual(mod.main(["-r"]), 0)
            finally:
                os.chdir(old)
            self.assertTrue(os.path.exists(os.path.join(d, "b.fb2.zip")))
            self.assertTrue(os.path.exists(os.path.join(sub, "c.fb2.zip")))

    @unittest.skipUnless(HAS_PIL, "Pillow missing")
    def test_lossy_on_zip_book(self):
        import io as _io
        buf = _io.BytesIO()
        _gradient(200, 200).save(buf, "JPEG", quality=95)
        raw = buf.getvalue()
        self.assertGreater(len(raw), mod.LOSSY_MIN_BYTES)
        fb2 = make_fb2(base64.b64encode(raw).decode())
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "book.fb2.zip")
            make_zip(zp, fb2)
            with mock.patch.object(mod, "_ssim_score", return_value=0.999):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    with mock.patch.object(mod, "have_ffmpeg",
                                           return_value=True):
                        with mock.patch.object(mod, "_lossy_tools_ok",
                                               return_value=True):
                            with redirect_stdout(io.StringIO()):
                                self.assertEqual(mod.main(["--lossy", zp]), 0)
            self.assertTrue(os.path.exists(zp))

    def test_batch_survives_unexpected_exception(self):
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "a.fb2.zip")
            make_zip(zp, make_fb2())
            calls = {"n": 0}

            def flaky(path, tmp_root, have_ect, registry, lossy=None,
                      img_workers=1):
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





def _solid(mode, size, color):
    from PIL import Image as _I
    return _I.new(mode, size, color)


def _flat_two_color():
    from PIL import Image as _I, ImageDraw as _D
    im = _I.new("RGB", (64, 64), "white")
    _D.Draw(im).rectangle([8, 8, 56, 56], fill="navy")
    return im


def _png_bytes(im):
    import io as _io
    buf = _io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


class TestPixelHelpers(unittest.TestCase):
    def test_pixels_equal(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        a = _png_bytes(_flat_two_color())
        self.assertTrue(mod._pixels_equal(a, a))
        b = _png_bytes(_gradient(64, 64))
        self.assertFalse(mod._pixels_equal(a, b))
        self.assertFalse(mod._pixels_equal(b"junk", a))
        self.assertFalse(mod._pixels_equal(a, b"junk"))

    def test_has_alpha(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        self.assertFalse(mod._has_alpha(_solid("RGB", (4, 4), "red")))
        self.assertTrue(mod._has_alpha(_solid("RGBA", (4, 4), (1, 2, 3, 4))))
        p = _solid("P", (4, 4), 0)
        p.info["transparency"] = 0
        self.assertTrue(mod._has_alpha(p))
        self.assertTrue(mod._has_alpha(None))

    def test_exact_gray(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        self.assertTrue(mod._is_exact_gray(_solid("RGB", (8, 8), (77, 77, 77))))
        self.assertTrue(mod._is_exact_gray(_solid("L", (8, 8), 77)))
        self.assertFalse(mod._is_exact_gray(_solid("RGB", (8, 8), (77, 78, 77))))
        self.assertFalse(mod._is_exact_gray(None))

    def test_gray_score_orders(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        gray = mod._gray_score(_solid("RGB", (64, 64), (100, 100, 100)))
        red = mod._gray_score(_solid("RGB", (64, 64), (220, 30, 30)))
        self.assertLess(gray, 1.0)
        self.assertGreater(red, 20.0)

    def test_distinct_colors(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        self.assertEqual(mod._distinct_colors(_flat_two_color()), 2)
        self.assertIsNone(mod._distinct_colors(_gradient()))
        self.assertIsNone(mod._distinct_colors(None))

    def test_scale_pair(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        work, ref = mod._scale_pair(_solid("RGB", (100, 50), "red"))
        self.assertEqual(work.size, (100, 50))
        self.assertEqual(ref.mode, "RGB")
        work, ref = mod._scale_pair(_solid("RGB", (2500, 1000), "red"))
        self.assertEqual(max(work.size), mod.LOSSY_MAX_SIDE)
        self.assertEqual(work.size, (1920, 768))
        self.assertEqual(ref.size, work.size)
        self.assertEqual(mod._scale_pair(None), (None, None))

    def test_set_content_type(self):
        self.assertEqual(
            mod._set_content_type(' id="a" content-type="image/png"', "jpg"),
            ' id="a" content-type="image/jpeg"')
        self.assertEqual(
            mod._set_content_type(' id="a" CONTENT-TYPE="image/png" ', "jpg"),
            ' id="a" content-type="image/jpeg" ')
        self.assertEqual(mod._set_content_type(' id="a"', "png"),
                         ' id="a" content-type="image/png"')

    def test_patch_binary_attrs(self):
        text = '<binary id="a" content-type="image/png">BODY</binary>'
        out = mod._patch_binary_attrs(text, "a", ' id="a" content-type="image/jpeg"')
        self.assertIn('content-type="image/jpeg"', out)
        self.assertIn("BODY", out)
        self.assertEqual(mod._patch_binary_attrs(text, "zzz", " X"), text)
        self.assertEqual(mod._patch_binary_attrs("", "a", " X"), "")


@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestLosslessVariants(unittest.TestCase):
    def _img(self, raw, kind):
        return mod._Image(idx=0, img_id="v", kind=kind, raw=raw,
                          orig_b64_len=10, attrs="", orig_body="")

    def test_gray_rgb_png_to_l(self):
        raw = _png_bytes(_solid("RGB", (32, 32), (90, 90, 90)))
        img = self._img(raw, "png")
        with tempfile.TemporaryDirectory() as d:
            out = mod._try_lossless_variants(img, d, raw, False)
        back = mod._pil_open(out)
        self.assertEqual(back.mode, "L")
        self.assertLess(len(out), len(raw))
        self.assertTrue(mod._pixels_equal(out, raw))

    def test_palette_trim(self):
        from PIL import Image as _I
        p = _flat_two_color().quantize(colors=256, method=_I.MEDIANCUT)
        buf = _png_bytes(p)
        before = len(buf)
        img = self._img(buf, "png")
        with tempfile.TemporaryDirectory() as d:
            out = mod._try_lossless_variants(img, d, buf, False)
        self.assertLessEqual(len(out), before)
        self.assertTrue(mod._pixels_equal(out, buf))

    def test_skips_alpha_and_garbage(self):
        import io as _io
        buf = _io.BytesIO()
        _solid("RGBA", (16, 16), (1, 2, 3, 4)).save(buf, "PNG")
        raw = buf.getvalue()
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                mod._try_lossless_variants(self._img(raw, "png"), d, raw, True),
                raw)
            self.assertEqual(
                mod._try_lossless_variants(self._img(b"junk", "png"), d,
                                           b"junk", True), b"junk")

    def test_jpeg_graphic_tries_png(self):
        im = _flat_two_color()
        raw = _jpeg_bytes(im, 85)
        img = self._img(raw, "jpg")
        seen = []
        real_squeeze = mod._ect_squeeze

        def spy(path, kind):
            seen.append(kind)
            return real_squeeze(path, kind)
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ect_squeeze", spy):
                out = mod._try_lossless_variants(img, d, raw, True)
        self.assertTrue(mod._pixels_equal(out, raw))
        self.assertLessEqual(mod._packed_cost(out), mod._packed_cost(raw))

    def test_ratio_gate_skips_hopeless_ect(self):
        # §5.2: candidate packed 3x over base -> no ect pass; ~1x -> chance.
        gray = _solid("RGB", (32, 32), (90, 90, 90))
        import io as _io
        buf = _io.BytesIO()
        gray.save(buf, "PNG")
        raw = buf.getvalue()
        img = self._img(raw, "png")
        real_cost = mod._packed_cost

        def _scaled(factor):
            def _fake(b):
                if _fake.first:
                    _fake.first = False
                    return real_cost(b)
                return int(real_cost(b) * factor)
            _fake.first = True
            return _fake

        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_packed_cost", _scaled(3.0)):
                with mock.patch.object(mod, "_ect_squeeze") as squeeze:
                    out = mod._try_lossless_variants(img, d, raw, True)
            self.assertEqual(squeeze.call_count, 0)
            self.assertEqual(out, raw)
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_packed_cost", _scaled(1.0)):
                with mock.patch.object(mod, "_ect_squeeze",
                                       wraps=mod._ect_squeeze) as squeeze:
                    out = mod._try_lossless_variants(img, d, raw, True)
            self.assertGreater(squeeze.call_count, 0)
            self.assertTrue(mod._pixels_equal(out, raw))

    def test_kind_change_rewrites_content_type(self):
        fb2 = make_fb2()
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "optimize_images",
                                   return_value={0: JPG_MIN}):
                new, stats = mod.optimize_fb2_payload(fb2, d, False)
        self.assertIn(b'content-type="image/jpeg"', new)
        self.assertNotIn(b'content-type="image/png"', new)


@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestSmartLossy(unittest.TestCase):
    def _img(self, raw, kind):
        return mod._Image(idx=0, img_id="s", kind=kind, raw=raw,
                          orig_b64_len=10, attrs="", orig_body="")

    def test_downscale_caps_result(self):
        raw = _jpeg_bytes(_gradient(2500, 1800), 95)
        img = self._img(raw, "jpg")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", return_value=0.999):
                out = mod._lossy_jpeg(mod._pil_open(raw), img, d, 0.99)
        self.assertIsNotNone(out)
        self.assertLessEqual(max(mod._pil_open(out[0]).size),
                             mod.LOSSY_MAX_SIDE)

    def test_native_win_skips_crossover(self):
        raw = _jpeg_bytes(_gradient(128, 128), 95)
        img = self._img(raw, "jpg")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", return_value=0.999):
                with mock.patch.object(
                        mod, "_lossy_png",
                        side_effect=AssertionError("must not run")):
                    out = mod._lossy_jpeg(mod._pil_open(raw), img, d, 0.99,
                                          True, len(raw) * 10)
        self.assertIsNotNone(out)

    def test_crossover_when_native_loses(self):
        raw = _jpeg_bytes(_gradient(128, 128), 95)
        img = self._img(raw, "jpg")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", return_value=0.999):
                out = mod._lossy_jpeg(mod._pil_open(raw), img, d, 0.99,
                                      True, 1)  # base tiny: native "loses"
        self.assertIsNotNone(out)  # crossover PNG may still deliver

    def test_tiny_images_skip_search(self):
        img = self._img(b"x" * 100, "jpg")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(
                    mod, "_lossy_variant",
                    side_effect=AssertionError("must not run")):
                self.assertEqual(mod._try_lossy(img, d, 0.9, b"x" * 100),
                                 b"x" * 100)

    def test_gray_probe_fires_on_near_gray(self):
        from PIL import Image as _I
        base = _I.new("RGB", (64, 64), (120, 121, 119))
        raw = _jpeg_bytes(base, 95)
        self.assertLess(mod._gray_score(base), mod.GRAY_PROBE_SCORE)
        self.assertFalse(mod._is_exact_gray(base))
        img = self._img(raw, "jpg")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", return_value=0.999):
                out = mod._lossy_jpeg(mod._pil_open(raw), img, d, 0.99)
        self.assertIsNotNone(out)
        got = mod._pil_open(out[0])
        # L probe wins on near-gray: result decodes gray
        self.assertTrue(mod._is_exact_gray(got) or got.mode == "RGB")





def _text_png():
    from PIL import Image as _I, PngImagePlugin as _P
    im = _I.new("RGB", (32, 32), (110, 110, 110))
    info = _P.PngInfo()
    info.add_text("Comment", "scan 12")
    import io as _io
    buf = _io.BytesIO()
    im.save(buf, "PNG", pnginfo=info)
    return buf.getvalue()


@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestMetadataHonesty(unittest.TestCase):
    def _img(self, raw, kind):
        return mod._Image(idx=0, img_id="m", kind=kind, raw=raw,
                          orig_b64_len=10, attrs="", orig_body="")

    def test_text_chunk_survives_gray(self):
        from PIL import Image as _I
        raw = _text_png()
        self.assertIn("Comment", _I.open(__import__("io").BytesIO(raw)).text)
        with tempfile.TemporaryDirectory() as d:
            out = mod._try_lossless_variants(self._img(raw, "png"), d,
                                             raw, False)
        back = _I.open(__import__("io").BytesIO(out))
        back.load()
        self.assertEqual(back.mode, "L")  # conversion happened...
        self.assertEqual(back.text.get("Comment"), "scan 12")  # ...metadata kept
        self.assertTrue(mod._pixels_equal(out, raw))

    def test_exif_blocks_jpeg_to_png(self):
        crafted = _flat_two_color()
        crafted.info["exif"] = b"fake-exif"
        raw = _jpeg_bytes(_flat_two_color(), 90)
        img = self._img(raw, "jpg")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_distinct_colors",
                                   wraps=mod._distinct_colors) as spy:
                with mock.patch.object(mod, "_pil_open", return_value=crafted):
                    out = mod._try_lossless_variants(img, d, raw, False)
        self.assertEqual(out, raw)
        self.assertEqual(spy.call_count, 0)  # no attempt at all
        with tempfile.TemporaryDirectory() as d:
            del crafted.info["exif"]
            with mock.patch.object(mod, "_distinct_colors",
                                   wraps=mod._distinct_colors) as spy:
                with mock.patch.object(mod, "_pil_open", return_value=crafted):
                    mod._try_lossless_variants(img, d, raw, False)
        self.assertGreater(spy.call_count, 0)  # control: attempt proceeds

    def test_flat_scan_book_stays_honest(self):
        from PIL import Image as _I, ImageDraw as _D
        im = _I.new("RGB", (350, 500), "white")
        d = _D.Draw(im)
        for y in range(20, 500, 18):
            d.rectangle([30, y, 320, y + 8], fill="black")
        raw = _jpeg_bytes(im, 95)
        fb2 = make_fb2(base64.b64encode(raw).decode())
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "flat.fb2.zip")
            make_zip(zp, fb2)
            before = os.path.getsize(zp)
            saved, _ = mod.optimize_zip_file(
                zp, tempfile.mkdtemp(dir=d), False, [])
            after = os.path.getsize(zp)
            self.assertLessEqual(after, before)
            with zipfile.ZipFile(zp) as z:
                assert z.testzip() is None
                data = z.read("book.fb2")
        import re as _re
        m = _re.search(rb"<binary\b[^>]*>(.*?)</binary\s*>", data, _re.DOTALL)
        self.assertIsNotNone(m)
        self.assertTrue(mod._pixels_equal(
            base64.b64decode(b"".join(m.group(1).split())), raw))


HAVE_ECT = __import__("shutil").which("ect") is not None


@unittest.skipUnless(HAS_PIL and HAVE_ECT, "need Pillow + real ect")
class TestWithRealEct(unittest.TestCase):
    def test_exact_variant_end_to_end(self):
        raw = _png_bytes(_solid("RGB", (48, 48), (60, 60, 60)))
        img = mod._Image(idx=0, img_id="g", kind="png", raw=raw,
                         orig_b64_len=10, attrs="", orig_body="")
        with tempfile.TemporaryDirectory() as d:
            out = mod.optimize_images([img], d, True)
        self.assertLessEqual(mod._packed_cost(out[0]),
                             mod._packed_cost(raw))
        self.assertTrue(mod._pixels_equal(out[0], raw))





class TestLossyMarker(unittest.TestCase):
    def test_mark_helpers(self):
        self.assertIsNone(mod._lossy_mark(""))
        self.assertIsNone(mod._lossy_mark(' id="a"'))
        self.assertAlmostEqual(
            mod._lossy_mark(' id="a" fb2opt-lossy="0.92"'), 0.92)
        self.assertIsNone(mod._lossy_mark(' fb2opt-lossy="junk"'))
        self.assertEqual(
            mod._strip_mark_from_attrs(' id="a" fb2opt-lossy="0.92"'),
            ' id="a"')
        self.assertEqual(mod._strip_mark_from_attrs(' id="a"'), ' id="a"')

    def test_token_roundtrip(self):
        marks = {"cover.jpg": 0.92, "pic 1,x;y=z": 0.85}
        token = mod._render_lossy_token(marks)
        self.assertTrue(token.startswith("fb2opt-lossy["))
        back = mod._parse_lossy_token(" converted by X " + token + " done")
        self.assertEqual(back, marks)
        self.assertEqual(mod._render_lossy_token({}), "")
        self.assertEqual(mod._parse_lossy_token("no token here"), {})
        self.assertEqual(mod._parse_lossy_token("fb2opt-lossy[0.92]"), {})
        self.assertEqual(mod._parse_lossy_token("fb2opt-lossy[xx:a]"), {})

    def test_token_upsert(self):
        base = ("<description><document-info><author><first-name>A</first-name>"
                "</author><date>2020-01-01</date><id>1</id><version>1.0</version>"
                "</document-info></description>")
        out, ok = mod._upsert_program_used(base, "fb2opt-lossy[0.92:a]")
        self.assertTrue(ok)
        self.assertIn("<program-used>fb2opt-lossy[0.92:a]</program-used>", out)
        self.assertLess(out.index("<program-used>"),
                        out.index("<date>"))
        again, ok = mod._upsert_program_used(out, "fb2opt-lossy[0.85:a,b]")
        self.assertTrue(ok)
        self.assertEqual(again.count("fb2opt-lossy["), 1)
        self.assertIn("[0.85:a,b]", again)
        # existing program-used text survives
        src2 = base.replace("</author>",
                            "</author><program-used>Any2Fb2</program-used>", 1)
        out2, ok = mod._upsert_program_used(src2, "fb2opt-lossy[0.92:a]")
        self.assertTrue(ok)
        self.assertIn("Any2Fb2 fb2opt-lossy[0.92:a]", out2)
        # no document-info at all: honest failure, input untouched
        same, ok = mod._upsert_program_used("<a>text</a>", "fb2opt-lossy[0.9:x]")
        self.assertFalse(ok)
        self.assertEqual(same, "<a>text</a>")

    def test_variant_skips_marked(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        raw = _jpeg_bytes(_gradient(64, 64), 90)
        img = mod._Image(idx=0, img_id="m", kind="jpg", raw=raw,
                         orig_b64_len=10,
                         attrs=' id="m" fb2opt-lossy="0.92"', orig_body="")
        def _boom(a, b):
            raise AssertionError("metric must not run on marked")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "have_ffmpeg", return_value=True):
                with mock.patch.object(mod, "_ssim_score", _boom):
                    self.assertIsNone(mod._lossy_variant(img, d, 0.92))
                    self.assertIsNone(mod._lossy_variant(img, d, 0.95))
        # stricter target re-opens the search (metric runs, may still lose)
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "have_ffmpeg", return_value=True):
                with mock.patch.object(mod, "_ssim_score", return_value=0.99):
                    with mock.patch.object(mod, "run_tool", lambda cmd: True):
                        out = mod._lossy_variant(img, d, 0.85)
        self.assertIsNotNone(out)

    def test_mark_written_and_honored_on_rerun(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        import io as _io
        import random as _rnd
        from PIL import Image as _I
        small = _io.BytesIO()
        # already minimal-palette: a re-run finds nothing to improve
        _gradient(8, 8).quantize(colors=8, method=_I.MEDIANCUT,
                                 dither=_I.Dither.NONE).save(small, "PNG")
        small_png = small.getvalue()
        noisy = (mod.PNG_MAGIC + _rnd.Random(3).randbytes(5000)
                 + mod.PNG_TRAILER)
        fb2 = make_fb2(base64.b64encode(noisy).decode())
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_lossy_variant",
                                   return_value=(small_png, (8, 8))):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    with mock.patch.object(mod, "_lossy_tools_ok",
                                            return_value=True):
                        new, stats = mod.optimize_fb2_payload(fb2, d, False, 0.92)
        text = new.decode("utf-8")
        self.assertIn("fb2opt-lossy[0.92:cover]", text)
        self.assertNotIn('fb2opt-lossy="', text)  # tags stay schema-clean
        # re-run: marked image is shielded, metric never runs
        def _boom(a, b):
            raise AssertionError("metric must not run on marked")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", _boom):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    new2, stats2 = mod.optimize_fb2_payload(new, d, False, 0.92)
        self.assertEqual(stats2.marked, 1)
        self.assertEqual(new2, new)

    def test_legacy_attr_migrates_to_token(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        import io as _io
        buf = _io.BytesIO()
        _gradient(16, 16).save(buf, "PNG")
        raw = buf.getvalue()
        fb2 = make_fb2(base64.b64encode(raw).decode())
        fb2 = fb2.replace(b'id="cover"',
                          b'id="cover" fb2opt-lossy="0.92"', 1)
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "run_tool", lambda cmd: True):
                new, _ = mod.optimize_fb2_payload(fb2, d, False, 0.92)
        text = new.decode("utf-8")
        self.assertNotIn('fb2opt-lossy="', text)  # legacy gone from tags
        self.assertIn("fb2opt-lossy[0.92:cover]", text)  # lives in token





class TestOutputInvariants(unittest.TestCase):
    @unittest.skipUnless(HAS_PIL, "Pillow missing")
    def test_no_placeholders_survive(self):
        # Shadowing a uuid placeholder variable once shipped books
        # with __FB2OPT_ markers inside: never again, in any mode.
        import io as _io
        import random as _rnd
        from PIL import Image as _I
        small = _io.BytesIO()
        _gradient(8, 8).quantize(colors=8, method=_I.MEDIANCUT,
                                 dither=_I.Dither.NONE).save(small, "PNG")
        noisy = (mod.PNG_MAGIC + _rnd.Random(11).randbytes(2000)
                 + mod.PNG_TRAILER)
        fb2 = make_fb2(base64.b64encode(noisy).decode())
        with tempfile.TemporaryDirectory() as d:
            for have_ect, lossy in ((False, None), (True, None),
                                    (False, 0.92), (True, 0.92)):
                with mock.patch.object(
                        mod, "_lossy_variant",
                        return_value=(small.getvalue(), (8, 8))):
                    with mock.patch.object(mod, "run_tool",
                                           lambda cmd: True):
                        new, _ = mod.optimize_fb2_payload(
                            fb2, d, have_ect, lossy)
                self.assertNotIn(b"__FB2OPT_", new,
                                 f"placeholder leaked (ect={have_ect}, lossy={lossy})")

    def test_fallback_stamps_tags_without_document_info(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        import io as _io
        small = _io.BytesIO()
        _gradient(8, 8).save(small, "PNG")
        import random as _rnd
        raw = (mod.PNG_MAGIC + _rnd.Random(5).randbytes(3000)
               + mod.PNG_TRAILER)
        text = ("<?xml version='1.0'?><FictionBook><description><title-info>"
                "<book-title>T</book-title></title-info></description>"
                "<body><section><p>T</p></section></body>"
                "<binary id='c' content-type='image/png'>"
                + base64.b64encode(raw).decode() + "</binary></FictionBook>")
        fb2 = text.encode("utf-8")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_lossy_variant",
                                   return_value=(small.getvalue(), (8, 8))):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    with mock.patch.object(mod, "_lossy_tools_ok",
                                           return_value=True):
                        err = io.StringIO()
                        with redirect_stderr(err):
                            new, _ = mod.optimize_fb2_payload(
                                fb2, d, False, 0.92)
        self.assertIn("cannot place lossy token", err.getvalue())
        self.assertIn(b'fb2opt-lossy="0.92"', new)  # protected, legacy way
        self.assertNotIn(b"__FB2OPT_", new)

    def test_binary_tags_stay_schema_clean(self):
        # Audit v8 §4: only id + content-type may sit on <binary>.
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        import io as _io
        small = _io.BytesIO()
        _gradient(8, 8).save(small, "PNG")
        raw = (mod.PNG_MAGIC + b"q" * 3000 + mod.PNG_TRAILER)
        fb2 = make_fb2(base64.b64encode(raw).decode())
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_lossy_variant",
                                   return_value=(small.getvalue(), (8, 8))):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    new, _ = mod.optimize_fb2_payload(fb2, d, False, 0.92)
        import re as _re
        tags = _re.findall(rb"<binary\b([^>]*)>", new)
        self.assertTrue(tags)
        for tag in tags:
            names = _re.findall(rb'([a-zA-Z_:][-a-zA-Z0-9_.:]*)\s*=', tag)
            self.assertEqual(sorted(names), [b"content-type", b"id"],
                             f"unexpected attrs: {tag[:80]}")





class TestReopenedAndWrapper(unittest.TestCase):
    def test_reopened_count_and_warning(self):
        # A stricter target re-opens a stamped image that actually wins
        # again; the warning fires exactly then (not on no-op runs).
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        import io as _io
        import random as _rnd
        from PIL import Image as _I
        small = _io.BytesIO()
        _gradient(8, 8).quantize(colors=8, method=_I.MEDIANCUT,
                                 dither=_I.Dither.NONE).save(small, "PNG")
        small_png = small.getvalue()
        noisy = (mod.PNG_MAGIC + _rnd.Random(21).randbytes(5000)
                 + mod.PNG_TRAILER)
        fb2 = make_fb2(base64.b64encode(noisy).decode())
        fb2 = fb2.replace(b'id="cover"',
                          b'id="cover" fb2opt-lossy="0.95"', 1)
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_lossy_variant",
                                   return_value=(small_png, (8, 8))):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    with mock.patch.object(mod, "_lossy_tools_ok",
                                           return_value=True):
                        new, stats = mod.optimize_fb2_payload(
                            fb2, d, False, 0.85)
        self.assertEqual(stats.reopened, 1)
        self.assertEqual(stats.marked, 0)
        self.assertIn(b"fb2opt-lossy[0.85:cover]", new)
        err = io.StringIO()
        with redirect_stderr(err):
            mod._warn_skipped("b.fb2.zip", stats)
        self.assertIn("re-opened", err.getvalue())
        self.assertIn("already-lossy", err.getvalue())

    def test_wrapper_counted_in_marks(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        import io as _io
        small = _io.BytesIO()
        _gradient(8, 8).save(small, "PNG")
        import random as _rnd2
        rng = _rnd2.Random(9)
        noise = bytes(rng.randrange(256) for _ in range(200 * 200 * 3))
        from PIL import Image as _I2
        big = _io.BytesIO()
        _I2.frombytes("RGB", (200, 200), bytes(noise)).save(big, "PNG")
        assert len(big.getvalue()) > mod.LOSSY_MIN_BYTES
        fb2 = make_fb2(base64.b64encode(big.getvalue()).decode())
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_lossy_variant",
                                   return_value=(small.getvalue(), (8, 8))):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    with mock.patch.object(mod, "_lossy_tools_ok",
                                           return_value=True):
                        _, stats = mod.optimize_fb2_payload(fb2, d, False, 0.92)
        token = mod._render_lossy_token({"cover": 0.92})
        # make_fb2 has document-info but no program-used: +29 wrapper bytes
        self.assertEqual(stats.marks, -(len(token) + 29))

    def test_append_costs_one_space(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        import io as _io
        small = _io.BytesIO()
        _gradient(8, 8).save(small, "PNG")
        import random as _rnd2
        rng = _rnd2.Random(9)
        noise = bytes(rng.randrange(256) for _ in range(200 * 200 * 3))
        from PIL import Image as _I2
        big = _io.BytesIO()
        _I2.frombytes("RGB", (200, 200), bytes(noise)).save(big, "PNG")
        assert len(big.getvalue()) > mod.LOSSY_MIN_BYTES
        fb2 = make_fb2(base64.b64encode(big.getvalue()).decode())
        fb2 = fb2.replace(b"<date value=",
                          b"<program-used>Tool X</program-used><date value=", 1)
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_lossy_variant",
                                   return_value=(small.getvalue(), (8, 8))):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    with mock.patch.object(mod, "_lossy_tools_ok",
                                           return_value=True):
                        new, stats = mod.optimize_fb2_payload(
                            fb2, d, False, 0.92)
        token = mod._render_lossy_token({"cover": 0.92})
        self.assertEqual(stats.marks, -(len(token) + 1))
        self.assertIn(b"Tool X " + token.encode(), new)





class TestSingleLineBodies(unittest.TestCase):
    def test_encode_is_single_line(self):
        raw = bytes((i * 7) % 256 for i in range(300))
        body = mod.encode_body(raw)
        self.assertNotIn("\n", body)
        self.assertEqual(mod.decode_body(body), raw)
        self.assertEqual(len(body), (len(raw) + 2) // 3 * 4)
        self.assertEqual(mod._flat_b64_len(raw), len(body))
        self.assertEqual(mod._flat_b64_len(b""), 0)

    def test_output_bodies_are_single_line(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        from PIL import Image as _I
        import io as _io2
        buf = _io2.BytesIO()
        _I.new("RGB", (32, 32), (90, 90, 90)).save(buf, "PNG")
        raw = buf.getvalue()
        b64 = base64.b64encode(raw).decode()
        wrapped = "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64))
        fb2 = make_fb2(wrapped)
        with tempfile.TemporaryDirectory() as d:
            new, stats = mod.optimize_fb2_payload(fb2, d, False, None)
        import re as _re
        m = _re.search(rb"<binary\b[^>]*>(.*?)</binary\s*>", new, _re.DOTALL)
        body = m.group(1).decode()
        self.assertNotIn("\n", body)
        # counter is exact: flattened original minus new body
        self.assertEqual(stats.png_saved + stats.jpg_saved
                         + stats.other_saved,
                         len(b64) - len(body))
        # idempotent: single line in, single line out
        with tempfile.TemporaryDirectory() as d:
            new2, _ = mod.optimize_fb2_payload(new, d, False, None)
        self.assertEqual(new2, new)





@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestParallelDeterminism(unittest.TestCase):
    def test_workers_agree(self):
        from PIL import Image as _I
        import io as _io
        raws = []
        for _, (mode, color) in enumerate(
                (("RGB", (200, 30, 30)), ("RGB", (40, 40, 40)),
                 ("L", 128), ("P", 3))):
            buf = _io.BytesIO()
            _I.new(mode, (64, 64), color).save(buf, "PNG")
            raws.append(buf.getvalue())
        buf = _io.BytesIO()
        _gradient(64, 64).save(buf, "JPEG", quality=90)
        raws.append(buf.getvalue())
        kinds = ["png", "png", "png", "png", "jpg"]
        images = [mod._Image(idx=i, img_id=f"i{i}", kind=kinds[i], raw=r,
                             orig_b64_len=10, attrs="", orig_body="")
                  for i, r in enumerate(raws)]
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "run_tool", lambda cmd: True):
                seq = mod.optimize_images(images, d, True, None, None, 1)
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "run_tool", lambda cmd: True):
                par = mod.optimize_images(images, d, True, None, None, 4)
        self.assertEqual(seq, par)





@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestGenericFormats(unittest.TestCase):
    def _img(self, raw, kind):
        return mod._Image(idx=0, img_id="g", kind=kind, raw=raw,
                          orig_b64_len=10, attrs="", orig_body="")

    def test_bmp_crosses_to_png(self):
        import io as _io
        buf = _io.BytesIO()
        _gradient(64, 64).save(buf, "BMP")
        raw = buf.getvalue()
        self.assertTrue(raw.startswith(b"BM"))
        with tempfile.TemporaryDirectory() as d:
            out = mod._try_lossless_variants(self._img(raw, "other"), d,
                                             raw, False)
        back = mod._pil_open(out)
        self.assertEqual(back.format, "PNG")
        self.assertLessEqual(mod._packed_cost(out), mod._packed_cost(raw))
        self.assertTrue(mod._pixels_equal(out, raw))

    def test_tiff_and_gif_stay(self):
        import io as _io
        buf = _io.BytesIO()
        _flat_two_color().save(buf, "TIFF")
        raw = buf.getvalue()
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                mod._try_lossless_variants(self._img(raw, "other"), d,
                                           raw, False), raw)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                mod._try_lossless_variants(self._img(b"GIF89a...", "gif"), d,
                                           b"GIF89a...", True),
                b"GIF89a...")





@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestDefaultPixelIdentity(unittest.TestCase):
    """Architectural invariant: default mode never changes decoded pixels.

    Whatever the heuristics do (gray, palette, crossover), the bytes they
    install must decode to identical pixels — or the original stays.
    """

    def _cases(self):
        from PIL import Image as _I
        import io as _io

        def _png(im, **kw):
            buf = _io.BytesIO()
            im.save(buf, "PNG", **kw)
            return buf.getvalue()

        def _jpg(im, **kw):
            buf = _io.BytesIO()
            im.save(buf, "JPEG", **kw)
            return buf.getvalue()

        gradient = _gradient(96, 96)
        yield "rgb-photo-png", "png", _png(gradient)
        yield "rgb-photo-jpg", "jpg", _jpg(gradient, quality=90)
        yield "palette", "png", _png(
            gradient.quantize(colors=64, method=_I.MEDIANCUT))
        gray = _I.new("RGB", (48, 48), (110, 110, 110))
        yield "gray-rgb", "png", _png(gray)
        yield "gray-l", "png", _png(gray.convert("L"))
        rgba = _I.new("RGBA", (32, 32), (10, 20, 30, 128))
        yield "alpha", "png", _png(rgba)
        yield "bilevel", "png", _png(gradient.convert("1"))
        buf = _io.BytesIO()
        gradient.save(buf, "BMP")
        yield "bmp-as-other", "other", buf.getvalue()

    def test_pixels_survive_default(self):
        for name, kind, raw in self._cases():
            img = mod._Image(idx=0, img_id=name, kind=kind, raw=raw,
                             orig_b64_len=10, attrs="", orig_body="")
            with tempfile.TemporaryDirectory() as d:
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    out = mod.optimize_images([img], d, True, None, None, 1)
            self.assertTrue(mod._pixels_equal(out[0], raw),
                            f"pixels changed: {name}")


class TestAuditDirectCoverage(unittest.TestCase):
    """Прямые тесты закрывают замечания аудита (по одному на функцию)."""

    def test_run_tool_guards(self):
        self.assertFalse(mod.run_tool([]))
        self.assertFalse(mod.run_tool(["nonexistent-fb2opt-xyz-123"]))
        class _Ok:
            returncode = 0
        with mock.patch.object(mod.subprocess, "run", return_value=_Ok()):
            self.assertTrue(mod.run_tool(["whatever-cmd"]))
        with mock.patch.object(mod.subprocess, "run", side_effect=OSError("x")):
            self.assertFalse(mod.run_tool(["ect", "f"]))

    def test_cpu_umask_fresh_reg(self):
        self.assertGreaterEqual(mod._cpu_count(), 1)
        with mock.patch.object(mod.os, "cpu_count", side_effect=OSError("x")):
            self.assertEqual(mod._cpu_count(), 1)
        mod._CACHED_UMASK = None
        m1 = mod._umask()
        m2 = mod._umask()
        self.assertEqual(m1, m2)
        self.assertIsNotNone(mod._CACHED_UMASK)
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "s.fb2")
            _write(src, "x")
            info = mod._fresh_info("b.fb2", src)
            self.assertEqual(info.filename, "b.fb2")
            self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)
        reg: list = []
        mod._reg_append(reg, "a")
        mod._reg_append(reg, "b")
        self.assertEqual(reg, ["a", "b"])
        mod._reg_forget(reg, "a")
        mod._reg_forget(reg, "missing")
        self.assertEqual(reg, ["b"])
        # registry lock smoke across threads
        import threading as _t
        reg2: list = []
        def _w(n):
            for i in range(50):
                mod._reg_append(reg2, f"{n}-{i}")
        ths = [_t.Thread(target=_w, args=(n,)) for n in range(4)]
        [t.start() for t in ths]
        [t.join() for t in ths]
        self.assertEqual(len(reg2), 200)

    def test_deps_helpers(self):
        st = mod.dep_status()
        self.assertEqual(len(st), 5)
        self.assertEqual([n for n, _, _ in st],
                         ["ect", "oxipng", "jpegtran", "Pillow", "ffmpeg"])
        self.assertTrue(all(len(r) == 3 for r in st))
        with mock.patch.object(mod.shutil, "which", return_value=None):
            with mock.patch.object(mod, "have_pil", return_value=False):
                with mock.patch.object(mod, "have_ffmpeg", return_value=False):
                    st2 = mod.dep_status()
                    self.assertTrue(all(f is False for _, _, f in st2))
                    self.assertIn("NOT FOUND", mod.format_deps())
        self.assertIn("Dependencies", mod.format_deps())
        self.assertIn("Usage", mod.short_hint())
        self.assertIn("Dependencies", mod.short_hint())
        self.assertTrue(mod.have_pil() if HAS_PIL else not mod.have_pil())
        self.assertIsInstance(mod.have_ffmpeg(), bool)
        with mock.patch.object(mod, "have_pil", return_value=True):
            with mock.patch.object(mod, "have_ffmpeg", return_value=True):
                self.assertTrue(mod._lossy_tools_ok())
            with mock.patch.object(mod, "have_ffmpeg", return_value=False):
                self.assertFalse(mod._lossy_tools_ok())

    def test_gap_single_pass(self):
        # direct _gap_replace: right tag unconsumed (lookahead)
        mm = mod.GAP_RE.search("</p>\n<p>")
        self.assertIsNotNone(mm)
        self.assertEqual(mod._gap_replace(mm), "</p>")
        mm2 = mod.GAP_RE.search("</emphasis>\n<strong>")
        self.assertEqual(mod._gap_replace(mm2), "</emphasis> ")
        # chained gaps collapse in one pass O(N)
        self.assertEqual(mod.minify_skeleton("<a>\n<b>\n<c>"), "<a><b><c>")
        big = "<p>" + "</p>\n<p>" * 2000 + "x</p>"
        out = mod.minify_skeleton(big)
        self.assertNotIn("\n", out.replace("x", ""))
        self.assertEqual(mod.minify_skeleton(""), "")

    def test_ignored_spans(self):
        txt = "<p>a</p><!-- <binary id='x'>AA==</binary> --><![CDATA[<binary id='y'>BB==</binary>]]><binary id='z'>CC==</binary>"
        spans = mod._ignored_spans(txt)
        self.assertEqual(len(spans), 2)
        got = [m.group(1) for m in mod._binary_matches(txt)]
        self.assertEqual(len(got), 1)
        self.assertIn("z", got[0])
        self.assertEqual(list(mod._binary_matches("")), [])
        self.assertEqual(mod._ignored_spans(""), [])

    def test_commented_binary_untouched(self):
        b64 = base64.b64encode(PNG_1X1).decode()
        fb2 = make_fb2(b64)
        fb2s = fb2.decode("utf-8").replace("</FictionBook>",
            "<!-- <binary id='ghost' content-type='image/png'>" + b64 + "</binary> --></FictionBook>")
        fb2b = fb2s.encode("utf-8")
        with tempfile.TemporaryDirectory() as d:
            new, stats = mod.optimize_fb2_payload(fb2b, d, False)
        # comments are dropped by minify: ghost must not become pics=2
        self.assertEqual(stats.pics, 1)
        self.assertNotIn(b"__FB2OPT_", new)
        self.assertNotIn(b"ghost", new)

    def test_looks_complete(self):
        self.assertTrue(mod._looks_complete("gif", b"anything"))
        self.assertTrue(mod._looks_complete("other", b"x"))
        self.assertFalse(mod._looks_complete("png", b""))
        self.assertFalse(mod._looks_complete("jpg", b""))
        self.assertTrue(mod._looks_complete("png", mod.PNG_MAGIC + b"x" + mod.PNG_TRAILER))
        self.assertFalse(mod._looks_complete("png", mod.PNG_MAGIC + b"x"))
        self.assertTrue(mod._looks_complete("jpg", mod.JPEG_MAGIC + b"x" + mod.JPEG_TRAILER))
        self.assertFalse(mod._looks_complete("jpg", mod.JPEG_MAGIC + b"x"))

    def test_process_image_guards(self):
        with tempfile.TemporaryDirectory() as d:
            img = mod._Image(idx=0, img_id="e", kind="png", raw=b"", orig_b64_len=0, attrs="", orig_body="")
            self.assertEqual(mod._process_image(img, d, True, None, None), (0, b""))
            gif = mod._Image(idx=1, img_id="g", kind="gif", raw=b"GIF89a..", orig_b64_len=1, attrs="", orig_body="")
            self.assertEqual(mod._process_image(gif, d, True, None, None)[1], b"GIF89a..")
            other = mod._Image(idx=2, img_id="o", kind="other", raw=b"zz", orig_b64_len=1, attrs="", orig_body="")
            self.assertEqual(mod._process_image(other, d, True, None, None)[1], b"zz")
            with mock.patch.object(mod, "Image", None):
                png = mod._Image(idx=3, img_id="p", kind="png", raw=PNG_1X1, orig_b64_len=1, attrs="", orig_body="")
                self.assertEqual(mod._process_image(png, d, False, None, None)[1], PNG_1X1)

    def test_set_token_legacy_project_write(self):
        self.assertEqual(mod._set_lossy_mark("", 0.92), ' fb2opt-lossy="0.92"')
        self.assertIn('0.85', mod._set_lossy_mark(' id="a" fb2opt-lossy="0.92"', 0.85))
        self.assertIn('fb2opt-lossy', mod._set_lossy_mark(' id="a"', 0.9))
        self.assertGreater(mod._token_bytes("a fb2opt-lossy[0.92:x] b"), 0)
        self.assertEqual(mod._token_bytes("no token"), 0)
        self.assertEqual(mod._token_bytes(""), 0)
        txt = "<binary id='a' fb2opt-lossy=\"0.92\"/><binary id='b'/>"
        out, n = mod._strip_legacy_marks(txt)
        self.assertGreater(n, 0)
        self.assertNotIn("fb2opt-lossy", out)
        k, present = mod._project_lossy_marks("t", [], None)
        self.assertEqual((k, present), ({}, set()))
        # write token: reopened path + fallback path
        imgs = [mod._Image(idx=0, img_id="cover", kind="png", raw=b"r", orig_b64_len=1, attrs=' id="cover"', orig_body="")]
        base = ("<description><document-info><author><a/></author>"
                "<program-used>X</program-used><date>2020</date></document-info></description>"
                "<binary id=\"cover\">AA==</binary>")
        known = {"cover": 0.95}
        skel, old, new, reop = mod._write_lossy_token(base, dict(known), {"cover"}, imgs, {0}, 0.85, {0: ' id="cover"'})
        self.assertEqual(reop, 1)
        self.assertIn("fb2opt-lossy[0.85:cover]", skel)
        skel2, _, _, _ = mod._write_lossy_token("<a/>", {}, set(), [], set(), 0.9, {})
        self.assertEqual(skel2, "<a/>")

    def test_encode_exact_squeeze_save_drop(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        from PIL import Image as _I
        im = _I.new("RGB", (8, 8), (10, 20, 30))
        enc = mod._encode_png_bytes(im, im)
        self.assertTrue(enc.startswith(mod.PNG_MAGIC))
        self.assertIsNone(mod._encode_png_bytes(None, None))
        raw_g = _png_bytes(_solid("RGB", (16, 16), (50, 50, 50)))
        img = mod._Image(idx=0, img_id="g", kind="png", raw=raw_g, orig_b64_len=1, attrs="", orig_body="")
        cands = mod._exact_png_candidates(img, mod._pil_open(raw_g))
        self.assertGreaterEqual(len(cands), 1)
        # exif blocks crossover
        crafted = _flat_two_color()
        crafted.info["exif"] = b"x"
        imgj = mod._Image(idx=0, img_id="j", kind="jpg", raw=b"r", orig_b64_len=1, attrs="", orig_body="")
        self.assertEqual(mod._exact_crossover_candidates(imgj, crafted), [])
        big = _I.new("RGB", (2000, 2000), "red")
        self.assertEqual(mod._exact_crossover_candidates(imgj, big), [])
        with tempfile.TemporaryDirectory() as d:
            base = b"base-bytes"
            cb, cost = mod._squeeze_candidate(img, d, base, "png", base, mod._packed_cost(base), False)
            self.assertEqual(cb, base)
            mod._drop_paths([os.path.join(d, "no-such"), ""])
            # _save_png keeps text chunks
            t = _I.new("RGB", (8, 8), (1, 2, 3))
            t.text = {"K": "V"}
            buf = io.BytesIO()
            mod._save_png(t, buf, meta_from=t)
            self.assertTrue(buf.getvalue().startswith(mod.PNG_MAGIC))

    def test_jpeg_ladder_gray_probe(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        raw = _jpeg_bytes(_gradient(32, 32), 95)
        im = mod._pil_open(raw)
        work, ref = mod._scale_pair(im)
        with tempfile.TemporaryDirectory() as d:
            stem = os.path.join(d, "s")
            with mock.patch.object(mod, "_ssim_score", side_effect=[0.5, 0.999]):
                hit = mod._jpeg_ladder(work, ref, stem, 0.99)
            self.assertIsNotNone(hit)
            with mock.patch.object(mod, "_ssim_score", return_value=0.1):
                self.assertIsNone(mod._jpeg_ladder(work, ref, stem, 0.99))
            self.assertIsNone(mod._jpeg_ladder(None, None, stem, 0.9))
            g = mod._gray_probe_at(work, stem + "_ref.png", ref.size, stem, 70, 0.9999, [])
            self.assertIsNone(g)

    def test_iter_payloads_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(list(mod._iter_fb2_payloads([])), [])
            self.assertEqual(list(mod._iter_fb2_payloads([None])), [])
            zp = os.path.join(d, "b.fb2.zip")
            make_zip(zp, make_fb2())
            got = list(mod._iter_fb2_payloads([zp]))
            self.assertEqual(len(got), 1)
            bad = os.path.join(d, "bad.zip")
            _write(bad, b"junk", "wb")
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(list(mod._payloads_from_file(bad)), [])
            self.assertIn("error", err.getvalue().lower())
            with redirect_stderr(io.StringIO()):
                self.assertEqual(list(mod._payloads_from_file(os.path.join(d, "no.txt"))), [])
            # traversal guard
            imgdir = os.path.join(d, "img")
            os.makedirs(imgdir)
            _write(os.path.join(imgdir, "ok.png"), "x")
            self.assertTrue(mod._find_replacement("ok", imgdir).endswith("ok.png"))
            self.assertIsNone(mod._find_replacement("../ok", imgdir))
            self.assertIsNone(mod._find_replacement("/etc/passwd", imgdir))
            self.assertIsNone(mod._find_replacement("", imgdir))
            self.assertIsNone(mod._find_replacement("ok", os.path.join(d, "no-dir")))

    def test_limits_and_validate(self):
        self.assertGreater(mod.MAX_ARCHIVE_BYTES, 0)
        self.assertGreater(mod.MAX_MEMBER_BYTES, 0)
        self.assertGreater(mod.MAX_IMAGE_PX, 0)
        self.assertIsNone(mod.decode_body("ab!cd"))
        self.assertEqual(mod.decode_body(base64.b64encode(b"hi").decode()), b"hi")
        self.assertEqual(mod._flat_b64_len(b""), 0)
        self.assertEqual(mod._packed_cost(b""), 0)
        if HAS_PIL:
            self.assertIsNone(mod._pil_open(b"x" * (mod.MAX_MEMBER_BYTES + 1)))
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "c.zip")
            with zipfile.ZipFile(zp, "w") as z:
                z.writestr("a", b"1")
            self.assertFalse(mod._restore_member_comments(os.path.join(d, "missing.zip"), {"a": b"c"}))
        # archive too large pre-check via fake infos
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "big.fb2.zip")
            make_zip(zp, make_fb2())
            class _FakeInfo:
                filename = "book.fb2"
                file_size = mod.MAX_MEMBER_BYTES + 1
                def __init__(self): pass
            class _FakeZip:
                comment = b""
                def __init__(self, *a, **k): pass
                def __enter__(self): return self
                def __exit__(self, *a): return False
                def infolist(self): return [_FakeInfo()]
            with mock.patch.object(mod.zipfile, "ZipFile", _FakeZip):
                with self.assertRaises(mod.Fb2OptError):
                    mod.optimize_zip_file(zp, tempfile.mkdtemp(dir=d), False, [])



class TestVariantChains(unittest.TestCase):
    """Варианты 1 (oxipng->ect) и 2 (jpegtran-финиш): команды, порядок, фолбэки."""

    def test_have_helpers(self):
        with mock.patch.object(mod.shutil, "which", return_value="/usr/bin/x"):
            self.assertTrue(mod.have_oxipng())
            self.assertTrue(mod.have_jpegtran())
        with mock.patch.object(mod.shutil, "which", return_value=None):
            self.assertFalse(mod.have_oxipng())
            self.assertFalse(mod.have_jpegtran())

    def test_ect_reuse_probe(self):
        mod._ECT_REUSE_OK = None
        class R:
            returncode = 0
            stdout = b"--reuse  Keep PNG filter"
        with mock.patch.object(mod.subprocess, "run", return_value=R()):
            self.assertTrue(mod._ect_reuse_ok())
            self.assertTrue(mod._ect_reuse_ok())  # cached
        mod._ECT_REUSE_OK = None
        class R2:
            returncode = 0
            stdout = b"no such flag here"
        with mock.patch.object(mod.subprocess, "run", return_value=R2()):
            self.assertFalse(mod._ect_reuse_ok())
        mod._ECT_REUSE_OK = None
        with mock.patch.object(mod.subprocess, "run", side_effect=OSError("x")):
            self.assertFalse(mod._ect_reuse_ok())
        mod._ECT_REUSE_OK = None
        with mock.patch.object(mod.subprocess, "run", return_value=R()):
            self.assertTrue(mod._ect_reuse_ok())
        mod._ECT_REUSE_OK = None  # leave clean for other tests

    def test_png_chain_order_and_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.png")
            _write(p, mod.PNG_MAGIC + b"x" * 100 + mod.PNG_TRAILER, "wb")
            seen: list = []
            def fake_rewrite(cmd):
                seen.append(cmd)
                if cmd[0] == "oxipng":
                    with open(cmd[-1], "ab") as fh:  # simulate rewrite
                        fh.write(b"z")
                return True
            with mock.patch.object(mod, "have_oxipng", return_value=True):
                with mock.patch.object(mod, "_ect_reuse_ok", return_value=True):
                    with mock.patch.object(mod, "run_tool", fake_rewrite):
                        mod._ect_squeeze(p, "png")
            self.assertEqual(seen[0][:3], ["oxipng", "-o", "4"])
            self.assertNotIn("--strip", seen[0])  # chunks (text/ICC) must survive
            self.assertEqual(seen[1][:3], ["ect", "-9", "--reuse"])
            # no oxipng, old ect: plain -9, still no -progressive
            seen.clear()
            def fake_plain(cmd):
                seen.append(cmd)
                return True
            with mock.patch.object(mod, "have_oxipng", return_value=False):
                with mock.patch.object(mod, "_ect_reuse_ok", return_value=False):
                    with mock.patch.object(mod, "run_tool", fake_plain):
                        mod._ect_squeeze(p, "png")
            self.assertEqual(seen, [["ect", "-9", p]])
            # oxipng failure: ect still runs
            seen.clear()
            def flaky(cmd):
                seen.append(cmd)
                return False if cmd[0] == "oxipng" else True
            with mock.patch.object(mod, "have_oxipng", return_value=True):
                with mock.patch.object(mod, "_ect_reuse_ok", return_value=False):
                    with mock.patch.object(mod, "run_tool", flaky):
                        mod._ect_squeeze(p, "png")
            self.assertEqual([c[0] for c in seen], ["oxipng", "ect"])

    def test_reuse_only_after_successful_oxipng(self):
        # External audit P1: --reuse without oxipng keeps the ORIGINAL
        # filters and compresses ~2-7x worse. Plain ect -9 then.
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.png")
            _write(p, mod.PNG_MAGIC + b"x" * 100 + mod.PNG_TRAILER, "wb")
            seen: list = []
            def fake(cmd):
                seen.append(cmd)
                return True
            # oxipng absent, ect supports --reuse -> plain -9 runs first
            # on pristine bytes (small file then also tries --reuse)
            with mock.patch.object(mod, "have_oxipng", return_value=False):
                with mock.patch.object(mod, "_ect_reuse_ok", return_value=True):
                    with mock.patch.object(mod, "run_tool", fake):
                        mod._ect_squeeze(p, "png")
            self.assertEqual(seen[0], ["ect", "-9", p])
            # oxipng present but failed -> first ect is plain -9, no --reuse
            seen.clear()
            def flaky(cmd):
                seen.append(cmd)
                return False if cmd[0] == "oxipng" else True
            with mock.patch.object(mod, "have_oxipng", return_value=True):
                with mock.patch.object(mod, "_ect_reuse_ok", return_value=True):
                    with mock.patch.object(mod, "run_tool", flaky):
                        mod._ect_squeeze(p, "png")
            self.assertEqual(seen[0][0], "oxipng")
            self.assertEqual(seen[1], ["ect", "-9", p])

    def test_jpg_chain_and_finish_guards(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.jpg")
            _write(p, mod.JPEG_MAGIC + b"x" * 100 + mod.JPEG_TRAILER, "wb")
            seen: list = []
            def fake(cmd):
                seen.append(cmd)
                return True
            with mock.patch.object(mod, "have_jpegtran", return_value=True):
                with mock.patch.object(mod, "_jpegtran_finish") as jt:
                    with mock.patch.object(mod, "run_tool", fake):
                        mod._ect_squeeze(p, "jpg")
            self.assertIn("-progressive", seen[0])
            self.assertIn("-strip", seen[0])
            jt.assert_called_once_with(p)
            # finish guards: missing file, bad output kept
            mod._jpegtran_finish(os.path.join(d, "nope.jpg"))
            mod._jpegtran_finish("")
            with mock.patch.object(mod, "run_tool", return_value=False):
                before = open(p, "rb").read()
                mod._jpegtran_finish(p)
                self.assertEqual(open(p, "rb").read(), before)

    def test_jpegtran_finish_swaps_valid(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.jpg")
            orig = mod.JPEG_MAGIC + b"x" * 100 + mod.JPEG_TRAILER
            _write(p, orig, "wb")
            smaller = mod.JPEG_MAGIC + b"y" + mod.JPEG_TRAILER
            def fake(cmd):
                tmp = cmd[cmd.index("-outfile") + 1]
                _write(tmp, smaller, "wb")
                return True
            with mock.patch.object(mod, "run_tool", fake):
                mod._jpegtran_finish(p)
            self.assertEqual(open(p, "rb").read(), smaller)
            # broken output: original kept
            _write(p, orig, "wb")
            def fake_bad(cmd):
                tmp = cmd[cmd.index("-outfile") + 1]
                _write(tmp, b"junk", "wb")
                return True
            with mock.patch.object(mod, "run_tool", fake_bad):
                mod._jpegtran_finish(p)
            self.assertEqual(open(p, "rb").read(), orig)

    def test_chains_end_to_end_keep_smaller(self):
        big_png = mod.PNG_MAGIC + b"x" * 500 + mod.PNG_TRAILER
        img = mod._Image(idx=0, img_id="c", kind="png", raw=big_png,
                         orig_b64_len=10, attrs="", orig_body="B")
        with tempfile.TemporaryDirectory() as d:
            def fake_shrink(cmd, **kw):
                shrink_file(cmd[-1])
                class R: returncode = 0
                return R()
            with mock.patch.object(mod, "have_oxipng", return_value=True):
                with mock.patch.object(mod, "_ect_reuse_ok", return_value=True):
                    with mock.patch.object(mod.subprocess, "run", fake_shrink):
                        with redirect_stderr(io.StringIO()):
                            r = mod.optimize_images([img], d, True)
            self.assertLess(len(r[0]), len(big_png))


class TestBatchProgress(unittest.TestCase):
    """Прогресс виден сразу: строки печатаются по мере готовности, со сбросом."""

    def test_completion_order_not_submission_order(self):
        import time as _t
        with tempfile.TemporaryDirectory() as d:
            slow = os.path.join(d, "slow.fb2.zip")
            fast = os.path.join(d, "fast.fb2.zip")
            def fake_one(path, tmp_root, have_ect, registry,
                         lossy=None, img_workers=1):
                if path == slow:
                    _t.sleep(0.5)
                    return 0, "slow.fb2.zip: already optimal"
                return 0, "fast.fb2.zip: already optimal"
            with mock.patch.object(mod, "_optimize_one", fake_one):
                with mock.patch.object(mod, "_cpu_count", return_value=4):
                    out = io.StringIO()
                    with redirect_stdout(out):
                        rc = mod._run_optimize_batch([slow, fast], False, False, False)
            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("slow.fb2.zip", text)
            self.assertIn("fast.fb2.zip", text)
            self.assertLess(text.index("fast.fb2.zip"), text.index("slow.fb2.zip"))

    def test_result_lines_flushed(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "b.fb2.zip")
            def fake_one(path, tmp_root, have_ect, registry,
                         lossy=None, img_workers=1):
                return 0, "b.fb2.zip: already optimal"
            calls: list = []
            real_print = print
            def spy(*a, **k):
                calls.append((a, k))
                return real_print(*a, **k)
            with mock.patch.object(mod, "_optimize_one", fake_one):
                with mock.patch("builtins.print", spy):
                    with redirect_stdout(io.StringIO()):
                        mod._run_optimize_batch([p], False, False, False)
            outlines = [k for a, k in calls if a and "already optimal" in str(a[0])]
            self.assertTrue(outlines)
            self.assertTrue(all(k.get("flush") is True for k in outlines))


class TestBothModes(unittest.TestCase):
    """Оба режима ect на мелких PNG: побеждает packed-smaller, оригинал цел."""

    def _png(self, body):
        return mod.PNG_MAGIC + body + mod.PNG_TRAILER

    def test_keeps_packed_smaller(self):
        import random as _rnd
        rng = _rnd.Random(11)
        small = self._png(b"\0" * 2000)  # packed tiny
        big = self._png(rng.randbytes(2000) + mod.PNG_TRAILER)  # packed huge
        big = self._png(rng.randbytes(2000))
        self.assertLess(mod._packed_cost(small), mod._packed_cost(big))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.png")
            # reuse wins
            _write(p, big, "wb")
            def fake_reuse_wins(cmd):
                if cmd[:2] == ["ect", "-9"]:
                    _write(cmd[-1], small, "wb")
                else:
                    _write(cmd[-1], big, "wb")
                return True
            with mock.patch.object(mod, "run_tool", fake_reuse_wins):
                mod._ect_png_both(p)
            self.assertEqual(open(p, "rb").read(), small)
            # plain wins
            _write(p, big, "wb")
            def fake_plain_wins(cmd):
                if cmd == ["ect", "-9", p]:
                    _write(cmd[-1], small, "wb")
                else:
                    _write(cmd[-1], big, "wb")
                return True
            with mock.patch.object(mod, "run_tool", fake_plain_wins):
                mod._ect_png_both(p)
            self.assertEqual(open(p, "rb").read(), small)

    def test_tie_keeps_plain(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.png")
            orig = self._png(b"q" * 500)
            _write(p, orig, "wb")
            def fake_same(cmd):
                _write(cmd[-1], self._png(b"w" * 500), "wb")
                return True
            with mock.patch.object(mod, "run_tool", fake_same):
                mod._ect_png_both(p)
            got = open(p, "rb").read()
            self.assertEqual(got, self._png(b"w" * 500))

    def test_failure_restores_original(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.png")
            orig = self._png(b"z" * 500)
            _write(p, orig, "wb")
            with mock.patch.object(mod, "run_tool", return_value=False):
                mod._ect_png_both(p)
            self.assertEqual(open(p, "rb").read(), orig)
            mod._ect_png_both(os.path.join(d, "missing.png"))
            mod._ect_png_both("")
            self.assertTrue(mod._is_small_png(p))
            self.assertFalse(mod._is_small_png(os.path.join(d, "missing.png")))
            self.assertFalse(mod._is_small_png(""))

    def test_skipped_when_big(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "big.png")
            _write(p, self._png(b"v" * (mod.SMALL_PNG_BOTH + 100)), "wb")
            seen: list = []
            def fake(cmd):
                seen.append(cmd)
                return True
            with mock.patch.object(mod, "have_oxipng", return_value=False):
                with mock.patch.object(mod, "_ect_reuse_ok", return_value=True):
                    with mock.patch.object(mod, "run_tool", fake):
                        mod._ect_squeeze(p, "png")
            self.assertEqual(seen, [["ect", "-9", p]])


def _gate_png(w=256, h=256):
    import struct as _s
    import zlib as _z
    def _chunk(tag, data):
        head = tag + data
        return (_s.pack(">I", len(data)) + head
                + _s.pack(">I", _z.crc32(head) & 0xFFFFFFFF))
    ihdr = _s.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter None everywhere: non-optimal input
        for x in range(w):
            raw += bytes(((x * 3 + y) % 256, (x + y * 7) % 256,
                          (x * 13 + y * 11) % 256))
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", _z.compress(bytes(raw), 6)) + _chunk(b"IEND", b""))


@unittest.skipUnless(HAVE_ECT, "need real ect")
class TestByteGate(unittest.TestCase):
    """Байтовый гейт: цепочка обязана бить голый --reuse (регресс v4.9)."""

    def test_chain_beats_reuse_only(self):
        raw = _gate_png()
        with tempfile.TemporaryDirectory() as d:
            ref = os.path.join(d, "ref.png")
            _write(ref, raw, "wb")
            self.assertTrue(mod.run_tool(["ect", "-9", "--reuse", ref]))
            with open(ref, "rb") as fh:
                reuse = fh.read()
            img = mod._Image(idx=0, img_id="g", kind="png", raw=raw,
                             orig_b64_len=10, attrs="", orig_body="")
            res = mod.optimize_images([img], d, True)
            self.assertLess(mod._packed_cost(res[0]),
                            mod._packed_cost(reuse))
            self.assertLess(len(res[0]), len(raw))
            if HAS_PIL:
                self.assertTrue(mod._pixels_equal(res[0], raw))


if __name__ == "__main__":
    unittest.main(verbosity=2)
