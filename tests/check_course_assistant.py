"""Native acceptance of actual candidate ZIP, only synthetic loopback content."""
import contextlib
import hashlib
import importlib.util
import http.server
import json
import os
from pathlib import Path
import queue
import random
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import traceback
import uuid
import zipfile

ROOT=Path(__file__).absolute().parents[1]
WIN=Path(os.environ["SystemRoot"])
PS=WIN/"System32/WindowsPowerShell/v1.0/powershell.exe"
CMD=WIN/"System32/cmd.exe"
ROWS=[]
META={}
REPORT=None
PROCS=[]
REQUIRED={"home/skills/course-assistant/SKILL.md","home/skills/course-assistant/agents/openai.yaml",
    "home/skills/course-assistant/references/usage.md","tool/automation/course/course.ps1",
    "tool/automation/course/course.js","tool/automation/course/ocr.ps1","tool/automation/course/path_guard.py",
    "tool/automation/browser-bridge.js","tool/automation/portable-automation.ps1","tool/portable-process.ps1",
    "tool/node/node.exe","tool/python/python.exe","tool/automation/playwright/node_modules/playwright/index.js",
    "tool/automation/playwright/node_modules/playwright-core/lib/coreBundle.js",
    "tool/automation/playwright/node_modules/playwright-core/lib/utilsBundle.js"}


def save():
    REPORT.write_text(json.dumps(dict(metadata=META,rows=ROWS),ensure_ascii=True,indent=2)+"\n",encoding="utf-8")


def row(item,status,detail=""):
    value=dict(item=item,status=status,detail=detail)
    ROWS.append(value);save()
    print("COURSE_AUDIT_ROW="+json.dumps(value,ensure_ascii=True),flush=True)


def plain(p,directory=False):
    s=p.lstat()
    assert not stat.S_ISLNK(s.st_mode) and not getattr(s,"st_file_attributes",0)&0x400
    assert stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode) and s.st_nlink==1


def ancestors(p):
    for q in (*reversed(p.parents),p):plain(q,True)


def digest(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()


def verify(fixture,files,exact=True):
    for name,record in files.items():
        p=fixture/name;ancestors(p.parent);plain(p)
        assert p.stat().st_size==record["size"] and digest(p)==record["sha256"],name
    if exact:assert {p.relative_to(fixture).as_posix() for p in fixture.rglob("*") if p.is_file()}==set(files)


def extract(info,owned):
    archive,mp,sums=[Path(info[k]).absolute() for k in ("archive","manifest","checksums")]
    for p in (archive,mp,sums):
        assert p.is_relative_to(ROOT/"tmp");ancestors(p.parent);plain(p)
    manifest=json.loads(mp.read_bytes());files=manifest["files"]
    assert manifest["source_commit"]==os.environ["GITHUB_SHA"]
    assert manifest["release_version"]=="v0.172.0-portable.2" and manifest["codex_version"]=="0.172.0"
    assert manifest["package_kind"]=="customer" and len(files)==manifest["file_count"]
    assert REQUIRED<=set(files) and len({n.casefold() for n in files})==len(files)
    for name,rec in files.items():
        assert name and "\\" not in name and not name.startswith(("/","tests/",".github/"))
        for part in name.split("/"):
            assert part and part not in {".","..",".git"} and not part.endswith((" ","."))
            assert not re.search(r'[<>:"|?*\x00-\x1f]',part)
            assert not re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?",part)
        if name.split("/")[0] in {"work","tmp","cache","login_json","sqlite","home-runtime"}:
            assert Path(name).name in {".keep",".gitkeep"} and rec["size"]==0
    expected={}
    for line in sums.read_text(encoding="ascii").splitlines():
        h,n=line.split(None,1);assert n not in expected;expected[n]=h
    assert expected=={archive.name:digest(archive),mp.name:digest(mp)}
    assert info["archive_sha256"]==expected[archive.name]
    first=owned/"Initial";first.mkdir()
    with zipfile.ZipFile(archive) as z:
        assert z.namelist()==["Codex/"+n for n in files]
        for entry in z.infolist():
            assert not entry.is_dir() and not entry.flag_bits&1 and stat.S_IFMT(entry.external_attr>>16) in (0,stat.S_IFREG)
            rel=entry.filename[len("Codex/"):];rec=files[rel];assert entry.file_size==rec["size"]
            dst=first/rel;dst.parent.mkdir(parents=True,exist_ok=True)
            with z.open(entry) as src,dst.open("xb") as out:shutil.copyfileobj(src,out)
            assert digest(dst)==rec["sha256"],rel
    verify(first,files)
    fixture=owned/"Portable \u4e2d\u6587 \u7a7a\u683c";first.rename(fixture);assert not first.exists()
    verify(fixture,files)
    versions=json.loads((fixture/"tool/automation/versions.json").read_bytes())
    assert versions["browser"]["payloadBundled"] is True
    assert "tool/automation/"+versions["browser"]["executable"] in files
    META.update(source_commit=manifest["source_commit"],archive_sha256=expected[archive.name],
        manifest_sha256=expected[mp.name],file_count=len(files),browser=versions["browser"]["version"],
        playwright=versions["playwright"],release_version=manifest["release_version"])
    row("candidate actual ZIP, manifest, all hashes and Chinese-space relocation","PASS_ACTUAL")
    META["zip_verified"]=True;save()
    return fixture,files


class Page(http.server.BaseHTTPRequestHandler):
    variants={}
    submitted=[]
    hits=[]
    lock=threading.Lock()
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path!="/course/lesson":self.send_error(404);return
        cookie=self.headers.get("Cookie","")
        with self.lock:
            match=re.search(r"(?:^|;\s*)fixture=([0-9a-f]{32})(?:;|$)",cookie)
            token=match.group(1) if match else uuid.uuid4().hex
            if token not in self.variants:
                v=len(self.variants)+1
                rng=random.Random(int(token,16))
                keys=rng.sample(range(1000,9999),50)
                questions=[]
                for i,key in enumerate(keys):
                    stem=f"Fixture account {v}, code {key}: select matching labels"
                    typ="checkbox" if i%3==0 else "radio"
                    choices=[f"Code {key} option {ch}" for ch in "ABCD"]
                    correct=[choices[0],choices[2]] if typ=="checkbox" else [choices[1]]
                    rng.shuffle(choices)
                    questions.append(dict(stem=stem,type=typ,choices=choices,correct=correct))
                self.variants[token]=dict(account=v,questions=questions)
            data=self.variants[token]
            page_id=uuid.uuid4().hex
            self.hits.append((data["account"],page_id))
        v=data["account"]
        # Only synthetic data; the site fixture owns its clock and auto-submit.
        # The oracle (correct choices) is deliberately NOT sent to the browser.
        questions=[{k:x[k] for k in ("stem","type","choices")} for x in data["questions"]]
        html="""<!doctype html><meta charset="utf-8"><title>Synthetic course</title>
<style>body{font:18px Arial}.question{padding:10px;border-bottom:1px solid #aaa}.question label{display:block}canvas{display:block;margin:8px}#question-scroll{height:380px;overflow:auto}</style>
<article id="lesson"><h1>Synthetic course fixture</h1><p id="page-label">Page 2 of 2</p></article>
<div id="account">Synthetic account ACCOUNT</div><div id="page-instance">PAGE_INSTANCE</div>
<div id="exam">fixture-42</div><span id="total">50</span> questions
<div id="remaining"></div><div id="submitted">Not submitted</div><button id="submit">Submit fixture</button>
<div id="question-scroll"><div id="questions"></div></div>
<canvas id="ocrTable" width="1000" height="360"></canvas><canvas id="ocrZh" width="900" height="180"></canvas>
<script>
const fixtureQuestions=QUESTION_DATA;
const list=document.querySelector("#questions"),view=document.querySelector("#question-scroll");
let next=0;
function add(n){
 for(const q of fixtureQuestions.slice(next,next+n)){
   const section=document.createElement("section");section.className="question";
   const h=document.createElement("h2");h.className="stem";h.textContent=q.stem;section.append(h);
   for(const choice of q.choices){
     const label=document.createElement("label"),input=document.createElement("input");
     input.type=q.type;input.name="q-"+next;label.append(input,document.createTextNode(choice));section.append(label);
   }
   list.append(section);next++;
 }
}
add(20);
view.addEventListener("scroll",()=>{if(next<50&&view.scrollTop+view.clientHeight>=view.scrollHeight-45)add(15)});
let submitted=false;
function submit(){if(submitted)return;submitted=true;document.querySelector("#submitted").innerText="Submitted";fetch("/submit",{method:"POST"})}
document.querySelector("#submit").onclick=submit;
const deadline=Date.now()+3600000;
function tick(){const seconds=Math.max(0,Math.ceil((deadline-Date.now())/1000));document.querySelector("#remaining").innerText=String(seconds);if(!seconds)submit()}
tick();setInterval(tick,250);
const canvas=document.querySelector("#ocrTable"),x=canvas.getContext("2d");
x.fillStyle="white";x.fillRect(0,0,1000,360);x.fillStyle="black";x.font="bold 48px Arial";
for(const [t,a,b] of [["ROW",35,60],["COUNT",300,60],["RATE",650,60],["A",35,130],["1208",300,130],["0.05",650,130],["B",35,200],["70301",300,200],["9007",650,200]])x.fillText(t,a,b);
x.font="36px Arial";x.fillText("SYNTHETIC WATERMARK",35,275);x.fillText("PERSON ID SYNTH-314159",35,335);
const c=document.querySelector("#ocrZh"),z=c.getContext("2d");z.fillStyle="white";z.fillRect(0,0,900,180);z.fillStyle="black";z.font="64px Microsoft YaHei";z.fillText("\u4e2d\u6587\u8bfe\u4ef6 123",20,115);
</script>""".replace("ACCOUNT",str(v)).replace("PAGE_INSTANCE",page_id).replace("QUESTION_DATA",json.dumps(questions,ensure_ascii=True))
        payload=html.encode("utf-8")
        self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Set-Cookie","fixture="+token+"; Path=/; HttpOnly; SameSite=Strict")
        self.send_header("Content-Length",str(len(payload)));self.end_headers();self.wfile.write(payload)
    def do_POST(self):self.submitted.append(self.path);self.send_error(405)


@contextlib.contextmanager
def serve():
    with http.server.ThreadingHTTPServer(("127.0.0.1",0),Page) as s:
        t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
        try:yield "http://127.0.0.1:"+str(s.server_port)
        finally:s.shutdown();t.join(10)


def env(fixture,account):
    out={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","PATHEXT","OS","PROCESSOR_ARCHITECTURE","USERNAME","COMPUTERNAME") if k in os.environ}
    runtime=fixture/"work/course-fixture"/account/"runtime";runtime.mkdir(parents=True,exist_ok=True)
    for k in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","TEMP","TMP","PROGRAMDATA"):out[k]=str(runtime)
    out["PATH"]=str(WIN/"System32");out["PSModuleAnalysisCachePath"]=str(runtime/"ps-module-cache")
    return out


def command(fixture,action,account,*args):
    return [str(PS),"-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",
        str(fixture/"tool/automation/course/course.ps1"),"-Action",action,"-Task","fixture","-Account",account,"-TaskAuthorized",*args]


class Process:
    def __init__(self,fixture,action,account,*args):
        self.p=subprocess.Popen(command(fixture,action,account,*args),cwd=fixture,env=env(fixture,account),
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        PROCS.append(self.p);self.q=queue.Queue();self.errors=[]
        def reader():
            for line in self.p.stdout:self.q.put(line.decode("utf-8","replace").strip())
            self.q.put(None)
        def err():
            for line in self.p.stderr:self.errors.append(line.decode("utf-8","replace")[:300])
        threading.Thread(target=reader,daemon=True).start();threading.Thread(target=err,daemon=True).start()
    def read(self,timeout=180):
        try:v=self.q.get(timeout=timeout)
        except queue.Empty:raise AssertionError("course process deadline")
        assert v is not None,("course process exited",self.p.poll(),self.errors[-5:])
        return v
    def end(self):
        if not self.p.stdin.closed:self.p.stdin.close()
        return self.p.wait(timeout=45)


class Owner(Process):
    def __init__(self,fixture,account,origin,select=False,blank=False):
        args=["-Origin",origin,"-PagePath","/course/lesson"]
        if not blank:args.append("-OpenNonTimedLandingPage")
        if select:args.append("-AllowPracticeSelection")
        super().__init__(fixture,"Owner",account,*args)
        deadline=time.monotonic()+240
        while True:
            v=self.read(max(1,deadline-time.monotonic()))
            if v.startswith("COURSE_SESSION_READY="):self.session=v.split("=",1)[1];break
        assert re.fullmatch("[0-9a-f]{32}",self.session)


class Client(Process):
    def __init__(self,fixture,account,session):
        super().__init__(fixture,"Client",account,"-Session",session)
        self.id=0;self.req("initialize",{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"fixture","version":"1"}})
    def req(self,method,params=None):
        self.id+=1;value={"jsonrpc":"2.0","id":self.id,"method":method}
        if params is not None:value["params"]=params
        self.p.stdin.write((json.dumps(value,ensure_ascii=True)+"\n").encode("ascii"));self.p.stdin.flush()
        r=json.loads(self.read());assert r.get("id")==self.id and "error" not in r,r
        return r["result"]
    def call(self,name,error=False,**args):
        r=self.req("tools/call",{"name":name,"arguments":args})
        assert bool(r.get("isError"))==error,(name,r)
        return r["content"][0]["text"] if error else json.loads(r["content"][0]["text"])


def process_snapshot(fixture):
    # Windows process metadata only. No command lines, browser state or host
    # credentials recorded; compare creation time as well as PID.
    code=("[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false); "
        "@(Get-CimInstance Win32_Process | Where-Object {$null -ne $_.CreationDate} | ForEach-Object { "
        "[pscustomobject]@{pid=[int]$_.ProcessId;parent=[int]$_.ParentProcessId;"
        "name=[string]$_.Name;born=[string]$_.CreationDate.ToUniversalTime().Ticks}}) | ConvertTo-Json -Compress")
    r=subprocess.run([str(PS),"-NoProfile","-NonInteractive","-Command",code],cwd=fixture,
        env=env(fixture,"a"),capture_output=True,timeout=40,check=True)
    return {p["pid"]:p for p in json.loads(r.stdout.decode("utf-8-sig"))}


def descendants(snapshot,pid):
    ids={pid}
    while True:
        nxt=ids|{p for p,x in snapshot.items() if x["parent"] in ids}
        if ids==nxt:break
        ids=nxt
    return {p:snapshot[p] for p in ids if p in snapshot}


def same_processes(old,new):
    return all(pid in new and old[pid]["born"]==new[pid]["born"] for pid in old)


def gone(old,new):
    return all(pid not in new or old[pid]["born"]!=new[pid]["born"] for pid in old)


def wait_gone(fixture,old):
    deadline=time.monotonic()+45
    while True:
        snap=process_snapshot(fixture)
        if gone(old,snap):return snap
        assert time.monotonic()<deadline,"Owned process tree still running"
        time.sleep(.5)


def snapshot_tree(root,limit=50000):
    """Metadata only. Do not follow reparse points or read any host file data."""
    out={};skipped=[];stack=[root]
    while stack:
        p=stack.pop()
        try:s=p.lstat()
        except FileNotFoundError:continue
        except OSError:skipped.append("access");continue
        if getattr(s,"st_file_attributes",0)&0x400 or stat.S_ISLNK(s.st_mode):
            skipped.append("reparse");continue
        if stat.S_ISDIR(s.st_mode):
            try:stack.extend(p.iterdir())
            except OSError:skipped.append("access")
        elif stat.S_ISREG(s.st_mode):
            out[p.relative_to(root).as_posix()]=(s.st_size,s.st_mtime_ns)
            if len(out)>=limit:skipped.append("limit");break
    return out,sorted(set(skipped))


def watched_host():
    # Only targeted cache/temp metadata under the disposable Windows runner.
    # These roots do not establish attribution or exhaustive kernel tracing.
    local=Path(os.environ["LOCALAPPDATA"]);home=Path(os.environ["USERPROFILE"])
    roaming=Path(os.environ["APPDATA"]);temp=Path(os.environ["TEMP"])
    roots={"LocalLow":home/"AppData/LocalLow","LocalLowIntel":home/"AppData/LocalLow/Intel",
        "LocalLowIntelShaderCache":home/"AppData/LocalLow/Intel/ShaderCache","Intel":local/"Intel","ShaderCache":local/"ShaderCache",
        "D3DSCache":local/"D3DSCache","Chrome":local/"Google/Chrome","Chromium":local/"Chromium",
        "CrashDumps":local/"CrashDumps","RoamingChromium":roaming/"Chromium","HostTEMP":temp}
    return {k:snapshot_tree(p) for k,p in roots.items()}


def differences(before,after):
    out={}
    for label,(old,skipped) in before.items():
        new,skipped2=after[label]
        changed={n for n in new if n not in old or new[n]!=old[n]}
        removed=set(old)-set(new)
        # No host filenames, content or full user paths written to the report.
        out[label]={"new_or_changed":len(changed),"removed":len(removed),"before":len(old),"after":len(new),
            "incomplete":sorted(set(skipped+skipped2))}
    return out


def local_inventory(fixture):
    state=fixture/"work/course-fixture"
    report={}
    for account in ("a","b"):
        base=state/account
        for label in ("profile","cache","crashes","downloads","runtime","tmp","notes"):
            files,skipped=snapshot_tree(base/label)
            report[account+"/"+label]={"files":len(files),"bytes":sum(v[0] for v in files.values()),"incomplete":skipped,
                "gpu_or_shader":sum(bool(re.search(r"gpu|shader|intel|localLow",n,re.I)) for n in files),
                "logs":sum(bool(re.search(r"\.log$|(?:^|/)logs?(?:/|$)",n,re.I)) for n in files),
                "screenshots":sum(bool(re.search(r"\.(png|jpg|jpeg|webp)$",n,re.I)) for n in files),
                "cache_location_sample":sorted({n.split("/")[0] for n in files if re.search(r"gpu|shader|intel|localLow|cache|\.log$",n,re.I)})[:30]}
    return report


QA=dict(questionSelector=".question",stemSelector=".stem")
PROGRESS={**QA,"totalSelector":"#total","timerSelector":"#remaining","pendingSelector":"#submitted","pendingText":"Not submitted","expectedTotal":50}


def all_questions(client):
    first=client.call("course_questions",**QA);assert first["renderedCount"]==20
    counts=[20]
    for _ in range(100):
        client.call("course_scroll",selector="#question-scroll",pixels=1200)
        time.sleep(.06)
        result=client.call("course_questions",**QA)
        n=result["renderedCount"]
        if n!=counts[-1]:
            assert n>counts[-1];counts.append(n)
        if n==50:break
    assert counts==[20,35,50] and result["renderedCount"]==50,counts
    assert len({q["fingerprint"] for q in result["questions"]})==50
    return result["questions"],counts


def account_oracle(client):
    account=int(client.call("course_read",selector="#account")["text"].split()[-1])
    matches=[x for x in Page.variants.values() if x["account"]==account]
    assert len(matches)==1
    return account,{x["stem"]:x for x in matches[0]["questions"]}


def answer(client,questions,oracle):
    assert len(questions)==len(oracle)==50
    seen=set()
    for q in questions:
        expected=oracle[q["stem"]]
        assert q["type"]==expected["type"] and q["choices"]==expected["choices"]
        assert q["fingerprint"] not in seen;seen.add(q["fingerprint"])
        want=expected["correct"]
        if q["type"]=="checkbox" and not any(x.startswith("multi-") for x in seen):
            # Prove both incomplete and extra selections are corrected, not
            # just that two correct boxes can be checked in an empty group.
            client.call("course_select",**QA,fingerprint=q["fingerprint"],choices=want[:1],confirmed=True)
            extra=next(x for x in q["choices"] if x not in want)
            result=client.call("course_select",**QA,fingerprint=q["fingerprint"],choices=[*want,extra],confirmed=True)
            assert sorted(result["selected"])==sorted([*want,extra])
            seen.add("multi-correction")
        final=client.call("course_select",**QA,fingerprint=q["fingerprint"],choices=want,confirmed=True)
        assert final["fingerprint"]==q["fingerprint"] and sorted(final["selected"])==sorted(want)
    assert "multi-correction" in seen
    return verify_answers(client,oracle)


def verify_answers(client,oracle):
    result=client.call("course_questions",**QA)
    assert result["renderedCount"]==len(oracle)==50
    actual={}
    for q in result["questions"]:
        expect=oracle[q["stem"]]
        assert q["choices"]==expect["choices"] and sorted(q["selected"])==sorted(expect["correct"])
        actual[q["fingerprint"]]=sorted(q["selected"])
    assert len(actual)==50
    status=client.call("course_progress",**PROGRESS)
    assert status["answered"]==status["rendered"]==status["total"]==50 and status["pending"]
    assert status["status"]=="\u5df2\u7b54 50/50\uff0c\u5f85\u4ea4\u5377"
    assert status["siteTimer"].isdigit() and int(status["siteTimer"])>0
    return actual,status


def ocr_notes(fixture,a,b):
    # OCR provenance and numerical output must come from the image, not an
    # embedded text answer. The test oracle only verifies the actual output.
    zh=a.call("course_ocr_check",language="zh-Hans-CN")
    assert isinstance(zh["supported"],bool) and isinstance(zh["zhHansSupported"],bool)
    if zh["supported"]:
        r=a.call("course_ocr",selector="#ocrZh",pageSelector="#page-label",language="zh-Hans-CN")
        assert "\u4e2d\u6587" in re.sub(r"\s+","",r["text"]) and "123" in r["text"]
        assert r["source"]["pageLabel"]=="Page 2 of 2" and r["lines"]
        row("actual Chinese Windows OCR, page provenance","PASS_ACTUAL",r["actualLanguage"])
    else:
        r=a.call("course_ocr",selector="#ocrZh",pageSelector="#page-label",language="zh-Hans-CN")
        assert r["supported"] is False and r["text"] is None
        row("actual Chinese Windows OCR","BLOCKED_LANGUAGE_MISSING","zh-Hans-CN unavailable; no install/fallback")
    en=a.call("course_ocr_check",language="en-US")
    if en["supported"]:
        o=a.call("course_ocr",selector="#ocrTable",pageSelector="#page-label",language="en-US")
        assert o["source"]["pageLabel"]=="Page 2 of 2" and o["source"]["imageSelector"]=="#ocrTable"
        assert o["source"]["bindingId"]==a.call("course_status")["bindingId"]
        assert a.call("course_read",selector="#page-label")["text"]==o["source"]["pageLabel"]
        words=[w for line in o["lines"] for w in line["words"]]
        assert words and all(w["width"]>0 and w["height"]>0 for w in words)
        expected={"1208":(300,130),"0.05":(650,130),"70301":(300,200),"9007":(650,200)}
        found={}
        for value,(x,y) in expected.items():
            matches=[w for w in words if w["text"]==value and abs(w["x"]-x)<55 and abs(w["y"]-y)<85]
            assert len(matches)==1,(value,[(w["text"],w["x"],w["y"]) for w in words])
            found[value]=matches[0]
        compact=lambda s:re.sub(r"[^a-z0-9]","",s.lower())
        exclusions=["SYNTHETIC WATERMARK","SYNTH-314159"]
        assert all(compact(x) in compact(o["text"]) for x in exclusions),"OCR did not actually see watermark/identifier fixture"
        lines=["# Synthetic reviewed lesson","",f"Source: {o['source']['pageLabel']}, {o['source']['imageSelector']}","","| Row | Count | Rate |","|---|---:|---:|",
            "| A | "+found["1208"]["text"]+" | "+found["0.05"]["text"]+" |","| B | "+found["70301"]["text"]+" | "+found["9007"]["text"]+" |",
            "","## Source index"]
        for k in expected:
            w=found[k];lines.append(f"- {w['text']}: page 2, image #ocrTable, x={w['x']:.0f}, y={w['y']:.0f}")
        md="\n".join(lines)+"\n"
        a.call("course_save_notes",error=True,slug="raw",markdown="# "+o["text"],excludedText=exclusions,confirmed=True)
        n=a.call("course_save_notes",slug="lesson",markdown=md,excludedText=exclusions,confirmed=True)
        p=fixture/"work/course-fixture/a"/n["saved"];content=p.read_text(encoding="utf-8")
        assert content==md and all(compact(x) not in compact(content) for x in exclusions)
        assert all(k in content for k in expected) and "Page 2 of 2" in content
        row("OCR actual numerical table, source page/word coordinates, watermark/identifier exclusion in Markdown","PASS_ACTUAL",
            "four verified values; both synthetic identifiers present in OCR and absent from saved note")
    else:
        row("OCR numerical table and redaction","BLOCKED_LANGUAGE_MISSING","English engine unavailable; no image recognition claim")
        n=a.call("course_save_notes",slug="lesson",markdown="# Synthetic note\n\nPage 2\n",excludedText=[],confirmed=True)
        p=fixture/"work/course-fixture/a"/n["saved"]
    a.call("course_save_notes",error=True,slug="lesson",markdown="# replacement",excludedText=[],confirmed=True)
    a.call("course_save_notes",error=True,slug="bad",markdown="# Link https://example.invalid/a?signature=synthetic",excludedText=[],confirmed=True)
    note_b=b.call("course_save_notes",slug="retain",markdown="# Synthetic B retained note\n\nPage 2\n",excludedText=[],confirmed=True)
    pb=fixture/"work/course-fixture/b"/note_b["saved"]
    for language in ("mi-NZ","zu-ZA","mt-MT","ga-IE"):
        missing=a.call("course_ocr_check",language=language)
        if not missing["supported"]:break
    assert not missing["supported"] and a.call("course_ocr",selector="#ocrZh",pageSelector="#page-label",language=language)["text"] is None
    assert not list((fixture/"work/course-fixture/a/tmp").glob("ocr-*.png"))
    row("missing OCR language refusal and temporary image cleanup","PASS_ACTUAL",language)
    return {p:digest(p),pb:digest(pb)}


def package_nonaccount(fixture):
    files,skipped=snapshot_tree(fixture)
    return {"package_outside_course_accounts":({n:v for n,v in files.items() if not n.startswith(("work/course-fixture/a/","work/course-fixture/b/"))},skipped)}


def native_codex_course(fixture,session,binding):
    # Reuse the accepted native Responses peer. The tested BAT/Codex and
    # MCP entry are always from the exact relocated candidate ZIP.
    helper=ROOT/"tests/check_codex_browser_mcp.py"
    spec=importlib.util.spec_from_file_location("candidate_course_native_peer",helper)
    peer=importlib.util.module_from_spec(spec);spec.loader.exec_module(peer)
    store=fixture/"home/portable-extensions.toml"
    config=fixture/"env.local.ps1"
    assert not store.exists() and not config.exists()
    lines=["[mcp_servers.course_a]","command = "+json.dumps(str(PS)),
        "args = "+json.dumps(["-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",
            str(fixture/"tool/automation/course/course.ps1"),"-Action","Client","-Task","fixture","-Account","a","-TaskAuthorized","-Session",session]),
        "cwd = "+json.dumps(str(fixture/"work")),"startup_timeout_sec = 120","tool_timeout_sec = 120",
        "supports_parallel_tool_calls = false","required = true",'default_tools_approval_mode = "approve"']
    store.write_text("\n".join(lines)+"\n",encoding="utf-8")
    initial_store=digest(store)
    model="gpt-6-sol"
    for mode,bat in (("normal","\u542f\u52a8Codex.bat"),("maintenance","\u542f\u52a8Codex-\u7ef4\u62a4\u6a21\u5f0f.bat")):
        peer.MODEL_REQUESTS.clear();peer.MODEL_ERRORS.clear()
        def handler(body,_):
            if len(peer.MODEL_REQUESTS)==1:
                assert "course-assistant" in json.dumps({"instructions":body.get("instructions"),"input":body.get("input")},ensure_ascii=False)
                entries=list(peer.tool_entries(body.get("tools",[])))
                custom=next(((ns,t) for ns,t in entries if t.get("type")=="custom" and t.get("name")=="exec"),None)
                if custom:
                    ns,t=custom
                    code=('const t=ALL_TOOLS.find(x=>x.name.includes("course_a")&&x.name.endsWith("course_status"));'
                          'if(!t)throw new Error("course MCP missing");const r=await tools[t.name]({});'
                          'if(r.isError)throw new Error("course status failed");text(JSON.stringify(r));')
                    item={"type":"custom_tool_call","call_id":"native-course","name":t["name"],"input":code}
                else:
                    ns,t=next((ns,t) for ns,t in entries if t.get("type")=="function" and "course_a" in str(ns)+str(t.get("name")) and t["name"].endswith("course_status"))
                    item={"type":"function_call","call_id":"native-course","name":t["name"],"arguments":"{}"}
                if ns is not None:item["namespace"]=ns
                return item
            output=peer.call_output(body,"native-course")
            assert output and binding in json.dumps(output),"actual MCP result did not return same owner binding"
            return {"id":"msg_course","type":"message","role":"assistant","status":"completed",
                "content":[{"type":"output_text","text":"native-course-reconnect-ok","annotations":[]}]}
        with peer.serving(peer.provider("",model=model,handler=handler)) as port:
            config.write_text('$env:CODEX_AUTH_MODE = "api"\n$env:CODEX_PORTABLE_ALLOW_USER_MCP = "true"\n'
                '$env:CODEX_PROXY_ENABLED = "false"\n$env:CODEX_DISABLE_WEBSOCKET = "true"\n'
                f'$env:CODEX_MODEL = "{model}"\n$env:CODEX_BASE_URL = "http://127.0.0.1:{port}/v1"\n'
                '$env:OPENAI_API_KEY = "synthetic-offline-not-a-real-key"\n',encoding="utf-8")
            base_env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","PATHEXT","OS","PROCESSOR_ARCHITECTURE","USERNAME","COMPUTERNAME") if k in os.environ}
            base_env["PATH"]=str(WIN/"System32")
            command_line='"'+str(CMD)+'" /d /s /c "'+subprocess.list2cmdline([str(fixture/bat),"--portable-auth=api","--portable-extensions","exec","--skip-git-repo-check","--json","Read authorized synthetic course session status"])+'"'
            p=subprocess.Popen(command_line,executable=str(CMD),cwd=fixture,env=base_env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            PROCS.append(p)
            try:out,err=p.communicate(timeout=360)
            except subprocess.TimeoutExpired:
                subprocess.run([str(WIN/"System32/taskkill.exe"),"/PID",str(p.pid),"/T","/F"],capture_output=True,timeout=30,check=False)
                p.communicate(timeout=30);raise
            # Do not persist raw request bodies, session capabilities or page data.
            assert p.returncode==0 and not peer.MODEL_ERRORS and b"native-course-reconnect-ok" in out,("native Codex course MCP",mode,p.returncode,peer.MODEL_ERRORS)
            assert len(peer.MODEL_REQUESTS)==2 and digest(store)==initial_store
            import tomllib
            cfg=tomllib.loads((fixture/"home/config.toml").read_text(encoding="utf-8-sig"))
            assert "course_a" in cfg["mcp_servers"] and cfg["sandbox_mode"]=="workspace-write"
            assert cfg["approval_policy"]=="on-request"
        row("actual native Codex opt-in course MCP reconnect ("+mode+")","PASS_ACTUAL","same binding; no global registration or policy change")


def native(fixture,origin):
    before_host=watched_host();before_package=package_nonaccount(fixture)
    oa=Owner(fixture,"a",origin,True);a=Client(fixture,"a",oa.session)
    names={t["name"] for t in a.req("tools/list")["tools"]}
    assert not any("submit" in n or "navigate" in n or "evaluate" in n for n in names)
    assert a.call("course_status")["account"]=="a"
    bind_a=a.call("course_bind",confirmed=True)["bindingId"]
    same=subprocess.run(command(fixture,"Owner","a","-Origin",origin,"-PagePath","/course/lesson"),cwd=fixture,env=env(fixture,"a"),capture_output=True,timeout=45)
    assert same.returncode!=0
    ob=Owner(fixture,"b",origin,True);b=Client(fixture,"b",ob.session)
    bind_b=b.call("course_bind",confirmed=True)["bindingId"]
    assert bind_a!=bind_b and oa.session!=ob.session
    assert a.call("course_read",selector="#exam")==b.call("course_read",selector="#exam") and len(Page.variants)==2
    acct_a,oracle_a=account_oracle(a);acct_b,oracle_b=account_oracle(b)
    assert acct_a!=acct_b and set(oracle_a).isdisjoint(oracle_b)
    qa,counts_a=all_questions(a);qb,counts_b=all_questions(b)
    a.call("course_select",error=True,**QA,fingerprint=qb[0]["fingerprint"],choices=[qb[0]["choices"][0]],confirmed=True)
    row("two actual independent cookie sessions, same exam ID, 20/35/50 lazy batches and profile lock","PASS_ACTUAL",
        json.dumps({"a":counts_a,"b":counts_b}))
    selected_a,pa=answer(a,qa,oracle_a);selected_b,pb=answer(b,qb,oracle_b)
    assert set(selected_a).isdisjoint(selected_b) and not Page.submitted
    row("both actual 50-question papers verified by stem/options, corrected missing/extra multi-selection","PASS_ACTUAL",
        json.dumps({"a":pa,"b":pb},ensure_ascii=True))
    notes=ocr_notes(fixture,a,b)
    page_a=a.call("course_read",selector="#page-instance")["text"];page_b=b.call("course_read",selector="#page-instance")["text"]
    old_hits=list(Page.hits)
    # Actual Windows process termination, not closing a Python stdin facade.
    snap=process_snapshot(fixture)
    owner_a=descendants(snap,oa.p.pid);owner_b=descendants(snap,ob.p.pid)
    client_a=descendants(snap,a.p.pid)
    assert any(x["name"].lower()=="chrome.exe" for x in owner_a.values())
    assert any(x["name"].lower()=="chrome.exe" for x in owner_b.values())
    assert any(x["name"].lower()=="node.exe" for x in client_a.values())
    assert set(client_a).isdisjoint(owner_a) and set(client_a).isdisjoint(owner_b)
    timer_a=int(a.call("course_progress",**PROGRESS)["siteTimer"])
    timer_b=int(b.call("course_progress",**PROGRESS)["siteTimer"])
    subprocess.run([str(WIN/"System32/taskkill.exe"),"/PID",str(a.p.pid),"/T","/F"],capture_output=True,timeout=30,check=True)
    assert a.p.wait(timeout=45)!=0
    snap=wait_gone(fixture,client_a)
    # Some Chromium utility processes can churn independently; require the
    # original owner wrapper and actual Chrome browser root to survive.
    root_a={p:x for p,x in owner_a.items() if p==oa.p.pid or x["name"].lower()=="chrome.exe" and owner_a.get(x["parent"],{}).get("name","").lower()!="chrome.exe"}
    root_b={p:x for p,x in owner_b.items() if p==ob.p.pid or x["name"].lower()=="chrome.exe" and owner_b.get(x["parent"],{}).get("name","").lower()!="chrome.exe"}
    assert same_processes(root_a,snap) and same_processes(root_b,snap)
    time.sleep(2.2)
    a=Client(fixture,"a",oa.session)
    assert a.call("course_status")["bindingId"]==bind_a and b.call("course_status")["bindingId"]==bind_b
    assert a.call("course_read",selector="#page-instance")["text"]==page_a and b.call("course_read",selector="#page-instance")["text"]==page_b
    assert account_oracle(a)[0]==acct_a and account_oracle(b)[0]==acct_b
    ra,pa2=verify_answers(a,oracle_a);rb,pb2=verify_answers(b,oracle_b)
    assert ra==selected_a and rb==selected_b and int(pa2["siteTimer"])<timer_a and int(pb2["siteTimer"])<timer_b
    assert Page.hits==old_hits and not Page.submitted
    row("killed real MCP client process tree, reconnected same bound page and both 50/50 states with site clocks running","PASS_ACTUAL",
        json.dumps({"terminated_processes":len(client_a),"same_owner_roots":len(root_a)+len(root_b),
            "page_requests_unchanged":True,"a_timer":[timer_a,int(pa2["siteTimer"])],"b_timer":[timer_b,int(pb2["siteTimer"])]}))
    # Reject cross-account session and cleanup while B is still running.
    wrong=subprocess.run(command(fixture,"Client","b","-Session",oa.session),cwd=fixture,env=env(fixture,"b"),capture_output=True,timeout=60)
    assert wrong.returncode!=0
    running_clean=subprocess.run(command(fixture,"Clean","b","-CleanupAuthorized"),cwd=fixture,env=env(fixture,"b"),capture_output=True,timeout=60)
    assert running_clean.returncode!=0
    inventory_before=local_inventory(fixture);host_active=watched_host()
    snap=process_snapshot(fixture);old_b={**descendants(snap,ob.p.pid),**descendants(snap,b.p.pid)}
    b.call("course_close",confirmed=True);b.end();assert ob.p.wait(timeout=60)==0
    snap=wait_gone(fixture,old_b);assert same_processes(root_a,snap)
    clean=subprocess.run(command(fixture,"Clean","b","-CleanupAuthorized"),cwd=fixture,env=env(fixture,"b"),capture_output=True,timeout=150,check=True)
    assert b"COURSE_ACCOUNT_CLEANED=PASS" in clean.stdout
    state_b=fixture/"work/course-fixture/b"
    for name in ("profile","cache","crashes","downloads","runtime","tmp"):
        assert not (state_b/name).exists(),name
    assert all(digest(p)==v for p,v in notes.items())
    assert verify_answers(a,oracle_a)[0]==selected_a and a.call("course_status")["bindingId"]==bind_a
    assert a.call("course_read",selector="#page-instance")["text"]==page_a
    assert Page.hits==old_hits
    inventory_after_clean=local_inventory(fixture);host_cleaned=watched_host()
    # Same entry, no landing option: truly blank window after cleanup.
    fresh=Owner(fixture,"b",origin,blank=True);c=Client(fixture,"b",fresh.session)
    assert fresh.session!=ob.session and c.call("course_status")["blank"] and not c.call("course_status")["bound"]
    c.call("course_bind",error=True,confirmed=True)
    assert Page.hits==old_hits
    c.call("course_close",confirmed=True);c.end();assert fresh.p.wait(timeout=60)==0
    # Reopen a known NON-timed local fixture URL only in this synthetic test.
    # Its fresh cookie must be distinct from both prior simulated accounts.
    fresh2=Owner(fixture,"b",origin,blank=False);c=Client(fixture,"b",fresh2.session);c.call("course_bind",confirmed=True)
    assert account_oracle(c)[0] not in {acct_a,acct_b} and len(Page.variants)==3
    readonly=c.call("course_questions",**QA)["questions"][0]
    c.call("course_select",error=True,**QA,fingerprint=readonly["fingerprint"],choices=[readonly["choices"][0]],confirmed=True)
    c.call("course_close",confirmed=True);c.end();assert fresh2.p.wait(timeout=60)==0
    assert verify_answers(a,oracle_a)[0]==selected_a and all(digest(p)==v for p,v in notes.items())
    assert not Page.submitted
    row("closed B only, verified its owned processes exited, explicitly cleaned, fresh blank then new login identity","PASS_ACTUAL",
        "A retained page/answers; both Markdown digests unchanged")
    row("actual account-local profile/cache/TEMP/logs/screenshots inventory","OBSERVED",
        json.dumps({"before_B_cleanup":inventory_before,"after_B_cleanup":inventory_after_clean},ensure_ascii=True))
    row("host cache/temp metadata observation, no host cleanup","OBSERVED",
        json.dumps({"while_live":differences(before_host,host_active),"after_B_cleanup":differences(before_host,host_cleaned)},ensure_ascii=True))
    outside=differences(before_package,package_nonaccount(fixture))["package_outside_course_accounts"]
    row("package write observation outside both account trees","PASS_ACTUAL" if not outside["new_or_changed"] and not outside["removed"] and not outside["incomplete"] else "FAIL",
        json.dumps(outside))
    assert not outside["new_or_changed"] and not outside["removed"] and not outside["incomplete"]
    # A actual Codex client reconnect also must leave its existing page intact.
    assert a.end()==0
    prior_hits=list(Page.hits)
    native_codex_course(fixture,oa.session,bind_a)
    a=Client(fixture,"a",oa.session)
    assert a.call("course_status")["bindingId"]==bind_a and verify_answers(a,oracle_a)[0]==selected_a and Page.hits==prior_hits
    a.call("course_close",confirmed=True);a.end();assert oa.p.wait(timeout=60)==0
    assert not Page.submitted
    row("no tool-driven or premature site submission","PASS_ACTUAL")


def boundary(fixture,origin):
    guard=fixture/"tool/automation/course/path_guard.py";python=fixture/"tool/python/python.exe";e=env(fixture,"a")
    note=fixture/"work/course-fixture/a/notes/course-lesson.md"
    subprocess.run([str(python),"-I","-B",str(guard),"file",str(note)],cwd=fixture,env=e,check=True,timeout=30)
    target=fixture/"work/owned-target";target.mkdir();marker=target/"sentinel.txt";marker.write_text("keep")
    link=fixture/"work/course-fixture/linked"
    subprocess.run([str(CMD),"/d","/c","mklink","/J",str(link),str(target)],cwd=fixture,env=e,check=True,capture_output=True,timeout=30)
    try:
        assert subprocess.run([str(python),"-I","-B",str(guard),"tree",str(link)],cwd=fixture,env=e,capture_output=True,timeout=30).returncode!=0
        assert subprocess.run(command(fixture,"Owner","linked","-Origin",origin,"-PagePath","/course/lesson"),cwd=fixture,env=e,capture_output=True,timeout=30).returncode!=0
        assert marker.read_text()=="keep"
    finally:os.rmdir(link)
    assert subprocess.run([str(python),"-I","-B",str(guard),"file",str(ROOT/"README.md")],cwd=fixture,env=e,capture_output=True,timeout=30).returncode!=0
    row("bundled Python, junction and actual outside-package path refusal","PASS_ACTUAL")


def main():
    global REPORT
    assert os.name=="nt" and os.environ.get("GITHUB_REPOSITORY")=="rileyaaa/Portable"
    assert os.environ.get("GITHUB_REF")=="refs/heads/dev/stable-tool-refresh"
    assert Path(sys.executable).resolve()==(ROOT/"tool/python/python.exe").resolve()
    assert len(sys.argv)==3;REPORT=Path(sys.argv[2]).absolute()
    info=json.loads(Path(sys.argv[1]).read_bytes())
    owned=ROOT/"tmp"/("course-native-"+uuid.uuid4().hex);ancestors(owned.parent);owned.mkdir()
    try:
        fixture,files=extract(info,owned)
        with serve() as origin:native(fixture,origin);boundary(fixture,origin)
        verify(fixture,files,exact=False)
        row("original candidate member bytes unchanged after runtime","PASS_ACTUAL")
        META["completed"]=True;save()
    except Exception:
        row("course native harness","FAIL",traceback.format_exc()[-8000:]);return 1
    finally:
        for p in reversed(PROCS):
            if p.poll() is None:
                subprocess.run([str(WIN/"System32/taskkill.exe"),"/PID",str(p.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,check=False)
                p.wait(timeout=30)
        if owned.exists():shutil.rmtree(owned)
    return 0


if __name__=="__main__":
    for stream in (sys.stdout,sys.stderr):stream.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
