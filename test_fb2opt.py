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
            open(p, "w").write("x")
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
            open(cmd[-1], "wb").write(b"junk")
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
            open(zp, "wb").write(b"not a zip")
            with self.assertRaises(mod.Fb2OptError):
                mod.optimize_zip_file(zp, tempfile.mkdtemp(dir=d), False, [])

    def test_pack_raw_fb2(self):
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "book.fb2")
            open(fp, "wb").write(make_fb2())
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
            open(t, "w").write("x")
            reg = [t]
            with redirect_stderr(io.StringIO()):
                mod._drop_tmp(t, reg)
            self.assertFalse(os.path.exists(t))
            self.assertEqual(reg, [])

    def test_drop_tmp_refuses_book(self):
        with tempfile.TemporaryDirectory() as d:
            book = os.path.join(d, "book.fb2.zip")
            open(book, "w").write("precious")
            reg = [book]
            err = io.StringIO()
            with redirect_stderr(err):
                mod._drop_tmp(book, reg)
            self.assertTrue(os.path.exists(book))
            self.assertEqual(open(book).read(), "precious")
            self.assertIn("refusing", err.getvalue())

    def test_drop_tmp_bad_type_safe(self):
        with redirect_stderr(io.StringIO()):
            mod._drop_tmp(None, [])
            mod._drop_tmp("", [])

    def test_sweep_cleans_only_registry(self):
        with tempfile.TemporaryDirectory() as d:
            t = os.path.join(d, ".fb2opt-s.zip")
            open(t, "w").write("x")
            book = os.path.join(d, "b.fb2.zip")
            open(book, "w").write("y")
            with redirect_stderr(io.StringIO()):
                mod._sweep_temps([t, book])
            self.assertFalse(os.path.exists(t))
            self.assertTrue(os.path.exists(book))

    def test_place_smaller_replaces(self):
        with tempfile.TemporaryDirectory() as d:
            final = os.path.join(d, "f.fb2.zip")
            open(final, "wb").write(b"1" * 100)
            tmp = os.path.join(d, ".fb2opt-n.zip")
            open(tmp, "wb").write(b"2" * 10)
            ok, _ = mod._place_if_smaller(tmp, final, 100, [tmp])
            self.assertTrue(ok)
            self.assertEqual(os.path.getsize(final), 10)

    def test_place_bigger_keeps(self):
        with tempfile.TemporaryDirectory() as d:
            final = os.path.join(d, "f.fb2.zip")
            open(final, "wb").write(b"1" * 10)
            tmp = os.path.join(d, ".fb2opt-n.zip")
            open(tmp, "wb").write(b"2" * 100)
            ok, _ = mod._place_if_smaller(tmp, final, 10, [tmp])
            self.assertFalse(ok)
            self.assertEqual(os.path.getsize(final), 10)
            self.assertFalse(os.path.exists(tmp))

    def test_place_refuses_empty(self):
        with tempfile.TemporaryDirectory() as d:
            final = os.path.join(d, "f.fb2.zip")
            open(final, "wb").write(b"1" * 10)
            tmp = os.path.join(d, ".fb2opt-n.zip")
            open(tmp, "wb").write(b"")
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
            open(p, "w").write("1")
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

            def deleting_one(path, tmp_root, have_ect, registry):
                if path == zp:
                    os.unlink(path)
                    return 0, "x: already optimal"
                return real_one(path, tmp_root, have_ect, registry)
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
            open(raw, "wb").write(make_fb2())
            self.assertEqual(mod.cmd_pack([raw], imgdir, True), 0)
            self.assertTrue(any(f.startswith("packed_") for f in os.listdir(d)))

    def test_pack_rejects_zip(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(mod.cmd_pack(["b.zip"], "/tmp", True), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
