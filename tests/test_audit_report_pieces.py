"""M-2: the audit page is rendered/validated/written as head + data + tail, never joined."""
import pytest

from configmerge.auditor import html_report as H
from configmerge.auditor.engine import AuditFile, AuditResult

TRICKY = "a=1\n</script><SCRIPT>x</Script> <!-- c --> </html></body> ✓ é \U0001F600\n"


def _result(tmp_path, n_files=1):
    files = [
        AuditFile(rel_path=f"conf/f{i}.properties", file_type="text", present_in=["n1", "n2"],
                  params=[], binary={}, raw_content={"n1": TRICKY, "n2": TRICKY + "b=2\n"},
                  mismatch_count=1)
        for i in range(n_files)
    ]
    return AuditResult(nodes=["n1", "n2"], node_dirs={"n1": "n1", "n2": "n2"}, files=files,
                       total_mismatches=n_files, total_logical_diffs=0,
                       run_timestamp="20260101_000000", run_dir=str(tmp_path))


def test_pieces_join_to_the_same_page(tmp_path):
    head, data_js, tail = H._render_html_parts(_result(tmp_path))
    page = H._build_html(_result(tmp_path))
    assert head + data_js + tail == page
    assert H._DATA_SLOT not in page
    assert page.count("const AUDIT_DATA = {") == 1


@pytest.mark.parametrize("data_js", [
    None,                                            # real rendered data
    '{"x": "</script><script>alert(1)"}',            # unescaped: must fall back to full parse
    '{"x": "<!-- -->"}',
    '{"x": "</html></body><!DOCTYPE html>"}',
    '{}',
])
def test_piecewise_validation_matches_whole_page(tmp_path, capsys, data_js):
    head, rendered, tail = H._render_html_parts(_result(tmp_path))
    data_js = rendered if data_js is None else data_js
    whole = H._validate_html(head + data_js + tail, "p.html")
    whole_err = capsys.readouterr().err
    parts = H._validate_html_parts(head, data_js, tail, "p.html")
    assert (parts, capsys.readouterr().err) == (whole, whole_err)


@pytest.mark.parametrize("head,tail", [("<html>", "</html>"), ("<!DOCTYPE html><script>", "")])
def test_piecewise_validation_reports_broken_skeleton(capsys, head, tail):
    assert H._validate_html_parts(head, "{}", tail, "p.html") is False
    assert H._validate_html(head + "{}" + tail, "p.html") is False
    err = capsys.readouterr().err
    assert err.count("CMT-AUD-W009") == 2


def test_written_single_and_multi_part_reports_equal_joined_pages(tmp_path, monkeypatch):
    path = H.write_audit_html(_result(tmp_path), str(tmp_path / "single"))
    assert open(path, encoding="utf-8", newline="").read() == H._build_html(
        _result(tmp_path), files_js=H._split_into_parts(_result(tmp_path))[0])

    monkeypatch.setattr(H, "_PART_SIZE_LIMIT", 1)      # one file per part
    res = _result(tmp_path, n_files=2)
    H.write_audit_html(res, str(tmp_path / "multi"))
    p2 = (tmp_path / "multi" / "audit_report_p02.html").read_text(encoding="utf-8")
    assert p2.startswith("<!DOCTYPE html>") and p2.endswith("</html>")
    assert "conf/f1.properties" in p2 and "conf/f0.properties\"" not in p2.split("const AUDIT_DATA")[1]


def test_report_write_memory_budget(tmp_path):
    """Regression budget: traced peak while writing the report stays < 3.5x the raw content.

    Measured on this fixture: 5.2x before M-2 (page joined, 2 bytes/char), 2.1x after.
    tracemalloc counts are deterministic, so the margin is not OS/allocator noise.
    """
    import random
    import tracemalloc
    rnd = random.Random(1)

    def text(n):
        return "".join(f"key{i}.name=value-{rnd.random()}\n" for i in range(n))

    files = [AuditFile(rel_path=f"c/f{i}.properties", file_type="text", present_in=["n1", "n2"],
                       params=[], binary={}, raw_content={"n1": text(4000), "n2": text(4000)},
                       mismatch_count=1) for i in range(20)]
    res = AuditResult(nodes=["n1", "n2"], node_dirs={}, files=files, total_mismatches=20,
                      total_logical_diffs=0, run_timestamp="20260101_000000", run_dir=str(tmp_path))
    raw = sum(len(v) for f in files for v in f.raw_content.values())
    tracemalloc.start()
    try:
        base = tracemalloc.get_traced_memory()[0]
        H.write_audit_html(res, str(tmp_path / "out"))
        peak = tracemalloc.get_traced_memory()[1] - base
    finally:
        tracemalloc.stop()
    assert peak < 3.5 * raw, f"report write peak {peak / raw:.2f}x raw content"


def test_version_is_stamped_in_audit_log_and_every_report_page(tmp_path, monkeypatch):
    import glob
    import pathlib
    from configmerge import __version__
    from configmerge.auditor.engine import AuditEngine
    from configmerge.models import BaseDirConfig

    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setattr(H, "_PART_SIZE_LIMIT", 1)      # force part pages + index page
    for node, val in (("n1", "a"), ("n2", "b")):
        for name in ("x.properties", "y.properties"):
            (tmp_path / node / "c").mkdir(parents=True, exist_ok=True)
            (tmp_path / node / "c" / name).write_text(f"[CouchBase]\nk={val}\n", encoding="utf-8")
    eng = AuditEngine(nodes=[BaseDirConfig(base_dir=str(tmp_path / n), name=n) for n in ("n1", "n2")],
                      report_dir=str(tmp_path / "reports"), quiet=True)
    eng.run()

    log = open(glob.glob(str(tmp_path / "reports" / "audit_*" / "audit*.log"))[0], encoding="utf-8").read()
    assert f"ConfigMergeTool v{__version__}" in log.splitlines()[0]
    pages = glob.glob(str(tmp_path / "reports" / "audit_*" / "*.html"))
    assert len(pages) == 3                              # index + 2 parts
    for p in pages:
        html = open(p, encoding="utf-8").read()
        assert f'<meta name="generator" content="ConfigMergeTool {__version__}">' in html
        assert f"ConfigMergeTool v{__version__}" in html.split("<body")[1]   # visible header
