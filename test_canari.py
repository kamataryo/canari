"""python3 test_canari.py — 生成物が壊れていないか（Office の「修復」ダイアログはおとりとして致命的）"""
import importlib.machinery
import importlib.util
import io
import posixpath
import zipfile
from datetime import date
from pathlib import Path
from xml.dom.minidom import parseString

loader = importlib.machinery.SourceFileLoader("canari", str(Path(__file__).with_name("canari")))
canari = importlib.util.module_from_spec(importlib.util.spec_from_loader("canari", loader))
loader.exec_module(canari)

BEACON = "https://example.invalid/t/AAAAAAAAAAAAAAAAAAAAAA"

for today in (date(2026, 11, 23), date(2027, 2, 1)):
    for key, name, spec in canari.templates(today):
        data = canari.render(spec(), BEACON, *canari.fake_times())
        if name.endswith(".txt"):
            assert BEACON + "/" in data.decode(), name
            continue
        z = zipfile.ZipFile(io.BytesIO(data))
        names = z.namelist()
        assert names[0] == "[Content_Types].xml", name
        docs = {n: parseString(z.read(n)) for n in names}  # 全部 well-formed

        # Content_Types の Override と、rels の内部参照がすべて実在する
        for o in docs["[Content_Types].xml"].getElementsByTagName("Override"):
            assert o.getAttribute("PartName").lstrip("/") in names, (name, o.getAttribute("PartName"))
        external = []
        for n in (n for n in names if n.endswith(".rels")):
            base = posixpath.dirname(posixpath.dirname(n))  # foo/_rels/bar.rels → foo
            for r in docs[n].getElementsByTagName("Relationship"):
                if r.getAttribute("TargetMode") == "External":
                    external.append(r.getAttribute("Target"))
                else:
                    assert posixpath.normpath(posixpath.join(base, r.getAttribute("Target"))) in names, (name, n)
        assert BEACON + ".gif" in external, name
        assert any(t.startswith(BEACON + "/") for t in external) == (key == "servers"), name

names = [n for _, n, _ in canari.templates(date(2027, 2, 1))]
assert "2026年度_給与一覧.xlsx" in names and "人事評価_2026下期.docx" in names, names
print("ok")
