"""Exercise the real interactive BAT/client path in an owned Windows pseudoconsole.

Called only by test_launcher_smoke.ps1 with its synthetic relocated package.
Never uses a real account or submits a model prompt.
"""
import ctypes
import codecs
import unicodedata
from ctypes import wintypes as W
import os
import re
from pathlib import Path
import sys
import threading
import time


class Screen:
    """Small VT screen for ConPTY differential redraws and cursor reports."""
    def __init__(self, report):
        self.rows=[[' ']*120 for _ in range(35)]
        self.x=self.y=0; self.pending=''; self.report=report
    def feed(self, text):
        text=self.pending+text; self.pending=''; i=0
        while i<len(text):
            c=text[i]
            if c=='\x1b':
                if i+1==len(text): break
                if text[i+1]=='[':
                    m=re.match(r'\x1b\[([0-?]*)[ -/]*([@-~])',text[i:])
                    if not m: break
                    raw,op=m.groups(); nums=[int(n or '0') for n in raw.split(';')] if not raw.startswith(('?','>','<','=')) else []
                    n=(nums[0] if nums else 0) or 1
                    if op in ('H','f'):
                        self.y=min(34,max(0,(nums[0] or 1)-1)) if nums else 0
                        self.x=min(119,max(0,((nums[1] if len(nums)>1 else 1) or 1)-1))
                    elif op=='A': self.y=max(0,self.y-n)
                    elif op=='B': self.y=min(34,self.y+n)
                    elif op=='C': self.x=min(119,self.x+n)
                    elif op=='D': self.x=max(0,self.x-n)
                    elif op=='G': self.x=min(119,n-1)
                    elif op=='J' and nums and nums[0] in (2,3): self.rows=[[' ']*120 for _ in range(35)]
                    elif op=='K':
                        mode=nums[0] if nums else 0
                        a,b=(0,120) if mode==2 else ((0,self.x+1) if mode==1 else (self.x,120))
                        self.rows[self.y][a:b]=[' ']*(b-a)
                    elif op=='n' and nums==[6]: self.report(self.y+1,self.x+1)
                    i+=len(m.group()); continue
                if text[i+1]==']':
                    bel=text.find('\x07',i+2); st=text.find('\x1b\\',i+2)
                    ends=[(n,k) for n,k in ((bel,1),(st,2)) if n>=0]
                    if not ends: break
                    end,k=min(ends);i=end+k;continue
                i+=2;continue
            if c=='\r': self.x=0
            elif c=='\n': self.y+=1
            elif c=='\b': self.x=max(0,self.x-1)
            elif c=='\t': self.x=min(119,(self.x//8+1)*8)
            elif ord(c)>=32:
                if self.x>=120: self.x=0;self.y+=1
                if self.y>=35: self.rows.pop(0);self.rows.append([' ']*120);self.y=34
                if not unicodedata.combining(c):
                    self.rows[self.y][self.x]=c
                    self.x+=2 if unicodedata.east_asian_width(c) in ('W','F') else 1
            if self.y>=35: self.rows.pop(0);self.rows.append([' ']*120);self.y=34
            i+=1
        self.pending=text[i:]
    def text(self): return '\n'.join(''.join(row) for row in self.rows)


def main():
    if os.name != 'nt':
        raise SystemExit('Windows ConPTY is required')
    root = Path(sys.argv[1]).absolute()
    bat = root / sys.argv[2]
    if not bat.is_file() or not (root / 'env.local.ps1').is_file():
        raise SystemExit('Synthetic launcher fixture is missing')
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    HANDLE = W.HANDLE
    SIZE = ctypes.c_size_t
    class COORD(ctypes.Structure):
        _fields_ = [('X', ctypes.c_short), ('Y', ctypes.c_short)]
    class SI(ctypes.Structure):
        _fields_ = [('cb',W.DWORD),('reserved',W.LPWSTR),('desktop',W.LPWSTR),('title',W.LPWSTR),
                    ('x',W.DWORD),('y',W.DWORD),('xs',W.DWORD),('ys',W.DWORD),('xc',W.DWORD),('yc',W.DWORD),
                    ('fill',W.DWORD),('flags',W.DWORD),('show',W.WORD),('count',W.WORD),('bytes',ctypes.c_void_p),
                    ('stdin',HANDLE),('stdout',HANDLE),('stderr',HANDLE)]
    class SIX(ctypes.Structure):
        _fields_ = [('si',SI),('attrs',ctypes.c_void_p)]
    class PI(ctypes.Structure):
        _fields_ = [('process',HANDLE),('thread',HANDLE),('pid',W.DWORD),('tid',W.DWORD)]
    prototypes = {
        'CreatePipe':([ctypes.POINTER(HANDLE),ctypes.POINTER(HANDLE),ctypes.c_void_p,W.DWORD],W.BOOL),
        'CreatePseudoConsole':([COORD,HANDLE,HANDLE,W.DWORD,ctypes.POINTER(HANDLE)],ctypes.c_long),
        'ClosePseudoConsole':([HANDLE],None),
        'InitializeProcThreadAttributeList':([ctypes.c_void_p,W.DWORD,W.DWORD,ctypes.POINTER(SIZE)],W.BOOL),
        'UpdateProcThreadAttribute':([ctypes.c_void_p,W.DWORD,SIZE,ctypes.c_void_p,SIZE,ctypes.c_void_p,ctypes.c_void_p],W.BOOL),
        'DeleteProcThreadAttributeList':([ctypes.c_void_p],None),
        'CreateProcessW':([W.LPCWSTR,W.LPWSTR,ctypes.c_void_p,ctypes.c_void_p,W.BOOL,W.DWORD,ctypes.c_void_p,W.LPCWSTR,ctypes.POINTER(SIX),ctypes.POINTER(PI)],W.BOOL),
        'CreateJobObjectW':([ctypes.c_void_p,W.LPCWSTR],HANDLE),
        'AssignProcessToJobObject':([HANDLE,HANDLE],W.BOOL),
        'TerminateJobObject':([HANDLE,W.UINT],W.BOOL),
        'TerminateProcess':([HANDLE,W.UINT],W.BOOL),
        'ResumeThread':([HANDLE],W.DWORD),
        'WaitForSingleObject':([HANDLE,W.DWORD],W.DWORD),
        'ReadFile':([HANDLE,ctypes.c_void_p,W.DWORD,ctypes.POINTER(W.DWORD),ctypes.c_void_p],W.BOOL),
        'WriteFile':([HANDLE,ctypes.c_void_p,W.DWORD,ctypes.POINTER(W.DWORD),ctypes.c_void_p],W.BOOL),
        'CloseHandle':([HANDLE],W.BOOL),
    }
    for name,(args,result) in prototypes.items():
        fn=getattr(k,name);fn.argtypes=args;fn.restype=result
    def check(ok):
        if not ok: raise ctypes.WinError(ctypes.get_last_error())
    handles=[]; console=HANDLE(); pi=PI(); attrs=None; initialized=False; reader=None
    output=bytearray(); ready=threading.Event(); writer_lock=threading.Lock()
    def write(data):
        with writer_lock:
            count=W.DWORD(); check(k.WriteFile(input_write,data,len(data),ctypes.byref(count),None))
    try:
        input_read,input_write,output_read,output_write=[HANDLE() for _ in range(4)]
        check(k.CreatePipe(ctypes.byref(input_read),ctypes.byref(input_write),None,0));handles.extend([input_read,input_write])
        check(k.CreatePipe(ctypes.byref(output_read),ctypes.byref(output_write),None,0));handles.extend([output_read,output_write])
        hr=k.CreatePseudoConsole(COORD(120,35),input_read,output_write,0,ctypes.byref(console))
        if hr != 0: raise OSError('CreatePseudoConsole HRESULT='+hex(hr & 0xffffffff))
        # The pseudoconsole owns the server ends now.
        for h in (input_read,output_write): k.CloseHandle(h);handles.remove(h)
        def drain():
            buf=ctypes.create_string_buffer(8192);count=W.DWORD()
            trusted=False
            decoder=codecs.getincrementaldecoder('utf-8')(errors='replace')
            screen=Screen(lambda y,x:write(('\x1b[%d;%dR'%(y,x)).encode('ascii')))
            while k.ReadFile(output_read,buf,len(buf),ctypes.byref(count),None) and count.value:
                block=buf.raw[:count.value];output.extend(block)
                # Answer VT cursor-position queries so terminal probing is real.
                screen.feed(decoder.decode(block))
                plain=screen.text()
                if not trusted and ('Do you trust' in plain or 'Yes, I trust' in plain):
                    trusted=True
                    try: write(b'\r')
                    except OSError: pass
                if 'OpenAI Codex' in plain and 'model:' in plain and 'directory:' in plain: ready.set()
        reader=threading.Thread(target=drain,daemon=True);reader.start()
        size=SIZE();k.InitializeProcThreadAttributeList(None,1,0,ctypes.byref(size))
        attrs=ctypes.create_string_buffer(size.value)
        check(k.InitializeProcThreadAttributeList(attrs,1,0,ctypes.byref(size)));initialized=True
        check(k.UpdateProcThreadAttribute(attrs,0,0x00020016,console,SIZE(ctypes.sizeof(HANDLE)),None,None))
        si=SIX();si.si.cb=ctypes.sizeof(si);si.attrs=ctypes.cast(attrs,ctypes.c_void_p)
        # Reopen stdio on the attached pseudoconsole, not the CI host pipes.
        command=ctypes.create_unicode_buffer('"'+os.environ['SystemRoot']+'\\System32\\cmd.exe" /d /s /c ""'+str(bat)+'" <CONIN$ >CONOUT$ 2>&1"')
        job=k.CreateJobObjectW(None,None);check(job);handles.append(job)
        check(k.CreateProcessW(None,command,None,None,False,0x00080000|0x00000004,None,str(root),ctypes.byref(si),ctypes.byref(pi)))
        handles.extend([pi.process,pi.thread])
        check(k.AssignProcessToJobObject(job,pi.process))
        if k.ResumeThread(pi.thread)==0xffffffff: check(False)
        deadline=time.monotonic()+180
        while time.monotonic()<deadline and not ready.wait(.1):
            if k.WaitForSingleObject(pi.process,0)==0: break
        # Output contains only synthetic fixture values, never real credentials.
        text=output.decode('utf-8',errors='replace')
        if not ready.is_set(): raise AssertionError('Native TUI did not become ready:\n'+text[-16000:])
        if 'CODEX_HOME must be outside' in text: raise AssertionError('Shared daemon package guard was reached')
        if (root/'home/app-server-daemon/current').exists(): raise AssertionError('Unexpected managed daemon installation')
        write(b'\x03');time.sleep(.2);write(b'\x03')
        print('PASS real ConPTY TUI opens in relocated package with package-local CODEX_HOME')
    finally:
        # Only this suspended/owned process tree is eligible for termination.
        if pi.process:
            if 'job' in locals() and job: k.TerminateJobObject(job,1)
            k.TerminateProcess(pi.process,1)
            k.WaitForSingleObject(pi.process,5000)
        if console: k.ClosePseudoConsole(console)
        if reader: reader.join(timeout=5)
        if initialized: k.DeleteProcThreadAttributeList(attrs)
        for h in reversed(handles): k.CloseHandle(h)

if __name__=='__main__': main()
