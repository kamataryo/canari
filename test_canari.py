"""python3 test_canari.py — 生成物が壊れていないか（Office の「修復」ダイアログはおとりとして致命的）"""
import importlib.machinery
import importlib.util
import io
import json
import os
import posixpath
import pty
import zipfile
from contextlib import redirect_stdout
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

def run_pick(keys, multi=True):
    """疑似端末で pick() を動かし、描画が出てからキーを送る（raw にする前の入力は捨てられるため）"""
    pid, fd = pty.fork()
    if pid == 0:
        try:
            print("RESULT", canari.pick(["a", "b", "c"], multi=multi), flush=True)  # os._exit は flush しない
        finally:
            os._exit(0)
    out = b""
    while "❯".encode() not in out:
        out += os.read(fd, 1024)
    os.write(fd, keys)
    while True:
        try:
            chunk = os.read(fd, 1024)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    os.waitpid(pid, 0)
    return out.decode().split("RESULT ")[-1].strip()


# カーソルは a から始まる。行は all, a, b, c
assert run_pick(b"\x1b[B \x1b[B \r") == "[1, 2]"
assert run_pick(b"kk\r") == "[2]"  # all を越えて末尾に回り、何も選ばずに enter なら今の行
assert run_pick(b" j \x1b[A \r") == "[1]"  # 選んで外す
assert run_pick(b"k j \r") == "[1, 2]"  # all で全部選んでから a を外す
assert run_pick(b"k  \r") == "[0, 1, 2]"  # all を 2 回で全部外れ、all の上で enter なら全部
# 1 つだけ選ぶ形。行は a, b, c で、space は効かない
assert run_pick(b"j\r", multi=False) == "[1]"
assert run_pick(b"k \r", multi=False) == "[2]"

# list: ラベルごとにまとまり、絞り込むとファイルごとになる。旧データ（description）も読める
canari.aws = lambda *a: {"Items": [
    {"id": {"S": "1"}, "label": {"S": "Dropbox /経理/"}, "filename": {"S": "a.xlsx"}, "created_at": {"N": "1763800000"},
     "hit_count": {"N": "2"}, "last_hit_at": {"N": "1763900000"}},
    {"id": {"S": "2"}, "label": {"S": "Dropbox /経理/"}, "filename": {"S": "b.xlsx"}, "created_at": {"N": "1763800001"},
     "hit_count": {"N": "0"}, "revoked_at": {"N": "1"}},
    {"id": {"S": "3"}, "description": {"S": "Google Drive"}, "filename": {"S": "c.docx"}, "created_at": {"N": "1763700000"},
     "hit_count": {"N": "0"}},
]}
with redirect_stdout(out := io.StringIO()):
    canari.cmd_list()
lines = out.getvalue().splitlines()
assert lines[1].split()[:4] == ["Google", "Drive", "1/1", "0"], lines
assert lines[2].split()[:4] == ["Dropbox", "/経理/", "1/2", "2"], lines
with redirect_stdout(out := io.StringIO()):
    canari.cmd_list("DROP")
lines = out.getvalue().splitlines()
assert [line.split()[2:4] for line in lines[1:]] == [["有効", "a.xlsx"], ["失効", "b.xlsx"]], lines

# remove: 確認で y 以外なら何も消さない。y なら選んだものだけ消す
scan, deleted = canari.aws, []
canari.aws = lambda *a: deleted.append(json.loads(a[a.index("--key") + 1])["id"]["S"]) if a[1] == "delete-item" else scan(*a)
canari.pick = lambda labels, multi=True: list(range(len(labels)))  # all を選んだことにする
for answer, expect in (("", []), ("n", []), ("y", ["1", "2"])):
    canari.input = lambda _, answer=answer: answer
    try:
        with redirect_stdout(io.StringIO()):
            canari.cmd_remove("drop")
    except SystemExit:
        pass
    assert deleted == expect, (answer, deleted)

names = [n for _, n, _ in canari.templates(date(2027, 2, 1))]
assert "2026年度_給与一覧.xlsx" in names and "人事評価_2026下期.docx" in names, names
print("ok")
