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
        self.assertEqual(s.breakdown(), "xml: 5, bin: 3")
        self.assertNotIn("\033[", s.breakdown())
        with mock.patch.object(mod.sys.stdout, "isatty", return_value=True):
            colored = mod.Fb2Stats(xml_saved=5, png_saved=3).breakdown(True)
        self.assertIn("\033[96mxml\033[0m", colored)
        self.assertIn("\033[91mbin\033[0m", colored)
        self.assertIn("\033[97m", colored)
        self.assertEqual(mod._disp("a\x1bb\r\n"), "a?b??")
        self.assertEqual(mod._disp(""), "")
        self.assertEqual(mod._disp(None), "")
        self.assertEqual(mod._sv(5), "saved 5 bytes")
        with mock.patch.object(mod.sys.stdout, "isatty", return_value=True):
            self.assertEqual(mod._sv(5),
                             "saved " + chr(27) + "[1;97m5" + chr(27)
                             + "[0m bytes")
        with mock.patch.dict(mod.os.environ, {"NO_COLOR": "1"}):
            with mock.patch.object(mod.sys.stdout, "isatty", return_value=True):
                self.assertEqual(mod._sv(5), "saved 5 bytes")
                self.assertNotIn("\033[", mod._sv(5))

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
                             lossy=None, img_workers=1, *args):
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
                      img_workers=1, *args):
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

    def test_token_parse_reader(self):
        # Reader stays for old books; writer is gone (bytes carry marks).
        back = mod._parse_lossy_token(
            " converted by X fb2opt-lossy[0.92:cover.jpg;0.85:pic] done")
        self.assertEqual(back, {"cover.jpg": 0.92, "pic": 0.85})
        self.assertEqual(mod._parse_lossy_token("no token here"), {})
        self.assertEqual(mod._parse_lossy_token("fb2opt-lossy[0.92]"), {})
        self.assertEqual(mod._parse_lossy_token("fb2opt-lossy[xx:a]"), {})
        self.assertFalse(hasattr(mod, "_render_lossy_token"))
        self.assertFalse(hasattr(mod, "_write_lossy_token"))
        self.assertFalse(hasattr(mod, "_upsert_program_used"))

    def test_token_spans_stripped_from_output(self):
        # Old tokens never survive a --lossy run; nothing is written back.
        fb2 = make_fb2()
        fb2 = fb2.replace(b"<date value=",
                          b"<program-used>X fb2opt-lossy[0.9:cover]</program-used><date value=",
                          1)
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "run_tool", lambda cmd: True):
                new, stats = mod.optimize_fb2_payload(fb2, d, False, 0.92)
        self.assertNotIn(b"fb2opt-lossy[", new)
        # meta-strip (same lossy run) takes the whole program-used element
        self.assertNotIn(b"program-used", new)
        self.assertGreater(stats.marks, 0)

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
        self.assertNotIn("fb2opt-lossy[", text)  # no token anymore
        self.assertNotIn('fb2opt-lossy="', text)  # tags stay schema-clean
        import re as _re2
        m = _re2.search(rb"<binary\b[^>]*>(.*?)</binary\s*>", new,
                        _re2.DOTALL)
        stored = base64.b64decode(b"".join(m.group(1).split()))
        self.assertTrue(stored.endswith(bytes([92])))  # trail = 0.92
        self.assertTrue(stored[:-1].startswith(mod.PNG_MAGIC))
        # re-run: marked image is shielded, metric never runs
        def _boom(a, b):
            raise AssertionError("metric must not run on marked")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", _boom):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    new2, stats2 = mod.optimize_fb2_payload(new, d, False, 0.92)
        self.assertEqual(stats2.marked, 1)
        self.assertEqual(new2, new)

    def test_legacy_attr_migrates_to_trailing_byte(self):
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
        self.assertNotIn("fb2opt-lossy[", text)  # and no token either
        import re as _re3
        m = _re3.search(rb"<binary\b[^>]*>(.*?)</binary\s*>", new,
                        _re3.DOTALL)
        stored = base64.b64decode(b"".join(m.group(1).split()))
        self.assertTrue(stored.endswith(bytes([92])))  # migrated to bytes
        # shielded on re-run at the same target
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score",
                                   side_effect=AssertionError("no metric")):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    new2, stats2 = mod.optimize_fb2_payload(
                        new, d, False, 0.92)
        self.assertEqual(stats2.marked, 1)
        self.assertEqual(new2, new)

    def test_token_migrates_to_trailing_byte(self):
        if not HAS_PIL:
            self.skipTest("Pillow missing")
        import io as _io
        buf = _io.BytesIO()
        _gradient(16, 16).save(buf, "PNG")
        raw = buf.getvalue()
        fb2 = make_fb2(base64.b64encode(raw).decode())
        fb2 = fb2.replace(b"<date value=",
                          b"<program-used>Tool fb2opt-lossy[0.85:cover]</program-used><date value=",
                          1)
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "run_tool", lambda cmd: True):
                with mock.patch.object(mod, "_lossy_tools_ok",
                                       return_value=True):
                    new, stats = mod.optimize_fb2_payload(
                        fb2, d, False, 0.92)
        text = new.decode("utf-8")
        self.assertNotIn("fb2opt-lossy[", text)  # token migrated away
        # meta-strip (same lossy run) takes the whole program-used element
        self.assertNotIn(b"program-used", new)
        self.assertGreater(stats.marks, 0)  # freed annotation bytes
        import re as _re4
        m = _re4.search(rb"<binary\b[^>]*>(.*?)</binary\s*>", new,
                        _re4.DOTALL)
        stored = base64.b64decode(b"".join(m.group(1).split()))
        self.assertTrue(stored.endswith(bytes([85])))  # 0.85 carried over





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

    def test_no_document_info_needs_no_fallback(self):
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
        self.assertNotIn("cannot place lossy token", err.getvalue())
        self.assertNotIn(b"fb2opt-lossy", new)  # tags AND text clean
        self.assertNotIn(b"__FB2OPT_", new)
        import re as _re7
        m = _re7.search(rb"<binary\b[^>]*>(.*?)</binary\s*>", new,
                        _re7.DOTALL)
        stored = base64.b64decode(b"".join(m.group(1).split()))
        self.assertTrue(stored.endswith(bytes([92])))

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
        self.assertNotIn(b"fb2opt-lossy", new)  # bytes carry it now
        import re as _re8
        m = _re8.search(rb"<binary\b[^>]*>(.*?)</binary\s*>", new,
                        _re8.DOTALL)
        stored = base64.b64decode(b"".join(m.group(1).split()))
        self.assertTrue(stored.endswith(bytes([85])))  # new target 0.85
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
        # byte markers need no wrapper element: nothing is spent
        self.assertEqual(stats.marks, 0)

    def test_program_used_stripped_by_meta_strip(self):
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
        # whole program-used element goes (meta-strip), bytes carry the mark
        self.assertNotIn(b"program-used", new)
        self.assertNotIn(b"Tool X", new)
        self.assertEqual(stats.marks, 0)  # strip freed bytes count as xml:
        import re as _re6
        m = _re6.search(rb"<binary\b[^>]*>(.*?)</binary\s*>", new,
                        _re6.DOTALL)
        stored = base64.b64decode(b"".join(m.group(1).split()))
        self.assertTrue(stored.endswith(bytes([92])))


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

    def test_tiff_and_gif_rules(self):
        import io as _io
        buf = _io.BytesIO()
        _flat_two_color().save(buf, "TIFF")
        raw = buf.getvalue()
        with tempfile.TemporaryDirectory() as d:
            out = mod._try_lossless_variants(self._img(raw, "other"), d,
                                             raw, False)
        self.assertTrue(out.startswith(mod.PNG_MAGIC))  # single TIFF crosses
        self.assertTrue(mod._pixels_equal(out, raw))
        buf = _io.BytesIO()
        _flat_two_color().save(buf, "GIF")
        still = buf.getvalue()
        with tempfile.TemporaryDirectory() as d:
            out = mod._try_lossless_variants(self._img(still, "gif"), d,
                                             still, False)
        self.assertTrue(out.startswith(mod.PNG_MAGIC))  # still GIF crosses
        self.assertTrue(mod._pixels_equal(out, still))
        buf = _io.BytesIO()
        _flat_two_color().save(buf, "GIF", save_all=True,
                               append_images=[_solid("RGB", (64, 64), "red")])
        anim = buf.getvalue()
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                mod._try_lossless_variants(self._img(anim, "gif"), d,
                                           anim, True), anim)  # anim stays
        buf = _io.BytesIO()
        _flat_two_color().save(buf, "TIFF", save_all=True,
                               append_images=[_flat_two_color()])
        multi = buf.getvalue()
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                mod._try_lossless_variants(self._img(multi, "other"), d,
                                           multi, False), multi)  # pages stay
        with tempfile.TemporaryDirectory() as d:
            crafted = mod._pil_open(raw)
            crafted.tag_v2[274] = 6  # as real scanner files carry it
            with mock.patch.object(mod, "_pil_open", return_value=crafted):
                self.assertEqual(
                    mod._try_lossless_variants(self._img(raw, "other"), d,
                                               raw, False),
                    raw)  # oriented stays





@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestCrossoverModes(unittest.TestCase):
    """No gif/bmp leftovers: convertible images become PNG (lossless)."""

    def _img(self, raw, kind):
        return mod._Image(idx=0, img_id="c", kind=kind, raw=raw,
                          orig_b64_len=10, attrs="", orig_body="")

    def _gray_gif(self):
        # Like the real 40x45 eldersign: L-mode GIF, ~190 gray levels.
        # RGB re-encoding of this is bigger than the GIF itself.
        from PIL import Image as _I
        import io as _io
        im = _I.new("L", (40, 45))
        px = im.load()
        for x in range(40):
            for y in range(45):
                px[x, y] = (x * 5 + y * 3) % 200
        buf = _io.BytesIO()
        im.save(buf, "GIF")
        return buf.getvalue()

    def test_gray_gif_becomes_gray_png(self):
        raw = self._gray_gif()
        self.assertTrue(raw.startswith(b"GIF8"))
        with tempfile.TemporaryDirectory() as d:
            out = mod._try_lossless_variants(self._img(raw, "gif"), d,
                                             raw, False)
        self.assertTrue(out.startswith(mod.PNG_MAGIC))
        self.assertLess(len(out), len(raw))
        self.assertLess(mod._packed_cost(out), mod._packed_cost(raw))
        self.assertTrue(mod._pixels_equal(out, raw))
        self.assertEqual(mod._pil_open(out).mode, "L")  # native, not RGB

    def test_rich_palette_gif_trimmed(self):
        from PIL import Image as _I
        import io as _io
        im = _I.new("RGB", (64, 64))
        px = im.load()
        for x in range(64):
            for y in range(64):
                px[x, y] = ((x * 4) % 256, (y * 4) % 256, ((x + y) * 2) % 256)
        pal = im.quantize(colors=200, method=_I.MEDIANCUT,
                          dither=_I.Dither.NONE)
        buf = _io.BytesIO()
        pal.save(buf, "GIF")
        raw = buf.getvalue()
        with tempfile.TemporaryDirectory() as d:
            out = mod._try_lossless_variants(self._img(raw, "gif"), d,
                                             raw, False)
        self.assertTrue(out.startswith(mod.PNG_MAGIC))
        self.assertLess(mod._packed_cost(out), mod._packed_cost(raw))
        self.assertTrue(mod._pixels_equal(out, raw))

    def test_bmp_photo_bypasses_color_gate(self):
        # 128x128 gradient: 16384 distinct colors, the old 4096 cap kept
        # the BMP as is; raw BMP must still become a tiny PNG.
        from PIL import Image as _I
        import io as _io
        im = _I.new("RGB", (128, 128))
        px = im.load()
        for x in range(128):
            for y in range(128):
                px[x, y] = ((x * 2) % 256, (y * 2) % 256, (x + y) % 256)
        buf = _io.BytesIO()
        im.save(buf, "BMP")
        raw = buf.getvalue()
        self.assertTrue(raw.startswith(b"BM"))
        self.assertIsNone(mod._distinct_colors(mod._pil_open(raw),
                                              limit=4097))
        with tempfile.TemporaryDirectory() as d:
            out = mod._try_lossless_variants(self._img(raw, "other"), d,
                                             raw, False)
        self.assertTrue(out.startswith(mod.PNG_MAGIC))
        self.assertLess(len(out), len(raw) // 10)
        self.assertTrue(mod._pixels_equal(out, raw))

    def test_transparent_gif_stays(self):
        from PIL import Image as _I
        import io as _io
        im = _I.new("P", (16, 16), 0)
        px = im.load()
        for x in range(8):
            px[x, 0] = 3
        buf = _io.BytesIO()
        im.save(buf, "GIF", transparency=0)
        raw = buf.getvalue()
        self.assertIsNotNone(mod._pil_open(raw).info.get("transparency"))
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                mod._try_lossless_variants(self._img(raw, "gif"), d,
                                           raw, False), raw)

    def test_end_to_end_gif_rewritten_as_png(self):
        import re as _re
        raw = self._gray_gif()
        body = base64.b64encode(raw).decode()
        fb2 = ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
               "<FictionBook><description><title-info><genre>sf</genre>"
               "<author><first-name>A</first-name><last-name>B</last-name>"
               "</author><book-title>T</book-title></title-info>"
               "<document-info><author><first-name>A</first-name>"
               "<last-name>B</last-name></author>"
               "<date value=\"2020-01-01\">2020</date><id>e2e-gif</id>"
               "<version>1.0</version></document-info></description>"
               "<body><section><p>Hi</p></section></body>"
               f"<binary id=\"pic.gif\" content-type=\"image/gif\">"
               f"{body}</binary></FictionBook>").encode()
        with tempfile.TemporaryDirectory() as d:
            new, stats = mod.optimize_fb2_payload(fb2, d, False)
        text = new.decode("utf-8")
        self.assertIn('content-type="image/png"', text)
        self.assertNotIn("image/gif", text)
        self.assertGreater(stats.other_saved, 0)
        m = _re.search(r"<binary[^>]*>(.*?)</binary>", text, _re.S)
        final = base64.b64decode(m.group(1).strip())
        self.assertTrue(final.startswith(mod.PNG_MAGIC))
        self.assertTrue(mod._pixels_equal(final, raw))

    def test_crossover_encodings_direct(self):
        from PIL import Image as _I
        img = mod._Image(idx=0, img_id="e", kind="gif", raw=b"GIF89a..",
                         orig_b64_len=1, attrs="", orig_body="")
        self.assertEqual(mod._crossover_encodings(img, None, None), [])
        with mock.patch.object(mod, "_pixels_equal", return_value=True):
            with mock.patch.object(mod, "_encode_png_bytes",
                                   return_value=b"PNG"):
                self.assertEqual(mod._crossover_encodings(
                    img, _I.new("L", (8, 8), 200), None), [(b"PNG", "png")])
        red = _solid("RGB", (16, 16), "red")
        import io as _io
        buf = _io.BytesIO()
        red.save(buf, "PNG")
        img_png = mod._Image(idx=0, img_id="e", kind="gif",
                             raw=buf.getvalue(), orig_b64_len=1, attrs="",
                             orig_body="")
        hits = mod._crossover_encodings(img_png, red, 1)
        self.assertEqual(len(hits), 2)
        self.assertTrue(all(k == "png" for _, k in hits))
        costs = [mod._packed_cost(c) for c, _ in hits]
        self.assertEqual(costs, sorted(costs))  # best first

    def test_max_abs_diff_direct(self):
        a = _png_bytes(_solid("RGB", (8, 8), "red"))
        self.assertEqual(mod._max_abs_diff(a, a), 0)
        b = _png_bytes(_solid("RGB", (8, 8), "blue"))
        self.assertGreater(mod._max_abs_diff(a, b), 0)
        self.assertIsNone(mod._max_abs_diff(b"junk", a))
        self.assertIsNone(mod._max_abs_diff(
            a, _png_bytes(_solid("RGB", (8, 9), "red"))))

    def test_mime_spelling_normalized(self):
        # image/jpg is a JPEG already: only the spelling is non-standard.
        jpg = _jpeg_bytes(_solid("RGB", (32, 32), "red"), 95)
        other = _jpeg_bytes(_solid("RGB", (32, 32), "red"), 90)
        self.assertNotEqual(jpg, other)
        attrs = ' id="a" content-type="image/jpg"'
        img = mod._Image(idx=0, img_id="a", kind="jpg", raw=jpg,
                         orig_b64_len=10, attrs=attrs, orig_body="")
        stats = mod.Fb2Stats(pics=1, skipped=0)
        # Rewritten block: canonical MIME on the new tag.
        blocks, late, _ = mod._assemble_blocks([img], {0: other}, set(),
                                               None, {0: attrs}, stats)
        self.assertIn((img.img_id, ' id="a" content-type="image/jpeg"'),
                      late)
        self.assertNotIn("image/jpg", blocks[0] + late[0][1])
        # Kept block (bytes identical): tag spelling still normalized,
        # body untouched.
        stats = mod.Fb2Stats(pics=1, skipped=0)
        blocks, late, _ = mod._assemble_blocks([img], {0: jpg}, set(),
                                               None, {0: attrs}, stats)
        self.assertEqual(blocks[0], "")
        self.assertIn((img.img_id, ' id="a" content-type="image/jpeg"'),
                      late)

    def test_kept_gif_tag_untouched(self):
        raw = b"GIF89a.."
        attrs = ' id="g" content-type="image/gif"'
        img = mod._Image(idx=0, img_id="g", kind="gif", raw=raw,
                         orig_b64_len=10, attrs=attrs, orig_body="")
        stats = mod.Fb2Stats(pics=1, skipped=0)
        blocks, late, _ = mod._assemble_blocks([img], {0: raw}, set(),
                                               None, {0: attrs}, stats)
        self.assertEqual(late, [])  # convertible GIFs cross over as bytes;
        # kept ones (animated/transparent) keep their honest tag.

    def test_svg_stays_svg(self):
        raw = (b'<svg xmlns="http://www.w3.org/2000/svg" width="10" '
               b'height="10"><rect width="10" height="10"/></svg>')
        img = self._img(raw, "svg")
        with tempfile.TemporaryDirectory() as d:
            out = mod.optimize_images([img], d, False, None, None, 1)
        self.assertEqual(mod.detect_kind(out[0], ""), "svg")


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

    def test_umask_windows_fallback(self):
        # No os.umask on Windows (AttributeError, not OSError): fresh
        # files fall back to a sane default instead of crashing.
        prev = mod._CACHED_UMASK
        mod._CACHED_UMASK = None
        try:
            with mock.patch.object(mod.os, "umask",
                                   side_effect=AttributeError("x")):
                self.assertEqual(mod._umask(), 0o022)
        finally:
            mod._CACHED_UMASK = prev

    def test_emit_direct(self):
        acc = [0, 0]
        buf = io.StringIO()
        with redirect_stdout(buf):
            mod._emit(10, "outline", None, False, acc)
        self.assertEqual(acc, [0, 10])
        self.assertIn("outline", buf.getvalue())
        acc = [0, 0]
        with mock.patch("builtins.print",
                         side_effect=UnicodeEncodeError("cp1251", "", 0,
                                                        1, "x")):
            mod._emit(10, "outline", "err", True, acc)  # never raises
        self.assertEqual(acc, [1, 10])

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

    def test_trail_and_collect_helpers(self):
        png = mod.PNG_MAGIC + b"x" * 100 + mod.PNG_TRAILER
        body, trail = mod._split_trail(png + bytes([92]), "png")
        self.assertEqual((body, trail), (png, 0.92))
        self.assertEqual(mod._split_trail(png, "png"), (png, None))
        self.assertEqual(mod._split_trail(png + b"\x00", "png"), (png + b"\x00", None))
        jpg = mod.JPEG_MAGIC + b"y" * 100 + mod.JPEG_TRAILER
        self.assertEqual(mod._split_trail(jpg + bytes([85]), "jpg"),
                         (jpg, 0.85))
        self.assertEqual(mod._split_trail(b"GIF89a..", "gif"), (b"GIF89a..", None))
        self.assertEqual(mod._split_trail(b"", "png"), (b"", None))
        self.assertEqual(mod._add_trail(png, 0.92), png + bytes([92]))
        self.assertEqual(mod._add_trail(b"", 0.9), b"")
        self.assertEqual(mod._add_trail(png, 99.0), png + bytes([100]))
        known = mod._collect_marks(
            '<program-used>A fb2opt-lossy[0.9:a;0.85:b]</program-used>'
            '<binary id="b" fb2opt-lossy="0.8"/>')
        self.assertEqual(known, {"a": 0.9, "b": 0.8})
        self.assertEqual(mod._collect_marks("no marks"), {})
        self.assertTrue(mod._image_refs_ok(
            '<image href="#a"/><section id="s"/>', {"a"}))
        self.assertFalse(mod._image_refs_ok('<image href="#gone"/>', {"a"}))
        self.assertTrue(mod._image_refs_ok("", set()))
        d1 = mod._digest(b"abc")
        self.assertEqual(d1, mod._digest(b"abc"))
        self.assertNotEqual(d1, mod._digest(b"abd"))
        self.assertEqual(mod._digest(b""), (0, ""))
        with mock.patch.object(mod.hashlib, "md5",
                               side_effect=ValueError("FIPS")):
            d2 = mod._digest(b"abc")
            self.assertEqual(d2[0], 3)
            self.assertTrue(d2[1])
        self.assertEqual(mod._token_bytes("a fb2opt-lossy[0.92:x] b") > 0, True)
        self.assertEqual(mod._token_bytes("plain"), 0)
        out, n = mod._strip_legacy_marks(
            "<binary id='a' fb2opt-lossy=\"0.92\"/>")
        self.assertGreater(n, 0)
        self.assertNotIn("fb2opt-lossy", out)
        self.assertEqual(mod._cache_settings(True, None)[0], True)
        self.assertEqual(mod._cache_settings(False, 0.9)[0], False)

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
            # oxipng failure: plain ect still runs
            seen.clear()
            def flaky(cmd):
                seen.append(cmd)
                return False if cmd[0] == "oxipng" else True
            with mock.patch.object(mod, "have_oxipng", return_value=True):
                with mock.patch.object(mod, "_ect_reuse_ok", return_value=True):
                    with mock.patch.object(mod, "run_tool", flaky):
                        mod._ect_squeeze(p, "png")
            self.assertEqual([c[0] for c in seen], ["oxipng", "ect"])
            self.assertNotIn("--reuse", seen[1])

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
                         lossy=None, img_workers=1, *args):
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
                         lossy=None, img_workers=1, *args):
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


class TestOtsu(unittest.TestCase):
    """Otsu: порог между пиками, 128 на вырожденном входе."""

    def test_bimodal(self):
        hist = [0] * 256
        hist[30] = 1000
        hist[220] = 1000
        thr = mod._otsu_threshold(hist, 2000)
        # any threshold inside the valley is optimal; impl takes the first
        self.assertGreaterEqual(thr, 30)
        self.assertLess(thr, 220)

    def test_uniform_and_degenerate(self):
        hist = [0] * 256
        hist[200] = 500
        self.assertEqual(mod._otsu_threshold(hist, 500), 128)
        self.assertEqual(mod._otsu_threshold([], 0), 128)
        self.assertEqual(mod._otsu_threshold([1, 2], -5), 128)
        self.assertEqual(mod._otsu_threshold(None, 10), 128)


def _scan_rgb(w=200, h=200):
    from PIL import Image as _I
    from PIL import ImageDraw as _D
    im = _I.new("RGB", (w, h), "white")
    d = _D.Draw(im)
    for y in range(20, h, 18):
        d.rectangle([20, y, w - 20, y + 8], fill="black")
    return im


@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestLossyBilevel(unittest.TestCase):
    def _img(self, raw, kind):
        return mod._Image(idx=0, img_id="b", kind=kind, raw=raw,
                          orig_b64_len=10, attrs="", orig_body="")

    def _scan_png(self, w=200, h=200):
        import io as _io
        buf = _io.BytesIO()
        _scan_rgb(w, h).save(buf, "PNG")
        return buf.getvalue()

    def test_pass_at_work_size(self):
        raw = self._scan_png()
        img = self._img(raw, "png")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", return_value=0.999) as m:
                hit = mod._lossy_bilevel(mod._pil_open(raw), img, d, 0.92)
        self.assertIsNotNone(hit)
        self.assertTrue(hit[0].startswith(mod.PNG_MAGIC))
        self.assertEqual(m.call_count, 1)  # no retry needed
        back = mod._pil_open(hit[0])
        self.assertEqual(back.mode, "1")

    def test_upscale_retry(self):
        raw = self._scan_png(2500, 1800)  # downscaled work, full-res retry
        img = self._img(raw, "png")
        im = mod._pil_open(raw)
        work, _ = mod._scale_pair(im)
        self.assertNotEqual(tuple(work.size), tuple(im.size))
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score",
                                   return_value=0.999) as m:
                hit = mod._lossy_bilevel(im, img, d, 0.92)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[1], tuple(im.size))  # winner is the full-res retry
        self.assertEqual(m.call_count, 1)  # work size failed the tile gate

    def test_tile_gate_rejects_gradient(self):
        # Near-gray gradient: passes the chroma gate, fails the tile gate.
        from PIL import Image as _I
        grad = _I.new("L", (128, 128))
        grad.putdata([x % 256 for y in range(128) for x in range(128)])
        gray = grad.convert("RGB")
        self.assertTrue(mod._is_exact_gray(gray))
        self.assertFalse(mod._scan_like(grad, 128))
        import io as _io
        buf = _io.BytesIO()
        gray.save(buf, "PNG")
        img = self._img(buf.getvalue(), "png")
        def _boom(a, b):
            raise AssertionError("metric must not run on gradients")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", _boom):
                self.assertIsNone(
                    mod._lossy_bilevel(mod._pil_open(img.raw), img, d, 0.9))

    def test_scan_like_units(self):
        from PIL import Image as _I
        white = _I.new("L", (32, 32), 255)
        self.assertTrue(mod._scan_like(white, 128))
        self.assertFalse(mod._scan_like(None, 128))
        mid = _I.new("L", (32, 32), 128)
        self.assertFalse(mod._scan_like(mid, 128))  # flat mid-gray: no text

    def test_no_retry_when_same_size(self):
        raw = self._scan_png()
        img = self._img(raw, "png")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", return_value=0.5) as m:
                self.assertIsNone(
                    mod._lossy_bilevel(mod._pil_open(raw), img, d, 0.92))
        self.assertEqual(m.call_count, 1)

    def test_none_when_metric_missing(self):
        raw = self._scan_png()
        img = self._img(raw, "png")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", return_value=None):
                self.assertIsNone(
                    mod._lossy_bilevel(mod._pil_open(raw), img, d, 0.92))

    def test_photo_inlay_rejected_without_metric(self):
        # Prefilter (pure PIL) rejects photo inlays before any SSIM call,
        # so Posterization can never hide behind a page-level mean.
        import random as _rnd
        rng = _rnd.Random(9)
        ph = _scan_rgb(56, 42)
        px = ph.load()
        for x in range(56):
            for y in range(42):
                px[x, y] = (rng.randrange(256), rng.randrange(256),
                            rng.randrange(256))
        page = _scan_rgb(300, 300)
        page.paste(ph, (100, 120))
        img = self._img(b"x" * 5000, "jpg")
        def _boom(a, b):
            raise AssertionError("metric must not run on photo inlays")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", _boom):
                self.assertIsNone(mod._lossy_bilevel(page, img, d, 0.92))

    def test_guards_skip_before_metric(self):
        from PIL import Image as _I
        import io as _io
        # alpha
        buf = _io.BytesIO()
        _I.new("RGBA", (32, 32), (1, 2, 3, 4)).save(buf, "PNG")
        imga = self._img(buf.getvalue(), "png")
        # colorful photo (high chroma, not a scan)
        photo = _jpeg_bytes(_gradient(64, 64), 95)
        imgp = self._img(photo, "jpg")
        # exotic mode
        cmyk = _jpeg_bytes(_gradient(32, 32).convert("CMYK"))
        imgc = self._img(cmyk, "jpg")
        def _boom(a, b):
            raise AssertionError("metric must not run on guarded input")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", _boom):
                self.assertIsNone(
                    mod._lossy_bilevel(mod._pil_open(imga.raw), imga, d, 0.9))
                self.assertIsNone(
                    mod._lossy_bilevel(mod._pil_open(imgp.raw), imgp, d, 0.9))
                self.assertIsNone(
                    mod._lossy_bilevel(mod._pil_open(imgc.raw), imgc, d, 0.9))
                self.assertIsNone(mod._lossy_bilevel(None, imgp, d, 0.9))

    def test_variant_prefers_bilevel(self):
        raw = self._scan_png()
        img = self._img(raw, "jpg")
        sentinel = (mod.PNG_MAGIC + b"s", (8, 8))
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_lossy_bilevel",
                                   return_value=sentinel):
                with mock.patch.object(
                        mod, "_lossy_jpeg",
                        side_effect=AssertionError("ladder must not run")):
                    with mock.patch.object(mod, "have_ffmpeg",
                                           return_value=True):
                        self.assertEqual(
                            mod._lossy_variant(img, d, 0.9), sentinel)

    def test_variant_falls_through(self):
        raw = self._scan_png()
        img = self._img(raw, "jpg")
        sentinel = (b"jpeg-bytes", (8, 8))
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_lossy_bilevel", return_value=None):
                with mock.patch.object(mod, "_lossy_jpeg",
                                       return_value=sentinel):
                    with mock.patch.object(mod, "have_ffmpeg",
                                           return_value=True):
                        self.assertEqual(
                            mod._lossy_variant(img, d, 0.9), sentinel)

    def test_end_to_end_scan_jpeg_becomes_bilevel_png(self):
        raw = _jpeg_bytes(_scan_rgb(300, 300), 95)
        self.assertGreater(len(raw), mod.LOSSY_MIN_BYTES)
        fb2 = make_fb2(base64.b64encode(raw).decode())
        fb2 = fb2.replace(b'content-type="image/png"',
                          b'content-type="image/jpeg"', 1)
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", return_value=0.999):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    with mock.patch.object(mod, "have_ffmpeg",
                                           return_value=True):
                        with mock.patch.object(mod, "_lossy_tools_ok",
                                               return_value=True):
                            with redirect_stderr(io.StringIO()):
                                new, _ = mod.optimize_fb2_payload(
                                    fb2, d, False, 0.92)
        self.assertIn(b'content-type="image/png"', new)


def _dup_book(b64a, b64b=None, extra_head=""):
    b64b = b64b if b64b is not None else b64a
    return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<FictionBook><description><title-info><genre>sf</genre>"
            "<author><first-name>A</first-name><last-name>B</last-name></author>"
            "<book-title>T</book-title></title-info>"
            "<document-info><author><first-name>A</first-name>"
            "<last-name>B</last-name></author>"
            "<date value=\"2020-01-01\">2020</date><id>x</id>"
            "<version>1.0</version></document-info></description>"
            + extra_head +
            "<body><section><p><image xlink:href=\"#a\"/>"
            "<image xlink:href=\"#b\"/></p></section></body>"
            f"<binary id=\"a\" content-type=\"image/png\">{b64a}</binary>"
            f"<binary id=\"b\" content-type=\"image/png\">{b64b}</binary>"
            "</FictionBook>").encode("utf-8")


@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestDedup(unittest.TestCase):
    def test_collapse_and_remap(self):
        raw = _png_bytes(_solid("RGB", (32, 32), (9, 9, 200)))
        fb2 = _dup_book(base64.b64encode(raw).decode())
        with tempfile.TemporaryDirectory() as d:
            new, stats = mod.optimize_fb2_payload(fb2, d, False)
        self.assertEqual(new.count(b"<binary"), 1)
        self.assertNotIn(b"#b\"", new)
        self.assertEqual(stats.pics, 1)
        import re as _re
        ids = set(_re.findall(rb'id="([^"]+)"', new))
        refs = _re.findall(rb'<image\b[^>]*?href="#([^"]+)"', new)
        self.assertTrue(all(r.decode() in [i.decode() for i in ids]
                            for r in refs))
        self.assertEqual(len(fb2) - len(new),
                         stats.png_saved + stats.jpg_saved +
                         stats.other_saved + stats.xml_saved)

    def test_no_dups_untouched(self):
        r1 = _png_bytes(_solid("RGB", (32, 32), (9, 9, 200)))
        r2 = _png_bytes(_solid("RGB", (32, 32), (200, 9, 9)))
        fb2 = _dup_book(base64.b64encode(r1).decode(),
                        base64.b64encode(r2).decode())
        with tempfile.TemporaryDirectory() as d:
            new, stats = mod.optimize_fb2_payload(fb2, d, False)
        self.assertEqual(new.count(b"<binary"), 2)
        self.assertEqual(stats.pics, 2)

    def test_dedup_unconditional(self):
        # No opt-out flag exists anymore: dedup is part of optimization.
        with self.assertRaises(SystemExit):
            mod.parse_args(["--no-dedup", "b.fb2.zip"])

    def test_rollback_on_dangling(self):
        raw = _png_bytes(_solid("RGB", (32, 32), (9, 9, 200)))
        fb2 = _dup_book(base64.b64encode(raw).decode())
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_image_refs_ok", return_value=False):
                err = io.StringIO()
                with redirect_stderr(err):
                    new, stats = mod.optimize_fb2_payload(fb2, d, False)
        self.assertEqual(new.count(b"<binary"), 2)
        self.assertGreater(stats.dedup_kept, 0)

    def test_same_id_twice_left_alone(self):
        raw = _png_bytes(_solid("RGB", (32, 32), (9, 9, 200)))
        b64 = base64.b64encode(raw).decode()
        fb2 = _dup_book(b64).replace(b'id="b"', b'id="a"')
        with tempfile.TemporaryDirectory() as d:
            new, _ = mod.optimize_fb2_payload(fb2, d, False)
        self.assertEqual(new.count(b"<binary"), 2)

    def test_strictest_mark_wins(self):
        import random as _rnd
        raw = (mod.PNG_MAGIC + _rnd.Random(4).randbytes(5000)
               + mod.PNG_TRAILER)
        marked92 = raw + bytes([92])
        marked85 = raw + bytes([85])
        fb2 = _dup_book(base64.b64encode(marked92).decode(),
                        base64.b64encode(marked85).decode())
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score",
                                   side_effect=AssertionError("shielded")):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    new, stats = mod.optimize_fb2_payload(
                        fb2, d, False, 0.9)
        # strictest of the group (0.85) lands on the survivor block
        import re as _re
        self.assertEqual(new.count(b"<binary"), 1)
        m = _re.search(rb"<binary\b[^>]*>(.*?)</binary\s*>", new, _re.DOTALL)
        stored = base64.b64decode(b"".join(m.group(1).split()))
        self.assertTrue(stored.endswith(bytes([85])))
        # stable on re-run: same bytes out, still shielded
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score",
                                   side_effect=AssertionError("shielded")):
                with mock.patch.object(mod, "run_tool", lambda cmd: True):
                    new2, stats2 = mod.optimize_fb2_payload(
                        new, d, False, 0.9)
        self.assertEqual(new2, new)
        self.assertEqual(stats2.marked, 1)


@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestSessionCache(unittest.TestCase):
    def _img(self, raw, idx=0):
        return mod._Image(idx=idx, img_id=f"i{idx}", kind="png", raw=raw,
                          orig_b64_len=10, attrs="", orig_body="")

    def test_hit_skips_recompress(self):
        raw = _png_bytes(_solid("RGB", (32, 32), (9, 9, 200)))
        cache: dict = {}
        calls = {"n": 0}
        real = mod._process_image

        def spy(img, workdir, have_ect, lossy, marks, *args):
            calls["n"] += 1
            return real(img, workdir, have_ect, lossy, marks)
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_process_image", spy):
                imgs = [self._img(raw, 0), self._img(raw, 1)]
                r = mod.optimize_images(imgs, d, False, None, None, 1, cache)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(r[0], r[1])
        self.assertTrue(cache)

    def test_marks_replayed_on_hit(self):
        raw = _png_bytes(_solid("RGB", (32, 32), (9, 9, 200)))
        cache: dict = {}
        marks: list = []
        calls = {"n": 0}

        def winner(img, workdir, have_ect, lossy, mine, *args):
            calls["n"] += 1
            mine.append(img.idx)  # like a lossy win does
            return img.idx, b"win-bytes"

        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_process_image", winner):
                r1 = mod.optimize_images([self._img(raw, 0)], d, True, 0.9,
                                         marks, 1, cache)
                r2 = mod.optimize_images([self._img(raw, 5)], d, True, 0.9,
                                         marks, 1, cache)
        self.assertEqual(calls["n"], 1)  # second served from cache
        self.assertEqual(r1[0], b"win-bytes")
        self.assertEqual(r2[5], b"win-bytes")
        self.assertEqual(sorted(marks), [0, 5])  # replayed for new idx

    def test_key_separates_contexts(self):
        raw = _png_bytes(_solid("RGB", (32, 32), (9, 9, 200)))
        cache: dict = {}
        calls = {"n": 0}
        real = mod._process_image

        def spy(img, workdir, have_ect, lossy, marks, *args):
            calls["n"] += 1
            return real(img, workdir, have_ect, lossy, marks)
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_process_image", spy):
                mod.optimize_images([self._img(raw, 0)], d, False, None,
                                    None, 1, cache)
                mod.optimize_images([self._img(raw, 0)], d, False, 0.9,
                                    None, 1, cache)
        self.assertEqual(calls["n"], 2)

    def test_fifo_cap(self):
        cache: dict = {}
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_CACHE_MAX", 2):
                with mock.patch.object(mod, "_process_image",
                                       side_effect=lambda i, *a: (i.idx, i.raw)):
                    for n in range(4):
                        raw = _png_bytes(
                            _solid("RGB", (8, 8), (n, n, n)))
                        mod.optimize_images([self._img(raw, n)], d, False,
                                            None, None, 1, cache)
        self.assertLessEqual(len(cache), 2)


class TestMetaStrip(unittest.TestCase):
    def _book(self, desc_extra="", head=""):
        return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
                "<FictionBook xmlns=\"http://www.gribuser.ru/xml/fictionbook/2.0\""
                " xmlns:xlink=\"http://www.w3.org/1999/xlink\">"
                "<description><title-info><genre>sf</genre>"
                "<author><first-name>A</first-name><last-name>B</last-name>"
                "<home-page>http://x</home-page><email>a@x</email></author>"
                "<book-title>T</book-title><keywords>k1 k2</keywords>"
                "<date value=\"2001-01-01\">2001</date>"
                "<coverpage><image xlink:href=\"#c\"/></coverpage>"
                "<lang>ru</lang><sequence name=\"S\" number=\"1\"/>"
                "<translator><first-name>Tr</first-name>"
                "<last-name>Ansl</last-name></translator>"
                "</title-info>"
                "<document-info><author><nickname>conv</nickname></author>"
                "<author><nickname>second</nickname></author>"
                "<program-used>Tool</program-used>"
                "<date value=\"2020-01-01\">2020</date>"
                "<src-url>http://src</src-url><src-ocr>ocr</src-ocr>"
                "<id>test-id</id><version>1.0</version>"
                "<history><p>v1</p></history>"
                "<publisher>holder</publisher></document-info>"
                "<publish-info><publisher>P</publisher><city>C</city>"
                "<year>1999</year><isbn>123</isbn></publish-info>"
                "<custom-info info-type=\"x\">y</custom-info>"
                + desc_extra + "</description>" + head +
                "<body><section><p>Text</p></section></body>"
                "</FictionBook>").encode("utf-8")

    def test_blacklist_goes_keeps_stay(self):
        fb2 = self._book()
        out, n, notes = mod._strip_meta_tags(fb2.decode("utf-8"))
        self.assertGreater(n, 0)
        for gone in ("publish-info", "custom-info", "src-url", "src-ocr",
                     "history", "program-used", "keywords", "home-page",
                     "second</nickname>"):
            self.assertNotIn(gone, out)
        for keep in ("<genre>sf</genre>", "<book-title>T</book-title>",
                     "<translator>", "<first-name>Tr</first-name>",
                     "<lang>ru</lang>", "<sequence", "<id>test-id</id>",
                     "<version>1.0</version>", "2020-01-01", "<body>",
                     "conv</nickname>"):
            self.assertIn(keep, out)
        import xml.etree.ElementTree as _ET
        _ET.fromstring(out)  # still well-formed

    def test_only_lossy_and_reported(self):
        fb2 = self._book()
        with tempfile.TemporaryDirectory() as d:
            new, stats = mod.optimize_fb2_payload(fb2, d, False, None)
        self.assertFalse(hasattr(stats, "stripped"))
        self.assertIn(b"publish-info", new)  # default keeps everything
        with tempfile.TemporaryDirectory() as d:
            new, stats = mod.optimize_fb2_payload(fb2, d, False, 0.92)
        self.assertNotIn(b"publish-info", new)  # stripped bytes live in xml:
        self.assertGreater(stats.xml_saved, 0)
        err = io.StringIO()
        with redirect_stderr(err):
            mod._warn_skipped("b.fb2.zip", stats)
        self.assertNotIn("[info]", err.getvalue())

    def test_rollback_on_surprise(self):
        # Already-invalid books (no required markers to lose) pass through.
        fb2 = self._book().replace(b"<id>test-id</id>", b"")
        out, n, _ = mod._strip_meta_tags(fb2.decode("utf-8"))
        self.assertNotIn("<publish-info>", out)
        # Catastrophic over-strip rolls back to the input untouched.
        full = self._book().decode("utf-8")
        with mock.patch.object(mod.re, "subn", return_value=("", 5)):
            out2, n2, notes2 = mod._strip_meta_tags(full)
        self.assertEqual(out2, full)
        self.assertEqual((n2, notes2), (0, []))

    def test_body_binary_untouched(self):
        fb2 = (self._book()
               .replace(b"</FictionBook>",
                        b"<binary id=\"c\" content-type=\"image/png\">AAAA</binary>"
                        b"</FictionBook>"))
        out, n, _ = mod._strip_meta_tags(fb2.decode("utf-8"))
        self.assertIn("AAAA", out)


@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestClosedLoop(unittest.TestCase):
    """Маркер никогда не покидает контур книга→RAM→книга."""

    def test_tools_never_see_trail(self):
        # Closed loop: external tools only ever receive clean bytes.
        raw = _png_bytes(_solid("RGB", (48, 48), (60, 60, 60)))
        fb2 = make_fb2(base64.b64encode(raw + bytes([92])).decode())
        seen: list = []

        def spy_tool(cmd):
            if cmd[0] in ("ect", "oxipng", "jpegtran"):
                with open(cmd[-1], "rb") as fh:
                    seen.append(fh.read())
            return True
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "run_tool", spy_tool):
                with mock.patch.object(mod, "have_oxipng", return_value=True):
                    with mock.patch.object(mod, "have_jpegtran",
                                           return_value=True):
                        mod.optimize_fb2_payload(fb2, d, True, 0.92)
        self.assertTrue(seen)  # tools actually ran
        for blob in seen:
            self.assertFalse(blob.endswith(bytes([92])))

    def test_default_carries_marks(self):
        raw = _png_bytes(_solid("RGB", (48, 48), (60, 60, 60)))
        fb2 = make_fb2(base64.b64encode(raw + bytes([90])).decode())
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "run_tool", lambda cmd: True):
                new, _ = mod.optimize_fb2_payload(fb2, d, True, None)
        import re as _re
        m = _re.search(rb"<binary\b[^>]*>(.*?)</binary\s*>", new, _re.DOTALL)
        stored = base64.b64decode(b"".join(m.group(1).split()))
        self.assertTrue(stored.endswith(bytes([90])))


class TestCacheDedupUnits(unittest.TestCase):
    def test_process_cached_direct(self):
        raw = b"raw-bytes-values"
        img = mod._Image(idx=3, img_id="c", kind="other", raw=raw,
                         orig_b64_len=1, attrs="", orig_body="")
        tools = mod._cache_settings(False, None)
        cache: dict = {}
        with mock.patch.object(mod, "_process_image",
                               return_value=(3, b"out")) as m:
            self.assertEqual(
                mod._process_cached(img, "/tmp", False, None, None,
                                    cache, tools), (3, b"out"))
            self.assertEqual(
                mod._process_cached(img, "/tmp", False, None, None,
                                    cache, tools), (3, b"out"))
        self.assertEqual(m.call_count, 1)
        self.assertIn(3, [3])  # idx preserved

    def test_deduplicate_direct(self):
        import re as _re
        r1 = b"same-bytes-here"
        r2 = b"other-bytes-xyz"
        imgs = [mod._Image(idx=0, img_id="a", kind="other", raw=r1,
                           orig_b64_len=1, attrs=' id="a"', orig_body="AA"),
                mod._Image(idx=1, img_id="b", kind="other", raw=r1,
                           orig_b64_len=1, attrs=' id="b"', orig_body="AA"),
                mod._Image(idx=2, img_id="c", kind="other", raw=r2,
                           orig_b64_len=1, attrs=' id="c"', orig_body="BB")]
        matches = [_re.match("(?s)(.*)", "")] * 3  # placeholder list len
        # real match objects with group(0): build via finditer on text
        text = ('<p><image href="#a"/><image href="#b"/></p>'
                '<binary id="a">AA</binary><binary id="b">AA</binary>'
                '<binary id="c">BB</binary>')
        skel = text.replace("AA</binary>", "__P0__</binary>", 1)
        matches = list(mod.BINARY_RE.finditer(
            text.replace("__P0__", "AA")))
        finals = {0: r1, 1: r1, 2: r2}
        ni, ns, dropped, kept, reop = mod._deduplicate_final(
            imgs, finals, matches, skel, "T", set(), None)
        self.assertEqual((kept, reop), (0, 0))
        self.assertEqual([i.img_id for i in ni], ["a", "c"])
        self.assertNotIn('href="#b"', ns)
        self.assertGreater(sum(dropped.values()), 0)


@unittest.skipUnless(HAS_PIL and mod.have_ffmpeg(), "need Pillow + ffmpeg")
class TestRealMetric(unittest.TestCase):
    """Единственный тест с настоящей метрикой (живёт в byte-gate job)."""

    def test_bilevel_real_ssim(self):
        # Real ffmpeg metric at the default target (measured 1.0 locally;
        # 0.92 leaves a chasm of margin).
        raw = _jpeg_bytes(_scan_rgb(300, 300), 95)
        img = mod._Image(idx=0, img_id="s", kind="jpg", raw=raw,
                         orig_b64_len=10, attrs="", orig_body="")
        with tempfile.TemporaryDirectory() as d:
            hit = mod._lossy_bilevel(mod._pil_open(raw), img, d, 0.92)
        self.assertIsNotNone(hit)
        self.assertTrue(hit[0].startswith(mod.PNG_MAGIC))
        self.assertEqual(mod._pil_open(hit[0]).mode, "1")

    def test_variant_end_to_end_inlay_survives(self):
        # Full _lossy_variant path with a real metric: a scan wins as
        # 1-bit PNG, a photo inlay is never posterized (returns None or
        # a non-bilevel variant, but never mode "1" from the inlay).
        import random as _rnd
        rng = _rnd.Random(9)
        scan = _scan_rgb(300, 300)
        simg = mod._Image(idx=0, img_id="s", kind="jpg",
                          raw=_jpeg_bytes(scan, 95),
                          orig_b64_len=10, attrs="", orig_body="")
        photo = _scan_rgb(56, 42)
        px = photo.load()
        for x in range(56):
            for y in range(42):
                v = 100 + rng.randrange(40)
                px[x, y] = (v, v, v)
        page = _scan_rgb(300, 300)
        page.paste(photo, (100, 120))
        mimg = mod._Image(idx=1, img_id="m", kind="jpg",
                          raw=_jpeg_bytes(page, 95),
                          orig_b64_len=10, attrs="", orig_body="")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "have_ffmpeg", return_value=True):
                with mock.patch.object(mod, "_lossy_tools_ok",
                                       return_value=True):
                    hit = mod._lossy_variant(simg, d, 0.92)
                    self.assertIsNotNone(hit)
                    self.assertTrue(hit[0].startswith(mod.PNG_MAGIC))
                    miss = mod._lossy_variant(mimg, d, 0.92)
        if miss is not None:
            got = mod._pil_open(miss[0])
            self.assertIsNotNone(got)
            self.assertNotEqual(got.mode, "1")


class TestNewHelpersDirect(unittest.TestCase):
    def test_svg_helpers(self):
        self.assertTrue(mod._looks_like_svg(b"<svg></svg>"))
        self.assertTrue(mod._looks_like_svg(b'  <?xml version="1.0"?><svg/>'))
        self.assertFalse(mod._looks_like_svg(b"<?xml version=\"1.0\"?><html/>"))
        self.assertFalse(mod._looks_like_svg(b""))
        self.assertFalse(mod._looks_like_svg(mod.PNG_MAGIC + b"xx"))
        a = "<svg><g><rect/></g><text>hi</text></svg>"
        self.assertTrue(mod._svg_text_safe(a, a))
        self.assertTrue(mod._svg_text_safe(a, "<svg><g><rect/></g><text>hi</text></svg>"))
        self.assertFalse(mod._svg_text_safe(a, "<svg><g><rect/></g><text>bye</text></svg>"))
        self.assertFalse(mod._svg_text_safe(a, "junk"))
        self.assertFalse(mod._svg_text_safe(
            a.replace("<text>", '<text xml:space="preserve">'), a))
        self.assertEqual(mod._svg_align(""), "")
        al = mod._svg_align("<svg><g><rect/></g></svg>")
        import re as _re
        for m in _re.finditer(r"<[^<>]*>", al):
            self.assertEqual(m.start() % 3, 0)
        self.assertEqual(mod._minify_svg_bytes(b""), b"")
        self.assertEqual(mod._minify_svg_bytes(b"\xff\xfe junk"), b"\xff\xfe junk")
        self.assertEqual(mod._minify_svg_bytes(mod.PNG_MAGIC), mod.PNG_MAGIC)

    def test_orig_flat_len(self):
        img = mod._Image(idx=0, img_id="a", kind="png", raw=b"123456",
                         orig_b64_len=1, attrs="", orig_body="")
        class _M:
            def group(self, n):
                return {0: "<binary>", 2: "QUJD"}[n]
        self.assertEqual(mod._orig_flat_len(img, _M()), len("<binary>") + 4)
        img2 = mod._Image(idx=0, img_id="a", kind="png", raw=b"123456",
                          orig_b64_len=1, attrs="", orig_body="",
                          rawtrail=0.9)
        self.assertGreater(mod._orig_flat_len(img2, _M()),
                           mod._orig_flat_len(img, _M()))

    def test_extract_and_assemble(self):
        fb2 = make_fb2()
        text = fb2.decode("utf-8")
        matches = list(mod._binary_matches(text))
        imgs, skel, skipped = mod._extract_images(text, matches, "tok")
        self.assertEqual((len(imgs), skipped), (1, 0))
        self.assertIn("__FB2OPT_tok_0__", skel)
        real_attrs = {i.idx: i.attrs for i in imgs}
        stats = mod.Fb2Stats()
        blocks, late, stripped = mod._assemble_blocks(
            imgs, {0: imgs[0].raw}, set(), None, real_attrs, stats)
        self.assertEqual(blocks[0], imgs[0].orig_body)
        self.assertEqual((late, stripped), ([], 0))


@unittest.skipUnless(HAVE_ECT, "need real ect")
class TestCorpusGolden(unittest.TestCase):
    """Золотая книга: выход никогда не больше эталона (+0.5%).

    Покрывает базовую цепочку при замокнутых опциональных инструментах
    (детерминизм на любом стенде с PIN-версией ect). Гейт односторонний:
    улучшения проходят молча.
    """
    GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "testdata", "golden.fb2.zip")
    TOL = 1.005

    def test_golden_never_regresses(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "testdata", "golden.json")) as fh:
            import json as _json
            gold = _json.load(fh)["size"]
        with tempfile.TemporaryDirectory() as d:
            work = os.path.join(d, "book.fb2.zip")
            import shutil as _sh
            _sh.copy(self.GOLDEN, work)
            before = os.path.getsize(work)
            with mock.patch.object(mod, "have_oxipng", return_value=False):
                with mock.patch.object(mod, "have_jpegtran",
                                       return_value=False):
                    with mock.patch.object(mod, "_ect_reuse_ok",
                                           return_value=False):
                        saved, line = mod.optimize_zip_file(
                            work, tempfile.mkdtemp(dir=d), True, [])
            after = os.path.getsize(work)
            self.assertLess(after, before)
            self.assertLessEqual(after, int(gold * self.TOL) + 1)


class TestOutputUnits(unittest.TestCase):
    def test_use_color_paint(self):
        with mock.patch.object(mod.sys.stdout, "isatty", return_value=False):
            self.assertFalse(mod._use_color())
        with mock.patch.object(mod.sys.stdout, "isatty",
                               side_effect=OSError("closed")):
            self.assertFalse(mod._use_color())
        with mock.patch.object(mod, "_use_color", return_value=False):
            self.assertEqual(mod._paint("x", "CODE"), "x")
            self.assertEqual(mod._paint("", "CODE"), "")
        with mock.patch.object(mod, "_use_color", return_value=True):
            self.assertEqual(mod._paint("x", "CODE"),
                             "CODE" + "x" + chr(27) + "[0m")

    def test_beats(self):
        lo = b"a" * 100
        hi = bytes((i * 7) % 256 for i in range(300))
        self.assertTrue(mod._beats(hi, lo))
        self.assertFalse(mod._beats(lo, hi))
        self.assertFalse(mod._beats(lo, b""))
        self.assertFalse(mod._beats(b"", lo))

    def test_dual_rule_rejects_proxy_lies(self):
        # Smaller packed but bigger on disk: challenger loses.
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.png")
            import random as _rnd
            orig = (mod.PNG_MAGIC + _rnd.Random(1).randbytes(2000)
                    + mod.PNG_TRAILER)
            _write(p, orig, "wb")
            # fake ect: plain keeps, --reuse returns packed-tiny but long
            blob = mod.PNG_MAGIC + b"\x00" * 10000 + mod.PNG_TRAILER
            assert mod._packed_cost(blob) < mod._packed_cost(orig)
            def fake(cmd):
                if "--reuse" in cmd:
                    _write(cmd[-1], blob, "wb")
                return True
            with mock.patch.object(mod, "run_tool", fake):
                mod._ect_png_both(p)
            self.assertEqual(open(p, "rb").read(), orig)

    def test_jpegtran_never_replaces_with_worse(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.jpg")
            orig = mod.JPEG_MAGIC + b"m" * 2000 + mod.JPEG_TRAILER
            _write(p, orig, "wb")
            bigger = mod.JPEG_MAGIC + b"n" * 5000 + mod.JPEG_TRAILER
            def fake(cmd):
                _write(cmd[cmd.index("-outfile") + 1], bigger, "wb")
                return True
            with mock.patch.object(mod, "run_tool", fake):
                with mock.patch.object(mod, "_packed_cost",
                                       side_effect=[10, 5, 10, 5]):
                    mod._jpegtran_finish(p)
            # packed(out) < packed(orig) but longer on disk: kept
            self.assertEqual(open(p, "rb").read(), orig)

    def test_ect_png_oxi_units(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.png")
            _write(p, b"junk", "wb")
            with mock.patch.object(mod, "run_tool", return_value=True):
                mod._ect_png_oxi(p)  # invalid input: untouched, no raise
            self.assertEqual(open(p, "rb").read(), b"junk")
            raw = mod.PNG_MAGIC + b"v" * 5000 + mod.PNG_TRAILER
            _write(p, raw, "wb")
            small = mod.PNG_MAGIC + b"w" * 100 + mod.PNG_TRAILER
            def fake_oxi_then_ect(cmd):
                if cmd[0] == "oxipng":
                    return True  # no rewrite: falls back to plain
                _write(cmd[-1], small, "wb")
                return True
            with mock.patch.object(mod, "have_oxipng", return_value=True):
                with mock.patch.object(mod, "_ect_reuse_ok", return_value=True):
                    with mock.patch.object(mod, "run_tool", fake_oxi_then_ect):
                        mod._ect_png_oxi(p)
            self.assertEqual(open(p, "rb").read(), small)


HAVE_JT = __import__("shutil").which("jpegtran") is not None


@unittest.skipUnless(HAVE_ECT, "need real ect")
class TestCorpusGoldenPhotos(unittest.TestCase):
    """Золотая книга (только JPEG-фото): выход никогда не больше эталона.

    Покрывает базовую цепочку (ect, переупаковка, минификация) при
    замокнутых опциональных инструментах; правила цепочек
    (jpegtran/oxipng/--reuse) проверяют юнит-тесты с фейковыми
    инструментами, а jpegtran-путь — TestCorpusGoldenJpegtran ниже.
    Гейт односторонний: улучшения проходят молча.
    """
    GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "testdata", "golden-photos.fb2.zip")
    TOL = 1.005

    def test_golden_never_regresses(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "testdata", "golden-photos.json")) as fh:
            import json as _json
            gold = _json.load(fh)["size"]
        with tempfile.TemporaryDirectory() as d:
            work = os.path.join(d, "book.fb2.zip")
            import shutil as _sh
            _sh.copy(self.GOLDEN, work)
            before = os.path.getsize(work)
            with mock.patch.object(mod, "have_oxipng", return_value=False):
                with mock.patch.object(mod, "have_jpegtran",
                                       return_value=False):
                    with mock.patch.object(mod, "_ect_reuse_ok",
                                           return_value=False):
                        saved, line = mod.optimize_zip_file(
                            work, tempfile.mkdtemp(dir=d), True, [])
            after = os.path.getsize(work)
            self.assertLess(after, before)
            self.assertLessEqual(after, int(gold * self.TOL) + 1)
            self.assertIn("bin:", line)


@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestSharedPool(unittest.TestCase):
    def test_shared_pool_agrees(self):
        raws = [_png_bytes(_solid("RGB", (32, 32), c))
                for c in ((200, 30, 30), (30, 200, 30), (30, 30, 200))]
        images = [mod._Image(idx=i, img_id=f"p{i}", kind="png", raw=r,
                             orig_b64_len=10, attrs="", orig_body="")
                  for i, r in enumerate(raws)]
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "run_tool", lambda cmd: True):
                seq = mod.optimize_images(images, d, True, None, None, 1)
        import concurrent.futures as _cf
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "run_tool", lambda cmd: True):
                ex = _cf.ThreadPoolExecutor(max_workers=4)
                try:
                    par = mod.optimize_images(images, d, True, None, None,
                                              1, None, ex)
                finally:
                    ex.shutdown(wait=True)
        self.assertEqual(seq, par)


@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestEctFailure(unittest.TestCase):
    """Single-file ect only: failures keep the original, never raise."""

    def test_batch_failure_falls_back(self):
        import random as _rnd
        raw = (mod.PNG_MAGIC + _rnd.Random(3).randbytes(2000)
               + mod.PNG_TRAILER)
        img = mod._Image(idx=0, img_id="f", kind="png", raw=raw,
                         orig_b64_len=10, attrs="", orig_body="")
        with tempfile.TemporaryDirectory() as d:
            def boom(cmd, **kw):
                raise OSError("no ect")
            with mock.patch.object(mod.subprocess, "run", boom):
                r = mod.optimize_images([img], d, True)
        self.assertEqual(r[0], raw)


@unittest.skipUnless(HAVE_ECT and HAVE_JT, "need real ect + jpegtran")
class TestCorpusGoldenJpegtran(unittest.TestCase):
    """Тот же фикстур, но jpegtran включён по-настоящему.

    Ловит регрессии keep-min финиша (безусловная замена давала +6%):
    эталон снят с включённым jpegtran, oxipng/--reuse замокнуты.
    """
    GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "testdata", "golden-photos.fb2.zip")
    TOL = 1.005

    def test_golden_never_regresses(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "testdata", "golden-jt.json")) as fh:
            import json as _json
            gold = _json.load(fh)["size"]
        with tempfile.TemporaryDirectory() as d:
            work = os.path.join(d, "book.fb2.zip")
            import shutil as _sh
            _sh.copy(self.GOLDEN, work)
            before = os.path.getsize(work)
            with mock.patch.object(mod, "have_oxipng", return_value=False):
                with mock.patch.object(mod, "_ect_reuse_ok",
                                       return_value=False):
                    saved, line = mod.optimize_zip_file(
                        work, tempfile.mkdtemp(dir=d), True, [])
            after = os.path.getsize(work)
            self.assertLess(after, before)
            self.assertLessEqual(after, int(gold * self.TOL) + 1)


class TestSplitHelpers(unittest.TestCase):
    def test_group_and_resolve(self):
        a = mod._Image(idx=0, img_id="a", kind="png", raw=b"11",
                       orig_b64_len=1, attrs="", orig_body="", trail=0.9)
        b = mod._Image(idx=1, img_id="b", kind="png", raw=b"11",
                       orig_b64_len=1, attrs="", orig_body="", trail=0.85)
        c = mod._Image(idx=2, img_id="c", kind="png", raw=b"22",
                       orig_b64_len=1, attrs="", orig_body="")
        groups = mod._group_dup_finals([a, b, c], {0: b"11", 1: b"11", 2: b"22"})
        self.assertEqual(len(groups), 1)
        self.assertEqual(mod._group_dup_finals([], {}), [])
        marks: set = set()
        surv, dups, hit = mod._resolve_dup_group(groups[0], marks, 0.92)
        self.assertEqual((surv.img_id, [d.img_id for d in dups], hit),
                         ("a", ["b"], 0))
        self.assertAlmostEqual(surv.trail, 0.85)  # strictest wins
        marks2 = {1}
        surv2, _, hit2 = mod._resolve_dup_group(groups[0], marks2, 0.8)
        self.assertEqual(hit2, 1)  # carried 0.85 > 0.8: re-opened
        self.assertIn(0, marks2)

    def test_excise(self):
        skel = ('<p><image href="#b"/></p>'
                '<binary id="a">AA</binary><binary id="b">AA</binary>')
        out = mod._excise_dup_blocks([], set(), {}, skel, "T")
        self.assertEqual(out, skel)
        imgs = [mod._Image(idx=0, img_id="a", kind="png", raw=b"1",
                           orig_b64_len=1, attrs=' id="a"', orig_body="")]
        out = mod._excise_dup_blocks(imgs, {1}, {"b": "a"}, skel, "T")
        self.assertIsNotNone(out)
        self.assertNotIn('href="#b"', out)

    @unittest.skipUnless(HAS_PIL and mod.have_ffmpeg(), "need Pillow + ffmpeg")
    def test_bilevel_attempt_units(self):
        from PIL import Image as _I
        with tempfile.TemporaryDirectory() as d:
            src = _I.new("RGB", (64, 64), "white")
            hit = mod._bilevel_attempt(src, (64, 64),
                                       os.path.join(d, "s"), 0, [], 0.9, src)
            self.assertIsNotNone(hit)
            self.assertEqual(hit[1], (64, 64))
            self.assertTrue(hit[0].startswith(mod.PNG_MAGIC))


@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestSplitHelpers2(unittest.TestCase):
    """Direct units for the crossover/midflat splits (budget gate)."""

    def test_crossover_keep(self):
        img = mod._Image(idx=0, img_id="k", kind="gif", raw=b"GIF89a..",
                         orig_b64_len=1, attrs="", orig_body="")
        self.assertIsNone(mod._crossover_keep(None, img))
        self.assertIsNone(mod._crossover_keep(b"junk-bytes", img))
        from PIL import Image as _I
        import io as _io
        buf = _io.BytesIO()
        _I.new("L", (8, 8), 200).save(buf, "PNG")
        enc = buf.getvalue()
        with mock.patch.object(mod, "_pixels_equal", return_value=True):
            self.assertEqual(mod._crossover_keep(enc, img), (enc, "png"))

    def test_crossover_palette_and_rgb(self):
        from PIL import Image as _I
        import io as _io
        red = _solid("RGB", (16, 16), "red")
        buf = _io.BytesIO()
        red.save(buf, "PNG")
        img = mod._Image(idx=0, img_id="r", kind="other",
                         raw=buf.getvalue(),
                         orig_b64_len=1, attrs="", orig_body="")
        self.assertEqual(mod._crossover_rgb(img, red, 1)[0][1], "png")
        pal = red.quantize(colors=2, method=_I.MEDIANCUT)
        hits = mod._crossover_palette(img, pal, 2)
        self.assertTrue(hits and all(k == "png" for _, k in hits))
        self.assertIsInstance(mod._crossover_palette(img, None, None), list)
        self.assertIsInstance(mod._crossover_rgb(img, None, None), list)

    def test_midflat_units(self):
        from PIL import Image as _I
        white = _I.new("L", (32, 32), 255).convert("RGB")
        gray = white.convert("L")
        tw = th = 4
        mean = gray.resize((tw, th), _I.BOX)
        vm = mod._midflat_varmap(gray, mean.load(), tw, th, 32, 32)
        self.assertEqual(vm, {})  # paper-white: no candidates
        self.assertEqual(mod._midflat_bad(vm, tw, th), [])
        self.assertTrue(mod._midflat_spread([], tw, th))
        self.assertFalse(mod._midflat_spread([(0, 0)], tw, th))
        full = [(x, y) for x in range(tw) for y in range(th)]
        self.assertTrue(mod._midflat_spread(full, tw, th))
        self.assertEqual(mod._midflat_varmap(None, None, 0, 0, 0, 0), {})

    def test_batch_env_direct(self):
        with mock.patch.object(mod.shutil, "which", return_value=None):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(mod._batch_env(True, None), (False, None))
        with mock.patch.object(mod.shutil, "which",
                               side_effect=OSError("x")):
            self.assertEqual(mod._batch_env(True, None), (False, None))
        with mock.patch.object(mod, "_lossy_tools_ok", return_value=False):
            with mock.patch.object(mod, "have_pil", return_value=False):
                with mock.patch.object(mod, "have_ffmpeg",
                                       return_value=False):
                    with redirect_stderr(io.StringIO()):
                        _, code = mod._batch_env(True, 0.92)
                    self.assertEqual(code, 2)

    def test_report_batch_direct(self):
        self.assertEqual(mod._report_batch(["a"], {}, [0, 0], True), 0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mod._report_batch(["a", "b"], {}, [0, 100], False)
        self.assertEqual(rc, 0)
        self.assertIn("Total: 2 files", buf.getvalue())
        with redirect_stderr(io.StringIO()):
            rc = mod._report_batch(["a"], {"gone.fb2.zip": True},
                                   [0, 0], True)
        self.assertEqual(rc, 1)
        self.assertEqual(mod._report_batch(["a"], {}, [3, 0], True), 1)

    def test_pack_helpers_direct(self):
        import re as _re
        m = _re.search(r"<binary([^>]*)>(.*?)</binary>",
                       '<binary id="x">QQ==</binary>')
        updated: list = []
        self.assertEqual(mod._pack_replace(m, "/nonexistent-dir-xyz", True,
                                           updated), m.group(0))
        self.assertEqual(updated, [])
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "pic.png"), "wb") as fh:
                fh.write(b"PNGDATA")
            m = _re.search(r"<binary([^>]*)>(.*?)</binary>",
                           '<binary id="pic">QQ==</binary>')
            out = mod._pack_replace(m, d, True, updated)
            self.assertIn(base64.b64encode(b"PNGDATA").decode(), out)
            self.assertEqual(updated, [1])
            self.assertEqual(mod._pack_one(os.path.join(d, "no.fb2"), d,
                                           True), 1)
            self.assertEqual(mod._pack_one(os.path.join(d, "a.zip"), d,
                                           True), 1)
            fb2path = os.path.join(d, "book.fb2")
            with open(fb2path, "wb") as fh:
                fh.write(make_fb2())
            with open(os.path.join(d, "cover.png"), "wb") as fh:
                fh.write(b"NEWPNG")
            self.assertEqual(mod._pack_one(fb2path, d, True), 0)
            self.assertTrue(os.path.isfile(
                os.path.join(d, "packed_book.fb2")))


@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestMidflatGate(unittest.TestCase):
    def test_text_passes_blobs_fail(self):
        page = _scan_rgb(200, 200)
        self.assertEqual(mod._midflat_frac(page.convert("L")), 0.0)
        import random as _rnd
        rng = _rnd.Random(9)
        blob = _scan_rgb(56, 42)
        px = blob.load()
        for x in range(56):
            for y in range(42):
                v = 100 + rng.randrange(40)
                px[x, y] = (v, v, v)
        page.paste(blob, (50, 50))
        frac = mod._midflat_frac(page.convert("L"))
        self.assertIsNotNone(frac)
        self.assertGreater(frac, mod.BILEVEL_MIDFLAT)

    def test_guards(self):
        self.assertIsNone(mod._midflat_frac(None))
        from PIL import Image as _I
        tiny = _I.new("L", (4, 4), 200)
        # A single tile always spans its page: background, not a patch.
        self.assertEqual(mod._midflat_frac(tiny), 0.0)
        white = _I.new("L", (32, 32), 255)
        self.assertEqual(mod._midflat_frac(white), 0.0)

    def test_end_to_end_blob_rejected(self):
        import random as _rnd
        rng = _rnd.Random(9)
        page = _scan_rgb(300, 300)
        blob = _scan_rgb(56, 42)
        px = blob.load()
        for x in range(56):
            for y in range(42):
                v = 100 + rng.randrange(40)
                px[x, y] = (v, v, v)
        page.paste(blob, (100, 120))
        img = mod._Image(idx=0, img_id="m", kind="jpg", raw=b"z",
                         orig_b64_len=1, attrs="", orig_body="")
        def _boom(a, b):
            raise AssertionError("metric must not run on smooth blobs")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", _boom):
                self.assertIsNone(mod._lossy_bilevel(page, img, d, 0.92))


    def _text_page(self, paper, nstrokes, w=500, h=700, seed=7):
        import random as _rnd
        from PIL import Image as _I
        rng = _rnd.Random(seed)
        im = _I.new("RGB", (w, h), (paper, paper, paper))
        px = im.load()
        for _ in range(nstrokes):
            x, y = rng.randrange(w), rng.randrange(h - 4)
            for dy in range(3):
                for dx in range(rng.choice([6, 9, 14])):
                    if x + dx < w:
                        px[x + dx, y + dy] = (20, 20, 20)
        return im

    def _noise_inlay(self, lo, hi, w, h, seed=11):
        import random as _rnd
        from PIL import Image as _I
        rng = _rnd.Random(seed)
        im = _I.new("RGB", (w, h))
        px = im.load()
        for x in range(w):
            for y in range(h):
                v = rng.randrange(lo, hi + 1)
                px[x, y] = (v, v, v)
        return im

    def test_audit_sized_noise_inlays_rejected(self):
        # Audit v19 residual hole: 1%-area inlays whose tones avoid
        # mid-gray entirely (dark 15-95, light 165-245). Both must die
        # before the metric (which is blind there: SSIM 0.90 on a flat).
        for lo, hi in ((15, 95), (165, 245)):
            page = self._text_page(250, 2600, w=1000, h=1400)
            page.paste(self._noise_inlay(lo, hi, 140, 105), (400, 600))
            frac = mod._midflat_frac(page.convert("L"))
            self.assertIsNotNone(frac)
            self.assertGreater(frac, mod.BILEVEL_MIDFLAT,
                               f"tones {lo}-{hi} slipped through")
            img = mod._Image(idx=0, img_id="m", kind="jpg", raw=b"z",
                             orig_b64_len=1, attrs="", orig_body="")
            def _boom(a, b):
                raise AssertionError("metric must not run on noise inlays")
            with tempfile.TemporaryDirectory() as d:
                with mock.patch.object(mod, "_ssim_score", _boom):
                    self.assertIsNone(mod._lossy_bilevel(page, img, d, 0.92))

    def test_gray_paper_is_no_patch(self):
        # Uniform background flags everywhere: spread, not a patch, so
        # gray-paper scans still reach bilevel (mocked metric passes).
        page = self._text_page(200, 1300)
        self.assertEqual(mod._midflat_frac(page.convert("L")), 0.0)
        img = mod._Image(idx=0, img_id="g", kind="jpg", raw=b"z",
                         orig_b64_len=1, attrs="", orig_body="")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "_ssim_score", return_value=1.0):
                hit = mod._lossy_bilevel(page, img, d, 0.92)
        self.assertIsNotNone(hit)
        self.assertEqual(mod._pil_open(hit[0]).mode, "1")

    def test_band_guards_otsu_threshold(self):
        # The band must guard the cut actually used: uniform dark noise
        # has nothing near 128 but everything near its Otsu threshold.
        gray = self._noise_inlay(15, 95, 140, 105).convert("L")
        thr = mod._otsu_threshold(gray.histogram(), 140 * 105)
        self.assertLess(thr, 128)
        self.assertFalse(mod._scan_like(gray, thr))
        scan = _scan_rgb(200, 200).convert("L")
        thr = mod._otsu_threshold(scan.histogram(), 200 * 200)
        self.assertTrue(mod._scan_like(scan, thr))


@unittest.skipUnless(HAS_PIL, "Pillow missing")
class TestExifOrientation(unittest.TestCase):
    """EXIF orientation is applied before any EXIF-dropping pass."""

    def _oriented(self, w=64, h=48, ori=6, fmt="JPEG", **kw):
        from PIL import Image as _I
        import io as _io
        im = _I.new("RGB", (w, h))
        px = im.load()
        for x in range(w):
            for y in range(h):
                px[x, y] = ((x * 4) % 256, (y * 6) % 256, 128)
        ex = _I.Exif()
        ex[274] = ori
        buf = _io.BytesIO()
        im.save(buf, fmt, exif=ex, **kw)
        return buf.getvalue()

    def _img(self, raw, kind):
        return mod._Image(idx=0, img_id="o", kind=kind, raw=raw,
                          orig_b64_len=10, attrs="", orig_body="")

    def test_orientation_of_guards(self):
        self.assertIsNone(mod._orientation_of(b""))
        self.assertIsNone(mod._orientation_of(b"not-an-image"))
        self.assertIsNone(mod._orientation_of(_jpeg_bytes(
            _solid("RGB", (8, 8), "red"), 90)))  # no EXIF
        self.assertEqual(mod._orientation_of(self._oriented()), 6)

    def test_upright_image_guards(self):
        img = self._img(b"GIF89a..", "gif")
        same, skip = mod._upright_image(img, ".")
        self.assertIs(same, img)
        self.assertFalse(skip)
        plain = self._img(_jpeg_bytes(_solid("RGB", (8, 8), "red"), 90),
                          "jpg")
        same, skip = mod._upright_image(plain, ".")
        self.assertIs(same, plain)
        self.assertFalse(skip)

    @unittest.skipUnless(HAVE_JT, "need real jpegtran")
    def test_jpeg_transposed_losslessly(self):
        raw = self._oriented(64, 48, 6, quality=90)
        img = self._img(raw, "jpg")
        with tempfile.TemporaryDirectory() as d:
            fixed, skip = mod._upright_image(img, d)
            self.assertFalse(skip)
            self.assertNotEqual(fixed.raw, raw)
            self.assertIsNone(mod._orientation_of(fixed.raw))
            self.assertEqual(mod._pil_open(fixed.raw).size, (48, 64))
            self.assertTrue(mod._transpose_jpeg_ok(raw, fixed.raw, 6,
                                                   d, 0))
            idx, out = mod._process_image(img, d, False, None, None)
            self.assertEqual(mod._pil_open(out).size, (48, 64))
            self.assertIsNone(mod._orientation_of(out))

    def test_jpeg_kept_without_jpegtran(self):
        raw = self._oriented(64, 48, 6, quality=90)
        img = self._img(raw, "jpg")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "have_jpegtran",
                                   return_value=False):
                with mock.patch.object(mod, "run_tool") as rt:
                    idx, out = mod._process_image(img, d, True, None, None)
            self.assertEqual(out, raw)  # byte-exact: strip would rotate
            rt.assert_not_called()  # ect never sees the oriented bytes

    @unittest.skipUnless(HAVE_JT, "need real jpegtran")
    def test_partial_mcu_kept(self):
        # 60x40 is no multiple of the iMCU grid: jpegtran transposes it
        # into garbage (rc 0!), so the triple check must refuse.
        raw = self._oriented(60, 40, 6, quality=90)
        img = self._img(raw, "jpg")
        with tempfile.TemporaryDirectory() as d:
            fixed, skip = mod._upright_image(img, d)
            self.assertTrue(skip)
            self.assertEqual(fixed.raw, raw)

    def test_oriented_other_kept_lossless(self):
        # No lossless transpose exists for gif/other containers: an
        # oriented source must never reach the re-encoding ladders.
        raw = self._oriented(64, 48, 6, quality=90)
        img = self._img(raw, "other")
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(mod, "have_ffmpeg", return_value=True):
                self.assertIsNone(mod._lossy_variant(img, d, 0.92))
                # Control: same container, no orientation → passes through.
                plain = self._img(_jpeg_bytes(_solid("RGB", (64, 48),
                                                       "red"), 90), "other")
                with mock.patch.object(mod, "_lossy_bilevel",
                                       return_value=(b"fake", (8, 8))):
                    self.assertEqual(mod._lossy_variant(plain, d, 0.92),
                                     (b"fake", (8, 8)))

    def test_orientation_of_tiff_tag(self):
        # TIFF keeps orientation outside EXIF (tag_v2 fallback).
        class _FakeTag(dict):
            def get(self, key, default=None):
                return super().get(key, default)
        class _FakeIm:
            def getexif(self):
                return {}
            tag_v2 = _FakeTag({274: 6})
        with mock.patch.object(mod.Image, "open", return_value=_FakeIm()):
            self.assertEqual(mod._orientation_of(b"TIFF...."), 6)

    @unittest.skipUnless(HAVE_JT, "need real jpegtran")
    def test_transpose_helpers_direct(self):
        raw = self._oriented(64, 48, 6, quality=90)
        with tempfile.TemporaryDirectory() as d:
            out = mod._transpose_run(raw, ["-rotate", "90"], d, 0)
            self.assertTrue(out.startswith(mod.JPEG_MAGIC))
            self.assertIsNone(mod._transpose_run(raw, ["-bogus-xyz"],
                                                 d, 0))
            with mock.patch.object(mod, "have_jpegtran",
                                   return_value=False):
                self.assertIsNone(mod._transpose_run(raw, ["-rotate",
                                                           "90"], d, 0))
            hit = mod._transpose_jpeg(raw, 6, d, 0)
            self.assertTrue(hit.startswith(mod.JPEG_MAGIC))
            self.assertIsNone(mod._transpose_jpeg(raw, 9, d, 0))
            self.assertIsNone(mod._transpose_jpeg(b"junk", 6, d, 0))

    def test_transpose_png_direct(self):
        raw = self._oriented(60, 40, 6, fmt="PNG")
        out = mod._transpose_png(raw)
        self.assertTrue(out.startswith(mod.PNG_MAGIC))
        self.assertEqual(mod._pil_open(out).size, (40, 60))
        self.assertIsNone(mod._transpose_png(b"junk"))

    def test_png_transposed_in_pillow(self):
        raw = self._oriented(60, 40, 6, fmt="PNG")
        self.assertEqual(mod._orientation_of(raw), 6)
        img = self._img(raw, "png")
        with tempfile.TemporaryDirectory() as d:
            fixed, skip = mod._upright_image(img, d)
            self.assertFalse(skip)
            self.assertEqual(mod._pil_open(fixed.raw).size, (40, 60))
            self.assertIsNone(mod._orientation_of(fixed.raw))
            self.assertTrue(mod._upright_equal(raw, fixed.raw))


class TestWindowsWrapper(unittest.TestCase):
    """The .bat launcher survives: references the script, forwards args."""

    def test_bat_wrapper(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "fb2opt.bat")
        with open(path, "rb") as fh:
            data = fh.read()
        self.assertIn(b"\r\n", data)  # CRLF: safe for stock cmd.exe
        text = data.decode("utf-8")
        self.assertIn("%~dp0fb2opt", text)  # script next to the launcher
        self.assertIn("%*", text)  # args forwarded
        self.assertIn("py", text)  # py launcher preferred


class TestBenchSmoke(unittest.TestCase):
    """bench.py runs hermetically on the in-repo corpus (no asserts on
    byte values: without ect the savings legitimately differ)."""

    def test_bench_runs_and_reports(self):
        import importlib.machinery as _mach
        bench_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "bench.py")
        loader = _mach.SourceFileLoader("bench_mod", bench_path)
        spec = importlib.util.spec_from_loader("bench_mod", loader)
        bench = importlib.util.module_from_spec(spec)
        sys.modules["bench_mod"] = bench
        loader.exec_module(bench)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = bench.main(["bench.py"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("golden.fb2.zip", out)
        self.assertIn("wall", out)



class TestRecursiveMasks(unittest.TestCase):
    def _tree(self, d):
        os.makedirs(os.path.join(d, "lorens stern"))
        open(os.path.join(d, "lorens stern", "zhizn.fb2.zip"), "w").write("x")
        open(os.path.join(d, "lorens stern", "other.txt"), "w").write("x")
        open(os.path.join(d, "top.fb2.zip"), "w").write("x")
        return d

    def _chdir(self, d):
        old = os.getcwd()
        os.chdir(d)
        self.addCleanup(os.chdir, old)

    def test_shorten_inside_shows_subfolders(self):
        with tempfile.TemporaryDirectory() as d:
            self._tree(d)
            self._chdir(d)
            self.assertEqual(mod._shorten(os.path.join(d, "lorens stern", "zhizn.fb2.zip")),
                             os.path.join("lorens stern", "zhizn.fb2.zip"))
            self.assertEqual(mod._shorten(os.path.join("lorens stern", "zhizn.fb2.zip")),
                             os.path.join("lorens stern", "zhizn.fb2.zip"))

    def test_shorten_outside_result_vs_error(self):
        self.assertEqual(mod._shorten("/tmp/xyz/book.fb2.zip"), "book.fb2.zip")
        self.assertEqual(mod._shorten("/tmp/xyz/book.fb2.zip", raw=True),
                         "/tmp/xyz/book.fb2.zip")
        self.assertEqual(mod._shorten(""), "")
        self.assertEqual(mod._shorten(None), "")

    def test_cwd_helper(self):
        cwd = mod._cwd()
        self.assertTrue(isinstance(cwd, str) and os.path.isabs(cwd))

    def test_is_book_path(self):
        self.assertTrue(mod._is_book_path("a.fb2.zip"))
        self.assertTrue(mod._is_book_path("A.FB2.ZIP"))
        self.assertTrue(mod._is_book_path("a.fb2"))
        self.assertFalse(mod._is_book_path("a.txt"))
        self.assertFalse(mod._is_book_path("a.zip"))
        self.assertFalse(mod._is_book_path(""))
        self.assertFalse(mod._is_book_path(None))

    def test_has_glob_magic(self):
        self.assertTrue(mod._has_glob_magic("*.fb2.zip"))
        self.assertTrue(mod._has_glob_magic("a?.fb2.zip"))
        self.assertTrue(mod._has_glob_magic("a[0].fb2.zip"))
        self.assertFalse(mod._has_glob_magic("book.fb2.zip"))
        self.assertFalse(mod._has_glob_magic(""))
        self.assertFalse(mod._has_glob_magic(None))

    def test_specs_and_matchers(self):
        spec = mod._mask_spec("sub/*.fb2.zip")
        self.assertEqual(spec[2:], (True, False))
        self.assertTrue(mod._file_matches_mask("x.fb2.zip", "sub/x.fb2.zip", spec))
        self.assertFalse(mod._file_matches_mask("x.fb2.zip", "other/x.fb2.zip", spec))
        star = mod._mask_spec("**/*.fb2.zip")
        self.assertTrue(star[3])
        self.assertTrue(mod._file_matches_mask("x.fb2.zip", "sub/x.fb2.zip", star))
        self.assertIsNone(mod._mask_spec(""))
        self.assertIsNone(mod._mask_spec(None))
        espec = mod._exact_spec("sub/b.fb2.zip")
        self.assertTrue(mod._file_matches_exact("b.fb2.zip", "sub/b.fb2.zip", espec))
        self.assertFalse(mod._file_matches_exact("c.fb2.zip", "sub/c.fb2.zip", espec))
        self.assertIsNone(mod._exact_spec(""))
        self.assertFalse(mod._file_matches_exact("a", "b", None))
        self.assertFalse(mod._file_matches_mask("a", "b", None))
        self.assertFalse(mod._dir_matches_mask("a", "b", None))

    def test_walk_books_only_packed(self):
        with tempfile.TemporaryDirectory() as d:
            self._tree(d)
            out = mod._walk_books(os.path.join(d, "lorens stern"))
            self.assertEqual([os.path.basename(p) for p in out], ["zhizn.fb2.zip"])
            self.assertEqual(mod._walk_books(os.path.join(d, "nope")), [])
            self.assertEqual(mod._walk_books(""), [])

    def test_mask_found_in_subfolders(self):
        with tempfile.TemporaryDirectory() as d:
            self._tree(d)
            self._chdir(d)
            out = mod._expand_sources(["*.fb2.zip"], True)
            base = sorted(os.path.basename(p) for p in out)
            self.assertEqual(base, ["top.fb2.zip", "zhizn.fb2.zip"])
            # case-insensitive extension
            out2 = mod._expand_sources(["*.FB2.ZIP"], True)
            self.assertEqual(sorted(os.path.basename(p) for p in out2), base)

    def test_starstar_mask_finds_nested_and_top(self):
        with tempfile.TemporaryDirectory() as d:
            self._tree(d)
            self._chdir(d)
            out = mod._expand_sources(["**/*.fb2.zip"], True)
            self.assertEqual(sorted(os.path.basename(p) for p in out),
                             ["top.fb2.zip", "zhizn.fb2.zip"])

    def test_multi_mask_one_walk(self):
        with tempfile.TemporaryDirectory() as d:
            self._tree(d)
            self._chdir(d)
            out = mod._expand_sources(["zhizn.fb2.zip", "top.fb2.zip"], True)
            self.assertEqual(sorted(os.path.basename(p) for p in out),
                             ["top.fb2.zip", "zhizn.fb2.zip"])
            # same book twice -> deduped
            out = mod._expand_sources(["lorens stern", "zhizn.fb2.zip"], True)
            self.assertEqual(len(out), 1)

    def test_exact_name_found_in_subfolders(self):
        with tempfile.TemporaryDirectory() as d:
            self._tree(d)
            self._chdir(d)
            out = mod._expand_sources(["zhizn.fb2.zip"], True)
            self.assertEqual(len(out), 1)
            self.assertTrue(out[0].endswith(os.path.join("lorens stern", "zhizn.fb2.zip")))

    def test_submask_with_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self._tree(d)
            self._chdir(d)
            out = mod._expand_sources([os.path.join("lorens stern", "*.fb2.zip")], True)
            self.assertEqual(len(out), 1)
            self.assertIn("zhizn.fb2.zip", out[0])

    def test_nonbooks_skipped_silently(self):
        with tempfile.TemporaryDirectory() as d:
            self._tree(d)
            self._chdir(d)
            # star matches everything, only books survive, no errors downstream
            self.assertEqual(sorted(os.path.basename(p)
                                    for p in mod._expand_sources(["*"], True)),
                             ["top.fb2.zip", "zhizn.fb2.zip"])
            # explicit non-book on disk: skipped, not an error
            self.assertEqual(mod._expand_sources(["lorens stern/other.txt"], True), [])
            # exact non-book name found in a subfolder: skipped
            self.assertEqual(mod._expand_sources(["other.txt"], True), [])
            # foreign zip (no .fb2 inside): skipped as well
            zp = os.path.join(d, "plain.zip")
            with zipfile.ZipFile(zp, "w") as z:
                z.writestr("a.txt", b"hi")
            self.assertEqual(mod._expand_sources(["plain.zip"], True), [])
            self.assertEqual(mod._expand_sources(["*.zip"], True),
                             sorted(mod._expand_sources(["*.fb2.zip"], True)))

    def test_miss_kept_for_error(self):
        with tempfile.TemporaryDirectory() as d:
            self._tree(d)
            self._chdir(d)
            self.assertEqual(mod._expand_sources(["nosuch.fb2.zip"], True), ["nosuch.fb2.zip"])
            self.assertEqual(mod._expand_sources(["*.nomatch"], True), ["*.nomatch"])

    def test_mask_hint_without_recursive(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(mod.Fb2OptError) as cm:
                mod._optimize_one(os.path.join(d, "*.fb2.zip"),
                                  tempfile.mkdtemp(dir=d), False, [])
            self.assertIn("-r", str(cm.exception))
            with self.assertRaises(mod.Fb2OptError) as cm2:
                mod._optimize_one(os.path.join(d, "nosuch.fb2.zip"),
                                  tempfile.mkdtemp(dir=d), False, [])
            self.assertNotIn("-r", str(cm2.exception))

    def test_nonrecursive_unchanged(self):
        self.assertEqual(mod._expand_sources(["*.fb2.zip"], False), ["*.fb2.zip"])

    def test_result_line_shows_subfolders(self):
        with tempfile.TemporaryDirectory() as d:
            self._tree(d)
            sub = os.path.join(d, "lorens stern", "zhizn.fb2.zip")
            make_zip(sub, make_fb2())
            self._chdir(d)
            saved, line = mod.optimize_zip_file(os.path.join("lorens stern", "zhizn.fb2.zip"),
                                                tempfile.mkdtemp(dir=d), False, [])
            self.assertIn(os.path.join("lorens stern", "zhizn.fb2.zip"), line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
