# Аудит fb2opt — исчерпывающий отчёт

- Дата: 2026-09-11
- Объект: `fb2opt` (2220 строк, один файл, Python3 stdlib + опц. Pillow/ect/ffmpeg), `test_fb2opt.py` (1699 строк, 113 тестов), `README.md`, `.github/workflows/ci.yml`
- Контракт: Supervisor → Architect → Coder → Auditor; чек-лист §1–§6
- Метод: ручной разбор всего `fb2opt`, прогон `python3 test_fb2opt.py` (113 OK), `py_compile` OK, статический поиск `def` (81 функция) vs покрытие `mod.*` в тестах, проверка `doc/roadmap.md` (отсутствует), анализ потоков/темпов/subprocess/ZIP/Pillow/regex.

**Вердикт: [REJECTED] (первичный аудит; см. Перепроверку ниже — [APPROVED])**

Причины отказа (блокеры контракта, первичный аудит):
1. §5 ТЕСТЫ — нет прямых юнит-тестов для ~18 функций (требование чек-листа «для каждой функции»).
2. §6 ROADMAP — `doc/roadmap.md` отсутствует, сверить реализацию со спецификацией невозможно; `doc/` вообще не существовал до этого аудита.

Критических RCE/инъекций нет (все `subprocess` — списком без `shell=True`), замена файла атомарна (`os.replace`), темпы чистятся через реестр. Ниже — всё, что must-fix перед APPROVED, плюс Warning/Opt.

---

## 1. ПАМЯТЬ И РЕСУРСЫ — утечки, дескрипторы, OOM

Python исключает double-free/use-after-free как класс. Явных утечек FD нет:
`mkstemp` → `os.close(handle)` (`_write_candidate:1529-1531`), все `open` — через `with`, темпы — через `registry` + `_drop_tmp` + `_sweep_temps` (1466-1503, 2197), `ThreadPoolExecutor.shutdown` корректен (2182), `_drop_paths`/`finally: unlink` в `_squeeze_candidate:961-965`, `_try_lossy:1319-1322`, `_jpeg_ladder:1134-1135`, `_lossy_png:1249-1250`.

Что не так — держат память/CPU без лимитов (DoS на враждебном входе):

| Блок кода | Тип | Описание | Как исправить |
|---|---|---|---|
| `optimize_zip_file:1721-1723`, `_restore_member_comments:1578-1579`, `optimize_fb2_payload:1344-1382` | Warning | Весь ZIP/FB2 + все картинки держатся в RAM (`members=[(info, zin.read(...))]`, `blob=fh.read()`, `images+blocks+new_skeleton` ~3× от размера книги). README честно пишет «holds several books in RAM», но враждебный ZIP (zip-bomb, 500 МБ FB2) = OOM. Нет лимита размера/числа членов. | Ввести лимиты: `MAX_ARCHIVE_BYTES`, `MAX_MEMBER_BYTES`, `MAX_MEMBERS`; при превышении — `Fb2OptError("archive too large")`. Для `_restore_member_comments` работать через `mmap` или потоково, либо отказ при `len(blob) > LIMIT`. Документировать в README. |
| `_pil_open:1006-1015` | Warning | `Image.open+load` без лимитов. Pillow по умолчанию только warns (`DecompressionBombWarning`), гигантский PNG (100k×100k) роняет процесс. | Перед `load` проверять `Image.MAX_IMAGE_PIXELS` (оставить дефолт), перехватывать `Image.DecompressionBombError/Warning` → вернуть `None` (keep original). Добавить тест. |
| `_umask:1505-1509` + `_fresh_info:1512-1521` + `optimize_fb2_file:1788` | Крит | `os.umask` — process-global. `_umask(){mask=os.umask(0); os.umask(mask)}` в пуле `file_workers>1` (2148) гоняет глобальное состояние: поток A ставит 0, поток B читает/ставит, итог — неверные права на свежих ZIP + окно с `umask 0`. Классический race. | Вычислить `umask` один раз в `main`/начале батча и передавать параметром; либо `threading.Lock` вокруг `os.umask` пары; либо вообще убрать `_umask()` и использовать `0o644`/`0o600` фиксированно. Добавить тест на многопоточный `optimize_fb2_file`. |
| `registry: list[str]` в `_run_optimize_batch:2140` + `_write_candidate:1534` / `_drop_tmp:1481-1488` | Warning | Общий `list` без лока между потоками (`_one` → append/remove конкурентно). В CPython `append` атомарен, `remove` + `list(registry)` в `_sweep_temps` — нет; возможен `ValueError` (погашен) или пропуск очистки. | Обернуть `registry` в `threading.Lock` или `queue.Queue`; либо per-thread реестр + merge в конце. |
| `img_workdir=os.path.join(tmp_root,"img")` + `optimize_images:453` `makedirs(exist_ok=True)` | Opt | При `file_workers>1` каждый файл имеет свой `per_file_tmp` (`_optimize_one:1843`) — коллизий нет. Но `stem=lossy_{idx}` общий для `_jpeg_ladder` и `_lossy_png` кроссовера внутри одного потока — сейчас последовательно, безопасно. Хрупко при будущем рефакторинге. | Добавить суффикс потока/уникальный `uuid` к `stem` или `TemporaryDirectory` на изображение; задокументировать инвариант «один idx — один поток». |

---

## 2. БЕЗОПАСНОСТЬ — overflow, race, UB, инъекции

Командных инъекций нет: `run_tool(["ect",...])`, `["ect","-9","-zip",tmp]`, `["ffmpeg",...]` — всё списком, `shell=False`, `timeout` задан (`TOOL_TIMEOUT=600`, `SSIM_TIMEOUT=120`), `run_tool`/`_ssim_score` никогда не бросают (`except OSError, SubprocessError`). `os.replace` атомарен, `_place_if_smaller:1670-1705` отказывается ставить пустой/не-меньший файл и сверяет размер после установки. `_verify_candidate:1635-1651` проверяет `testzip` + `namelist` после каждого `ect`. `_clone_info` сохраняет даты/права/комменты. Симлинки скипаются (`_optimize_one:1838-1839`), удаление только `.fb2opt-*.zip` (`_drop_tmp:1473`).

| Блок кода | Тип | Описание | Как исправить |
|---|---|---|---|
| `_find_replacement:1951-1967` (`cmd_pack`) | Warning (почти Крит, но эксплуатация локальная) | Path traversal: `img_id` берётся из враждебного FB2, `os.path.join(img_dir, img_id[.png/.jpg/...])` без нормализации. `id="../../etc/passwd"` или `"../secret"` выходит за `img_dir` и читается в `packed_*`. Плюс `isfile` следует симлинкам. | Каноникализировать: `full=os.path.abspath(os.path.join(img_dir,name)); if os.path.commonpath([full, os.path.abspath(img_dir)]) != os.path.abspath(img_dir): continue`. Отбрасывать абсолютные пути и `..`. Добавить тест `id="../evil"` → `None`. |
| `GAP_RE:59` + цикл `minify_skeleton:275-277` `while masked != previous` | Warning | Скрытый O(N²): паттерн `(<tag>)\s+(<tag>)` съедает оба тега, цепочка из N тегов требует ~N/2 проходов, каждый сканирует весь файл. На 50k-теговом FB2 — секунды/минуты. ReDoS-поверхность малая (классы `[^<>]*`), но сложность квадратичная. | Переписать одним проходом с lookahead: `r'(?<=<[^<>]*>)[ \t\r\n]+(?=<[^<>]*>)'` + функция замены по соседям, либо ограничить итерации (напр. 10) + тест на цепочку `<a>\n<b>\n...` 5k тегов с таймаутом. |
| `BINARY_RE:53-54` в `optimize_fb2_payload:1342` | Warning | Бинари ищутся до снятия комментов/CDATA. `<binary>` внутри `<!-- ... -->` или вне CDATA-маски будет оптимизирован/заменён, хотя это не картинка. Низкий риск, но нарушает «never touches» инвариант. | Сначала маскировать CDATA+комменты (как в `minify_skeleton`), искать `BINARY_RE` на маске, либо явно скипать матчи внутри `COMMENT_RE`/`CDATA_RE` диапазонов. Тест: `<!-- <binary id="x">... -->` остаётся байт-в-байт. |
| `_iter_fb2_payloads:1866` `os.walk`, `_expand_sources:2112-2119` | Warning | `os.walk` без `followlinks=False` явного + верхний `isdir(symlink→dir)` обходит ссылку наружу библиотеки; родительские симлинки в `path` не проверяются (`islink` только на сам файл). | Явно `os.walk(..., followlinks=False)`, в `_expand_sources`/`_optimize_one` резолвить `os.path.realpath` и скипать/предупреждать о симлинкнутых директориях. Тест с `symlink dir`. |
| `_restore_member_comments:1582-1632` ручной парсинг central directory | Warning | Ручная хирургия ZIP: `rfind(PK\x05\x06)` берёт последний EOCD (ложное срабатывание если комментарий архива содержит эти байты — тогда `cd_off+cd_size != eocd_pos` спасает и вернёт False, ок). ZIP64/multi-disk честно отклоняются. Риск — `open(tmp,"wb")` перезапись неатомарна (креш = обрезанный tmp, но оригинал цел + последующая `_verify_candidate` ловит). | Оставить логику, но писать в `tmp.new` + `os.replace`, добавить тест с `b"PK\x05\x06"` внутри `archive_comment` и с ZIP64-заглушкой. |
| `decode_body:192-206` `base64.b64decode(cleaned)` без `validate=True` | Opt | Мусорные символы молча игнорируются (стандартный `b64decode` пропускает non-alphabet?). Может принять слегка битый блок вместо skip. | Использовать `base64.b64decode(cleaned, validate=True)`; тест `decode_body("ab!cd") is None`. Сейчас тест `!!!not-base64!!!` уже None — проверить что с `validate` не сломается легитимный whitespace (он уже stripped). |
| `shutil.which("ect")/("ffmpeg")` TOCTOU | Opt | Проверка наличия и запуск разнесены во времени; PATH может смениться. Не эксплуатабельно, но `_run_optimize_batch` кэширует `have_ect` один раз — ок. | Не фиксить, только задокументировать; при `FileNotFoundError` в `run_tool` уже возвращается False. |

Буферных переполнений/UB нет (Python, срезы/struct с проверками длин). ZipSlip нет (нет `extractall`, только `read`/`writestr`).

---

## 3. СЛОЖНОСТЬ — O(N) оценка, скрытые циклы, аллокации

| Участок | Оценка | Комментарий |
|---|---|---|
| `minify_skeleton` без fixpoint | O(N) | `CDATA mask O(N) + COMMENT sub O(N) + replace токенов O(N)`. Fixpoint ломает до O(N²) — см. §2. |
| `optimize_fb2_payload` скелет | O(N + M·K) | N — байты FB2, M — число картинок, K — средний размер картинки. `list(BINARY_RE.finditer)` O(N), placeholders O(N), `blocks` dict O(M). |
| `_packed_cost(raw)=len(zlib.compress(b64(raw),9))` | O(K) sub-ms | Вызывается многократно: `base_cost` + per-candidate + `_squeeze_candidate` + `_try_lossy`. Для книги с 50 картинками × 4 кандидата = 200 compress — ок, но повторные compress одних и тех же `base`/`cb` не мемоизированы. Opt: кэш `dict[id(bytes)→cost]` в пределах одного `img`. |
| `_distinct_colors(limit)` `getcolors` | O(P) P=пиксели | Early exit на `limit` — хорошо. Лимиты 257/4097 адекватны. |
| `_pixels_equal` `convert(RGB)+difference+getbbox` | O(P) | Вызывается на каждого кандидата + финальная проверка — самый тяжёлый CPU после `ect`. Оправдано (pixel-identity инвариант). |
| `_jpeg_ladder` 8 rung × (encode+decode+`_ssim_score` fork ffmpeg ~25мс) | O(8·(P+F)) | Ранний выход на первом проходящем — хорошо. Ladder вверх вместо бисекции обоснован комментом (немонотонность SSIM). |
| `optimize_images` threads | O(M/W) wall, O(M) total | Детерминирован (`{idx:bytes}`, тесты `test_workers_agree`), порядок `lossy_marks` неважен (потребляется как set) — корректно. |
| `optimize_zip_file` + `_write_candidate` + `ect -zip` + `_verify`×2 | O(N+M·K) + fork | Два `verify` после `ect` — правильно, не избыточно. |
| `_parse_lossy_token`/`_render_lossy_token` | O(T) T=токены | Сортировка таргетов/ids — детерминирован, ок. |
| Память | O(N+M·K·~2.3) | `payload+text+skeleton+blocks(b64)+raw+optimized` одновременно. Для CLI-оптимизатора приемлемо, но см. лимиты §1. |

Лишних аллокаций мало: `encode_body` один раз на победителя, `blocks[img.idx]=orig_body` при keep — zero-copy (ссылка, не копия). `_flat_b64_len` без кодирования — хорошо.

---

## 4. ЧИТАЕМОСТЬ — нейминг, стиль, избыточность

Общее: отлично. Один файл 2220 строк, `snake_case`, guard-clauses первыми, docstrings у всех публичных, инварианты прокомментированы (почему ladder вверх, почему `CLOSE_RATIO=1.2`, почему `LOSSY_PNG_MAX_PX`). `VERSION="4.7"`, `DEPS` таблица, `Fb2Stats.breakdown()` скрывает нули — удобно.

| Блок кода | Тип | Описание | Как исправить |
|---|---|---|---|
| `test_fb2opt.py:1158-1159` `@unittest.skipUnless(HAS_PIL...)` дважды | Opt | Копипаста, второй декоратор мёртв. | Убрать дубль. |
| `GENERIC_SAFE_FORMATS:900` посреди эвристик | Opt | Константа затесалась между функциями, рядом `LOSSY_*` в шапке. | Перенести к `LOSSY_*` блоку (81-88). |
| `_Image.idx` vs `enumerate(matches)` | Opt | `idx` = индекс в `matches` (включая скипнутые без id?), но `images` фильтрует скипы — `idx` не плотный. Работает (ключи dict), но сбивает. | Либо `idx=len(images)` плотный, либо переименовать в `match_idx` с комментом. |
| `except Exception: return ...` в чистых хелперах (`_flat_b64_len:220`, `_packed_cost:231`, `_tag_name` ок) | Warning | Широкий `except` на арифметике/регексах маскирует баги (напр. `MemoryError`?). В PIL-местах широкий `except` оправдан комментом (981-982), в чистых — нет. | Сузить до `(TypeError, ValueError, OverflowError)`; добавить `raise` в debug через `assert`. |
| Дубли `stem + "_ref.png"` в `_jpeg_ladder:1100` и `_lossy_png:1224` | Opt | Одинаковый шаблон имён в двух функциях, риск коллизии при рефакторинге в общий пул. | Вынести `_lossy_stem(workdir, idx)` хелпер. |
| `print(..., file=sys.stderr)` напрямую в либе | Opt | Смешение либы и CLI затрудняет переиспользование. | Завести `_warn(msg)` хелпер или `logging`; тесты уже ловят через `redirect_stderr` — не сломается. |

Стиль: `from __future__ import annotations`, `dataclass`, `frozenset INLINE_TAGS`, regex-флаги явные — всё по PEP8. Избыточности логики нет.

---

## 5. ТЕСТЫ — покрытие каждой функции (блокер)

Прогон: `113 tests OK (7.6s)`, hermetic без `ect`/`ffmpeg` (моки), `real-ect` тесты скипаются корректно. CI матрица `3.9-3.13 × {nopillow,pillow}` — правильно ловит `Image is None` ветви. Инвариантные тесты сильные: `test_pixels_survive_default`, `test_no_placeholders_survive`, `test_binary_tags_stay_schema_clean`, `test_flat_scan_book_stays_honest`, `test_packed_cost_properties`, `test_ratio_gate_skips_hopeless_ect`.

Но чек-лист требует **прямой тест каждой функции**. Факт: 81 `def` в `fb2opt`, прямых `mod.*` упоминаний нет для:

| Блок кода | Тип | Описание | Как исправить |
|---|---|---|---|
| `dep_status`, `format_deps`, `short_hint:342-371` | Крит* (по контракту) | Нет ни одного `TestDeps`. `main([])` и `-h` косвенно трогают, но `dep_status` ветви `found/NOT FOUND` не проверены. | Добавить `TestDeps`: моки `shutil.which`/`have_pil` → `dep_status`/`format_deps` содержат `found`/`NOT FOUND`; `short_hint` содержит `Usage`+`Dependencies`. |
| `_cpu_count:312`, `_umask:1505`, `_fresh_info:1512` | Крит* | Нет прямых тестов. `_umask` race (§1) вообще не покрыт. | `test_cpu_count>=1`, `test_umask_restores`, `test_fresh_info_perms_and_mtime` (моки `getmtime`, проверка `0o644 & ~umask`). |
| `_gap_replace:244`, `_tag_name` ок, `_looks_complete:378` | Крит* | `_gap_replace` только через `minify`, `_looks_complete` только через shrink-тесты (png/jpg happy path, нет `gif/other→True`, `empty→False`). | Прямые кейсы: inline/inline→space, block→empty, `png` без трейлера→False, `other`→True. |
| `_process_image:389`, `run_tool:160`, `have_ffmpeg`, `_lossy_tools_ok` | Крит* | Только через интеграцию/моки строкой. Нет `run_tool([])→False`, `run_tool(bad cmd)→False`, `timeout` ветви. | `TestProcessImage`: пустой raw, gif passthrough, `OSError` на write→keep, `have_ect=False+Image=None`→keep. `TestRunTool`: `[]`, `["false"]`, `["nonexistent-xyz"]`. |
| `_set_lossy_mark:595`, `_token_bytes:669`, `_strip_legacy_marks:679`, `_project_lossy_marks:701`, `_write_lossy_token:734` | Крит* | Маркер-система — ядро lossy-безопасности, но прямые тесты есть только для `_lossy_mark`/`_strip_mark`/`token roundtrip`/`upsert`. `_set_lossy_mark`, `_token_bytes`, `_strip_legacy_marks`, `_project`, `_write` — только через `optimize_fb2_payload`. | По одному тесту: `set→overwrite`, `token_bytes` сумма, `strip_legacy` счётчик байт, `project` с `lossy=None→({},set())`, `write` reopened счёт + fallback без `document-info`. |
| `_encode_png_bytes:856`, `_exact_png_candidates:868`, `_exact_crossover_candidates:903`, `_squeeze_candidate:937`, `_save_png:1051`, `_drop_paths:1081`, `_jpeg_ladder:1090`, `_gray_probe_at:1138` | Крит* | Smart/lossy ядро без прямых тестов; покрыто через `_try_lossless_variants`/`_lossy_jpeg/png`, но ветви `meta_from=None`, `exif→[]`, `large→[]`, `OSError→base` не изолированы. | `TestExactCandidates`: gray→1 cand, palette trim, exif→[], huge→[], alpha→skip. `TestSqueeze`: `have_ect=False`→packed cost, `OSError`→base. `TestDropPaths`: несуществующие файлы не бросают. |
| `_iter_fb2_payloads:1857`, `_payloads_from_file:1874`, `_find_replacement:1951` | Крит* | Только через `cmd_extract/pack roundtrip`. Нет: missing src→stderr, bad zip→stderr, `no .fb2`→info, traversal (`../`) кейса. | Добавить `TestIterPayloads` + `test_find_replacement_traversal` (после фикса §2). |
| `_clone_info` ок, `_verify_candidate` ок, `_write_candidate` ок | — | Покрыты — пример как надо. | — |

*) «Крит» здесь — по букве контракта («нет теста на функцию → REJECTED»), не по техриску. После добавления ~20 focused тестов (≈150 строк) §5 будет закрыт без изменения прод-кода.

Оценка сложности исправления тестов: 1-2 часа, все моки уже есть в файле как образцы.

---

## 6. ROADMAP — сверка с `doc/roadmap.md`

| Блок кода | Тип | Описание | Как исправить |
|---|---|---|---|
| `doc/roadmap.md` отсутствует (`ls doc/` → No such file до аудита) | Крит | Чек-лист §6 требует сверить реализацию со спецификацией. Сверять не с чем. `git log` показывает итерации (`lossy stamp to program-used`, `hermetic lossy tests`, `member-comment restore`), но без roadmap нельзя отличить «фича по плану» от «отход от спецификации». README описывает поведение, но это не roadmap (нет этапов, критериев готовности, out-of-scope). | Создать `doc/roadmap.md` (этапы: lossless core → ZIP/comment preserve → lossy+SSIM → stamp/migration → perf/parallel; для каждого Done/Todo + инварианты). Либо зафиксировать решением что README = спецификация и удалить §6 из чек-листа. До тех пор — REJECTED. |

По README расхождений прод-кода не найдено (проверено вручную): `old-new>0` (`_place_if_smaller:1684`), `atomic os.replace` (1690,1818), `.fb2opt-*.zip` cleanup (1473), `ect -9/-strip/-progressive` (848-853), `progressive` caveat документирован, `marks:` учёт (1429,1441), `repack only` fallback (133), `symlink skip`/`hardlink inode`/`ZIP dates/perms/comments preserve` — всё соответствует коду. Но без roadmap это не засчитывается как §6.

---

## Итоговая таблица must-fix (минимум для APPROVED)

| # | Блок кода | Тип | Описание | Как исправить |
|---|---|---|---|---|
| 1 | `doc/roadmap.md` | Крит | Нет файла — §6 непроверяем | Создать roadmap или убрать требование |
| 2 | `_umask:1505` | Крит | Глобальный race в пуле потоков | Вычислить umask один раз / lock |
| 3 | `_find_replacement:1951` | Warning→Крит при враждебном FB2 | Path traversal за `img_dir` | `abspath+commonpath` guard + тест |
| 4 | §5 тесты (18 функций) | Крит (контракт) | Нет прямых тестов | Добавить ~20 focused тестов |
| 5 | `GAP fixpoint:275` | Warning | O(N²) на цепочках тегов | Lookahead одним проходом |
| 6 | ZIP/Pillow без лимитов | Warning | OOM/zip-bomb | `MAX_*` лимиты + `DecompressionBomb` guard |
| 7 | `registry` без лока | Warning | Race реестра темпов | `Lock` |
| 8 | `BINARY_RE` до маски | Warning | Комментный `<binary>` оптимизируется | Маскировать перед поиском |
| 9 | `except Exception` в чистых хелперах | Warning | Маскирует баги | Сузить исключения |
| 10 | `test:1158` дубль, `GENERIC_SAFE_FORMATS` место, `validate=True`, `walk followlinks` | Opt | Гигиена | По мелочи перед релизом |

Без 1-4 — только REJECTED. 5-10 могут уйти отдельными Warning в APPROVED с планом, но сейчас в пакете с блокерами — тоже в отказе.

---

## Приложение: что хорошо (не ломать при фиксах)

- Pixel-identity инвариант default-режима доказан тестами и `_pixels_equal` проверками на каждом кандидате (`_exact_png:874,882,895`, `_squeeze:958`, `_try_lossless:1001`).
- Packed-cost честность (`base64+zlib-9`) вместо `len(raw)` — правильно, тест `test_try_lossy_packed_cost_decides` ловит регрессию.
- `CLOSE_RATIO`/`ECT_FAST_BYTES` гейт ect-попыток — верный перфобаланс, покрыт `test_ratio_gate`.
- Токен `program-used` schema-valid + миграция legacy + `reopened` счётчик — архитектурно чисто.
- `minify_skeleton` CDATA byte-exact + inline-space сохранение (`one+two` не склеивает) — редкая аккуратность.
- CI hermetic (моки вместо ect/ffmpeg) + матрица pillow/nopillow — зрело.

*Аудитор: Senior Code Forensics / AppSec QA. Перепроверка после фиксов coder'а обязательна.*

---

# Перепроверка 2026-09-11 (после исправлений coder)

- Объект: `fb2opt` (2349 строк), `test_fb2opt.py` (1961 строк, 126 тестов), `README.md`
- Прогон: `py_compile OK`, `python3 test_fb2opt.py → Ran 126 tests OK` (было 113)
- Покрытие: 85/85 `def` имеют прямое упоминание `mod.<fn>` или `'fn'` в тестах (было ~67/81). Добавлен `TestAuditDirectCoverage` (13 методов).
- Функциональные спот-чеки (все OK): GAP inline/block/chain/text; traversal `ok`/`../ok`/`/etc/passwd`/`''`; commented `<binary>` → `pics==1`, без `__FB2OPT_`; `decode_body('ab!cd') is None`; `_umask` кэширован; `_pil_open(huge) is None`; `_encode_png_bytes(None) is None`; `_binary_matches` 1/3.

**Вердикт: [APPROVED]**

## §1 Память и ресурсы — исправлено
- `_umask` кэшируется под `_UMASK_LOCK` (двойной checked locking, fallback `0o022`): повторные вызовы не трогают process-global umask. Проверено `a==b==_CACHED_UMASK`.
- Реестр темпов `_reg_append/_reg_forget` под `_REGISTRY_LOCK`; все `registry.append/remove` переведены. Многопоточный smoke 4×50 append — 200 записей, без потерь.
- DoS-границы введены: `MAX_ARCHIVE_MEMBERS=10000`, `MAX_MEMBER_BYTES=500М`, `MAX_ARCHIVE_BYTES=1Г` (pre-check по `ZipInfo.file_size` до распаковки), `MAX_IMAGE_PX=50М` + `len(raw)` guard в `_pil_open`, size guard в `_restore_member_comments`. Утечек FD нет (контекстные менеджеры, `os.close` после `mkstemp`, `finally: unlink`).

## §2 Безопасность — исправлено
- `_find_replacement`: скип `isabs`, `abspath+commonpath` guard, `isfile` в `try/OSError`. Проверено на `../`, `/etc/passwd`.
- `GAP_RE` — lookahead `(?=(<...>))`, `_gap_replace` возвращает `left+sep`, `minify_skeleton` — один `sub()` O(N). Семантика сохранена (inline→пробел, block→склейка, текст не тронут).
- `<binary>` в комментах/CDATA: `_ignored_spans/_binary_matches` используются в `optimize_fb2_payload`, `cmd_extract`, `cmd_pack` (ручная сборка `_parts` со скипом). Закомментированный блок больше не даёт `pics+1`.
- `os.walk(..., followlinks=False)` в обоих местах; `b64decode(validate=True)`; `_DEP_CHECKS` динамический (`lambda: have_pil()`), `_encode_png_bytes/_save_png` guard на `None` (найдено новым тестом — реальный краш до фикса).

## §3 Сложность — принято
- GAP fixpoint O(N²) устранён; `_packed_cost` повторные compress без мемоизации — оставлено сознательно (sub-ms, книги малые); память ограничена лимитами §1. Скрытых циклов не найдено.

## §4 Читаемость — принято
- `GENERIC_SAFE_FORMATS` перенесён к константам, дубль `skipUnless` убран, `except` сужены в чистых хелперах (`_flat_b64_len`, `_packed_cost`, `_cpu_count`, `_token_bytes`, `_set_lossy_mark`, `decode_body split`). Широкие `except Exception` остались только там, где оправданы: PIL-зоопарк на враждебных входах, never-raises обёртки реестра, верхний guard батча. Нейминг/стиль без замечаний.

## §5 Тесты — закрыто
- Было: REJECTED (нет прямых тестов ~18 функций). Стало: 85/85 покрыты, 126/126 зелёные, hermetic (моки ect/ffmpeg), CI-матрица не сломана. Новых хелперов 4 (`_ignored_spans`, `_binary_matches`, `_reg_append`, `_reg_forget`) — все покрыты.

## §6 Roadmap — предупреждение вне контракта coder
| Блок кода | Тип (Крит/Warning/Opt) | Описание | Как исправить |
|---|---|---|---|
| `doc/roadmap.md` отсутствует | Warning (владелец: Architect) | Сверка по чек-листу невозможна; сверено по `README.md` как de-facto спецификации — расхождений прод-кода не найдено (`old-new>0`, `os.replace`, `.fb2opt-*.zip`, `ect -9/-strip/-progressive`, `marks:`, symlink-skip) | Architect/Supervisor: создать `doc/roadmap.md` либо формально зафиксировать `README.md` как спецификацию и снять §6. Coder'у запрещено трогать этот файл — повторный REJECTED по нему создал бы бесконечный цикл, поэтому не блокирует APPROVED по коду |

Замечание: `git diff README.md` (17 строк) — предсуществующее изменение рабочего дерева, не от coder-патча (патч трогал только `fb2opt`, `test_fb2opt.py`); на вердикт не влияет.

*Аудитор: Senior Code Forensics / AppSec QA. Код к релизу готов; roadmap — эскалировано.*
