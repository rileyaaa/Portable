"""Real installed typing_extensions consumers, using only owned synthetic data."""
import asyncio
import importlib.metadata as md
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import typing_extensions as te
import anyio
import requests
import httpx
import docx
import pptx
import openpyxl
import xlsxwriter

def ordinary(p, directory=False):
    s=p.lstat()
    assert not stat.S_ISLNK(s.st_mode) and not getattr(s,"st_file_attributes",0)&0x400
    assert stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode) and s.st_nlink==1

def main():
    root=Path(__file__).absolute().parents[1]
    runtime=root/"tool/python"
    assert os.name=="nt" and sys.version_info[:3]==(3,14,10)
    assert Path(sys.executable).resolve()==runtime/"python.exe"
    assert sys.flags.isolated and sys.flags.ignore_environment and sys.flags.safe_path
    assert set(map(Path,sys.path))=={runtime/"python314.zip",runtime,runtime/"Lib/site-packages"}
    assert os.environ.get("PIP_CONFIG_FILE")==os.devnull
    version=sys.argv[1]
    assert md.version("typing-extensions")==version
    for module in (te,anyio,requests,httpx,docx,pptx,openpyxl,xlsxwriter):
        assert Path(module.__file__).resolve().is_relative_to(runtime/"Lib/site-packages"),module.__name__
    for name in ("Protocol","TypedDict","Required","NotRequired","Self","TypeAliasType","TypeVar","ParamSpec","override","get_type_hints","Sentinel","no_type_check_decorator"):
        assert hasattr(te,name),name
    class Payload(te.TypedDict):
        value: te.Required[int]
        note: te.NotRequired[str]
    assert Payload.__required_keys__==frozenset({"value"})
    assert Payload.__optional_keys__==frozenset({"note"})
    assert te.get_type_hints(Payload,include_extras=True)["note"]==te.NotRequired[str]
    @te.runtime_checkable
    class Getter(te.Protocol):
        def get(self)->int: ...
    class Value:
        def get(self):return 42
    assert isinstance(Value(),Getter) and not isinstance(object(),Getter)
    print("TYPING_EXTENSIONS_PUBLIC_EXPORTS="+json.dumps(sorted(te.__all__),ensure_ascii=True),flush=True)
    print("TYPING_EXTENSIONS_EXISTING_RUNTIME_TYPES=PASS "+version,flush=True)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path=="/portable-probe"
            body=b'{"value":42}'
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self,*args):pass
    with ThreadingHTTPServer(("127.0.0.1",0),Handler) as server:
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        try:
            url="http://127.0.0.1:"+str(server.server_port)+"/portable-probe"
            with requests.Session() as session:
                session.trust_env=False
                response=session.get(url,timeout=5)
                response.raise_for_status()
                assert response.json()=={"value":42}
            with httpx.Client(trust_env=False,timeout=5) as client:
                assert client.get(url).raise_for_status().json()=={"value":42}
            async def fetch():
                async with httpx.AsyncClient(trust_env=False,timeout=5) as client:
                    assert (await client.get(url)).raise_for_status().json()=={"value":42}
            anyio.run(fetch,backend="asyncio")
        finally:
            server.shutdown()
            worker.join(10)
            assert not worker.is_alive()
    print("EXISTING_HTTP_SYNC_ASYNC_LOOPBACK=PASS "+version,flush=True)
    for p in (*reversed(root.parents),root):ordinary(p,True)
    scratch=root/"tmp";scratch.mkdir(exist_ok=True);ordinary(scratch,True)
    with tempfile.TemporaryDirectory(prefix="typing-docs-",dir=scratch) as temp:
        directory=Path(temp)/"Portable \u4fbf\u643a document"
        directory.mkdir()
        word=directory/"\u4fbf\u643a.docx"
        document=docx.Document()
        document.add_paragraph("\u4fbf\u643a text")
        document.save(word)
        assert docx.Document(word).paragraphs[0].text=="\u4fbf\u643a text"
        slides=directory/"\u4fbf\u643a.pptx"
        deck=pptx.Presentation()
        slide=deck.slides.add_slide(deck.slide_layouts[5])
        slide.shapes.title.text="\u4fbf\u643a text"
        deck.save(slides)
        assert pptx.Presentation(slides).slides[0].shapes.title.text=="\u4fbf\u643a text"
        sheet=directory/"\u4fbf\u643a.xlsx"
        with xlsxwriter.Workbook(str(sheet),{"tmpdir":str(directory)}) as book:
            ws=book.add_worksheet("Data")
            ws.write("A1","\u4fbf\u643a")
            ws.write_number("B1",21)
            ws.write_formula("C1","=B1*2",None,42)
        wb=openpyxl.load_workbook(sheet,data_only=False)
        try:
            assert wb["Data"]["A1"].value=="\u4fbf\u643a" and wb["Data"]["C1"].value=="=B1*2"
        finally:wb.close()
        cached=openpyxl.load_workbook(sheet,data_only=True)
        try:assert cached["Data"]["C1"].value==42
        finally:cached.close()
    print("EXISTING_OFFICE_ROUNDTRIP=PASS "+version+" cached formula value only, no recalculation",flush=True)

if __name__=="__main__":main()
