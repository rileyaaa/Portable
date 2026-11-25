"""Targeted native Windows image/PDF and PyInstaller checks in moved packages.

Real BAT, Codex, shell, bundled Python and normal frozen executables. Synthetic
loopback model only; no browser/MCP execution, hostile files, elevated child,
bootloader manipulation, or changes to the embedded interpreter or sandbox.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("image_packager_native_core",ROOT/"tests/check_codex_tool_discovery.py")
core=importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
m=core.m

PROBE=r'''
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
from importlib.metadata import version

root=Path(os.environ["CODEX_INSTALL_DIR"]).resolve()
work=Path(__file__).resolve().parent
py=root/"tool/python/python.exe"
assert Path(sys.executable).resolve()==py
assert sys.flags.isolated and sys.flags.ignore_environment and sys.flags.safe_path
assert all(Path(p).resolve().is_relative_to(root/"tool/python") for p in sys.path if p)
assert work.is_relative_to(root/"work")
config=tomllib.loads((root/"home/config.toml").read_text(encoding="utf-8-sig"))
expected=config["shell_environment_policy"]["set"]
for k in ("CODEX_HOME","CODEX_INSTALL_DIR","CODEX_PYTHON","PIP_CONFIG_FILE","TEMP","TMP","PYTHONUSERBASE","PYTHONPYCACHEPREFIX"):
    assert k in expected and os.path.normcase(os.environ[k])==os.path.normcase(expected[k]),k
assert os.environ["PIP_CONFIG_FILE"].lower()=="nul"
for k in ("TEMP","TMP","PYTHONUSERBASE","PYTHONPYCACHEPREFIX"):
    assert Path(os.environ[k]).resolve().is_relative_to(root),k
assert (config["sandbox_mode"],config["approval_policy"],config["sandbox_workspace_write"]["network_access"])==(
    ("workspace-write","on-request",False) if MODE=="normal" else ("danger-full-access","never",True))
assert "portable_browser" not in config.get("mcp_servers",{})
if MODE=="normal":
    for sentinel in (root/"protected-audit.txt",root.parent/"outside-workspace-audit.txt"):
        try:
            with sentinel.open("wb") as out:out.write(b"unexpected")
        except PermissionError:
            pass
        else:
            raise AssertionError("Unexpected common-mode write: "+sentinel.name)
print("NATIVE_IMAGE_PACKAGER_POLICY=PASS "+MODE,flush=True)

if SUITE=="image":
    import PIL
    from PIL import Image, ImageDraw, ImageSequence, ImageOps, features
    import numpy as np
    import pymupdf
    import docx
    import pptx
    import openpyxl
    import openpyxl.drawing.image
    from pptx.util import Inches
    for mod in (PIL,np,pymupdf,docx,pptx,openpyxl):
        assert Path(mod.__file__).resolve().is_relative_to(root/"tool/python")
    assert PIL.__version__==version("pillow")==EXPECTED["pillow"]
    output=work/"\u56fe\u7247 PDF \u7ed3\u679c"
    output.mkdir()
    first=Image.new("RGB",(64,48),(30,110,210))
    ImageDraw.Draw(first).rectangle((8,8,22,22),fill=(230,30,50))
    second=Image.new("RGB",(64,48),(40,190,70))
    for fmt,ext in (("PNG","png"),("JPEG","jpg"),("TIFF","tiff"),("GIF","gif"),("BMP","bmp"),("WEBP","webp")):
        path=output/("image."+ext)
        first.save(path,format=fmt)
        with Image.open(path) as im:
            assert im.format==fmt and im.size==(64,48)
            im.load()
            converted=im.convert("RGB")
            assert converted.resize((32,24)).size==(32,24)
            if fmt in {"PNG","TIFF","BMP"}:assert converted.tobytes()==first.tobytes()
    for fmt,ext in (("GIF","gif"),("TIFF","tiff"),("PNG","png")):
        path=output/("frames."+ext)
        first.save(path,format=fmt,save_all=True,append_images=[second],duration=50,loop=0)
        with Image.open(path) as im:
            assert im.n_frames==2
            frames=[frame.convert("RGB").copy() for frame in ImageSequence.Iterator(im)]
            assert all(f.size==(64,48) for f in frames) and frames[0].getpixel((0,0))!=frames[1].getpixel((0,0))
    # Use supported dtype conversions, no malformed files or exploit inputs.
    a=np.array([[1,257],[1024,65535]],dtype=np.uint16)
    path=output/"uint16.png"
    Image.fromarray(a).save(path)
    with Image.open(path) as im:assert list(im.getdata())==[1,257,1024,65535]
    assert ImageOps.grayscale(first).mode=="L"
    pdf=output/"\u4fbf\u643a images.pdf"
    first.save(pdf,format="PDF",save_all=True,append_images=[second])
    with pymupdf.open(pdf) as doc:
        assert len(doc)==2
        for page in doc:
            pix=page.get_pixmap()
            with Image.open(io.BytesIO(pix.pil_tobytes(format="PNG"))) as im:
                im.load();assert im.size==(pix.width,pix.height)
        assert doc[0].get_images()
    # Image consumers already bundled for Office; normal archive roundtrip.
    image=output/"image.png"
    d=docx.Document();d.add_picture(str(image));d.save(output/"image.docx")
    assert len(docx.Document(output/"image.docx").inline_shapes)==1
    p=pptx.Presentation();s=p.slides.add_slide(p.slide_layouts[6])
    s.shapes.add_picture(str(image),Inches(1),Inches(1));p.save(output/"image.pptx")
    assert len(pptx.Presentation(output/"image.pptx").slides[0].shapes)==1
    x=openpyxl.Workbook();x.active.add_image(openpyxl.drawing.image.Image(str(image)),"A1")
    x.save(output/"image.xlsx");x.close()
    x=openpyxl.load_workbook(output/"image.xlsx");assert len(x.active._images)==1;x.close()
    print("NATIVE_IMAGE_PDF_OFFICE=PASS pillow="+PIL.__version__+" mode="+MODE,flush=True)
elif SUITE=="packager":
    import PyInstaller
    import _pyinstaller_hooks_contrib
    import PIL
    assert PyInstaller.__version__==version("pyinstaller")==EXPECTED["pyinstaller"]
    assert _pyinstaller_hooks_contrib.__version__==version("pyinstaller-hooks-contrib")==EXPECTED["pyinstaller-hooks-contrib"]
    assert PIL.__version__==EXPECTED["pillow"]
    for mod in (PyInstaller,_pyinstaller_hooks_contrib,PIL):
        assert Path(mod.__file__).resolve().is_relative_to(root/"tool/python")
    assert str(root/"tool/python/Lib/site-packages/bin").casefold() not in os.environ["PATH"].casefold()
    assert shutil.which("pyinstaller.exe") is None, "Vendor EXE unexpectedly exposed"
    def run(argv,env,timeout=180):
        p=subprocess.run(list(map(str,argv)),cwd=work,env=env,capture_output=True,timeout=timeout)
        out=p.stdout.decode("utf-8","backslashreplace");err=p.stderr.decode("utf-8","backslashreplace")
        if p.returncode:
            print(out[-6000:],flush=True);print(err[-10000:],flush=True)
            raise RuntimeError("Normal packaging command failed exit="+str(p.returncode))
        return out,err
    env=os.environ.copy()
    # Common mode's workspace/tmp is writable; the documented persistent
    # cache is protected unless task-approved. Use a task-local tmp cache in
    # common mode, the documented package cache in YOLO. No policy changes.
    job=root/"tmp"/"pyinstaller \u4fbf\u643a build"
    job.mkdir(parents=True)
    cache=(job/"cache" if MODE=="normal" else root/"cache"/"pyinstaller")
    cache.mkdir(parents=True,exist_ok=True)
    env["PYINSTALLER_CONFIG_DIR"]=str(cache)
    env["PYTHONDONTWRITEBYTECODE"]="1"
    out,_=run([py,"-B","-m","PyInstaller","--version"],env,60)
    assert out.strip()==EXPECTED["pyinstaller"]
    if BUILD=="version":
        print("NATIVE_PYINSTALLER_CLI=PASS "+MODE,flush=True)
    else:
        # Only a benign normal program, with actual Pillow hook/native
        # extension, standard library, Unicode args and file roundtrip.
        program=work/"\u4fbf\u643a app.py"
        program.write_text(
            "from pathlib import Path\nimport io, json, sys\nfrom PIL import Image\n"
            "assert getattr(sys,'frozen',False)\n"
            "im=Image.new('RGB',(13,9),(17,83,121)); stream=io.BytesIO(); im.save(stream,format='PNG')\n"
            "with Image.open(io.BytesIO(stream.getvalue())) as decoded: assert decoded.size==(13,9) and decoded.getpixel((0,0))==(17,83,121)\n"
            "Path(sys.argv[1]).write_text('ordinary frozen image',encoding='utf-8')\n"
            "print('PORTABLE_FROZEN_IMAGE_OK',flush=True)\n",encoding="utf-8")
        dist=work/"\u51bb\u7ed3 output";dist.mkdir()
        specdir=job/"spec";specdir.mkdir()
        builddir=job/"work";builddir.mkdir()
        args=[py,"-B","-m","PyInstaller","--noconfirm","--clean","--console",
              "--"+BUILD,"--name","portable-probe","--workpath",builddir,
              "--specpath",specdir,"--distpath",dist,program]
        out,err=run(args,env,240)
        print("PYINSTALLER_BUILD_OUTPUT_TAIL="+err[-2200:],flush=True)
        exe=(dist/"portable-probe.exe" if BUILD=="onefile" else dist/"portable-probe"/"portable-probe.exe")
        assert exe.is_file() and exe.stat().st_size>1024
        if BUILD=="onedir":assert (exe.parent/"_internal").is_dir()
        # Move the entire ordinary frozen output before launching it.
        moved=work/"\u79fb\u52a8 frozen result"
        if BUILD=="onefile":
            moved.mkdir();dest=moved/exe.name;exe.rename(dest)
        else:
            exe.parent.rename(moved);dest=moved/exe.name
        result=work/"\u51bb\u7ed3 result.txt"
        out,_=run([dest,result],env,90)
        assert "PORTABLE_FROZEN_IMAGE_OK" in out and result.read_text(encoding="utf-8")=="ordinary frozen image"
        print("NATIVE_PYINSTALLER_BUILD_RUN=PASS "+BUILD+" mode="+MODE+" version="+PyInstaller.__version__,flush=True)
else:
    raise AssertionError("Unexpected suite")
print("PORTABLE_TARGETED_IMAGE_PACKAGER_OK",flush=True)
'''

def expected_versions():
    pairs={}
    for line in (ROOT/"tool/python-packages.in.txt").read_text(encoding="utf-8").splitlines():
        if "==" in line and not line.lstrip().startswith("#"):
            k,v=line.split("==",1);pairs[k.lower().replace("_","-")]=v
    return {k:pairs[k] for k in ("pillow","pyinstaller","pyinstaller-hooks-contrib")}

def native(suite,mode,build):
    assert os.name=="nt" and sys.flags.isolated
    assert suite in {"image","packager"} and mode in {"normal","yolo"}
    assert build in {"version","onedir","onefile"}
    for p in (*reversed(ROOT.parents),ROOT):m.ordinary(p)
    scratch=ROOT/"tmp";scratch.mkdir(exist_ok=True);m.ordinary(scratch)
    with core.extracted_package_fixture(scratch,suite+"-"+mode+"-"+build) as owned:
        fixture=owned/"Relocated \u4fbf\u643a Portable";fixture.mkdir()
        manifest=json.loads((ROOT/"tool/runtime-manifest.json").read_text(encoding="utf-8-sig"))
        bat="\u542f\u52a8Codex.bat"
        for relative in ("env.ps1","run-codex.ps1",bat,"tool/runtime-manifest.json",
                         "tool/portable-process.ps1","tool/python","tool/node","tool/bin",
                         "tool/android/platform-tools","home/skills",*manifest["files"]):
            m.copy_input(relative,fixture)
        if mode=="yolo":
            source=ROOT/"Version_History/YOLO mode\u4e13\u7528\u5305-env.ps1";m.ordinary(source)
            (fixture/"env.ps1").write_bytes(source.read_bytes())
        (fixture/"codex-resources").mkdir(exist_ok=True)
        probe=fixture/"work/tool-probe";probe.mkdir(parents=True)
        pth=fixture/"tool/python/python314._pth";original_pth=pth.read_bytes()
        assert original_pth==(ROOT/"tool/python/python314._pth").read_bytes()
        for sentinel in (fixture/"protected-audit.txt",owned/"outside-workspace-audit.txt"):
            sentinel.write_bytes(b"unchanged synthetic sentinel")
        (fixture/"home/portable-extensions.toml").write_text('[mcp_servers.portable_browser]\ncommand = "synthetic-never-executed"\n',encoding="utf-8")
        source="MODE="+repr(mode)+"\nSUITE="+repr(suite)+"\nBUILD="+repr(build)+"\nEXPECTED="+repr(expected_versions())+"\n"+PROBE
        (probe/"documents.py").write_text(source,encoding="utf-8")
        compile(source,str(probe/"documents.py"),"exec")
        core.DOCUMENT_MARKER="PORTABLE_TARGETED_IMAGE_PACKAGER_OK"
        # Reuse the already verified shell result/continuation protocol,
        # not the browser, MCP or prior document workloads.
        handler=core.handler_for(fixture,"documents")
        m.MODEL_REQUESTS.clear();m.MODEL_ERRORS.clear()
        model="gpt-6.2-sol"
        with m.serving(m.provider("",model=model,handler=handler,max_requests=2+core.MAX_CELL_WAITS)) as port:
            (fixture/"env.local.ps1").write_text(
                '$env:CODEX_AUTH_MODE = "api"\n'
                '$env:CODEX_PROXY_ENABLED = "false"\n'
                '$env:CODEX_DISABLE_WEBSOCKET = "true"\n'
                f'$env:CODEX_MODEL = "{model}"\n'
                f'$env:CODEX_BASE_URL = "http://127.0.0.1:{port}/v1"\n'
                '$env:OPENAI_API_KEY = "synthetic-offline-not-a-real-key"\n',encoding="utf-8")
            windows=Path(os.environ["SystemRoot"]);cmd=windows/"System32/cmd.exe"
            env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","PATHEXT","OS","PROCESSOR_ARCHITECTURE","USERNAME","COMPUTERNAME") if k in os.environ}
            env["PATH"]=str(windows/"System32")
            command=(f'"{cmd}" /d /s /c ""{fixture / bat}" --portable-auth=api '
                     'exec --skip-git-repo-check --json "Run the authorized local compatibility check.""')
            proc=subprocess.Popen(command,executable=str(cmd),cwd=fixture,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                out,err=proc.communicate(timeout=450)
            except subprocess.TimeoutExpired:
                subprocess.run([str(windows/"System32/taskkill.exe"),"/PID",str(proc.pid),"/T","/F"],capture_output=True,timeout=20)
                proc.communicate(timeout=20);raise AssertionError("Native targeted fixture timed out")
            if proc.returncode or m.MODEL_ERRORS or core.DONE.encode() not in out:
                print(out.decode("utf-8","replace")[-16000:]);print(err.decode("utf-8","replace")[-16000:])
                raise AssertionError("Native targeted failure "+suite+"/"+mode+"/"+build+": "+repr(m.MODEL_ERRORS))
            assert handler.continuation.finished and len(m.MODEL_REQUESTS)==2+handler.continuation.wait_count
            exits=[]
            for line in out.decode("utf-8","replace").splitlines():
                try:event=json.loads(line)
                except ValueError:continue
                item=event.get("item",{})
                if event.get("type")=="item.completed" and item.get("type")=="command_execution":exits.append(item.get("exit_code"))
            assert exits and all(x==0 for x in exits),exits
            evidence="".join(handler.continuation.evidence)
            marker=("NATIVE_IMAGE_PDF_OFFICE=PASS" if suite=="image" else
                    "NATIVE_PYINSTALLER_CLI=PASS" if build=="version" else "NATIVE_PYINSTALLER_BUILD_RUN=PASS "+build)
            assert marker in evidence and "NATIVE_IMAGE_PACKAGER_POLICY=PASS "+mode in evidence
            assert pth.read_bytes()==original_pth
            for sentinel in (fixture/"protected-audit.txt",owned/"outside-workspace-audit.txt"):
                assert sentinel.read_bytes()==b"unchanged synthetic sentinel"
            assert not (fixture/"cache/browser").exists()
            print("TARGETED_NATIVE_ACCEPTANCE=PASS "+suite+" "+mode+" "+build,flush=True)

if __name__=="__main__":
    assert len(sys.argv)==4
    native(*sys.argv[1:])
