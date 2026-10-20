# Project-owned R20 subprocess lifetime helper. Windows PowerShell 5.1 / .NET 4.x.
# Callers MUST validate executable, code inputs, cwd and this file before loading it.
# No credentials, command-line contents or captured output are included in errors.
function Initialize-PortableProcessJob {
    param([Parameter(Mandatory=$true)][string]$PackageRoot)
    if ('CodexPortable.ProcessJobR20' -as [type]) { return }
    $root = [IO.Path]::GetFullPath($PackageRoot).TrimEnd('\')
    $tempRoot = Join-Path $root 'tmp'
    foreach ($path in @($root, $tempRoot)) {
        $item = Get-Item -LiteralPath $path -Force -ErrorAction Stop
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe process-helper build directory.' }
    }
    $build = Join-Path $tempRoot ('process-build-' + [Guid]::NewGuid().ToString('N'))
    if (Test-Path -LiteralPath $build) { throw 'Process-helper build directory already exists.' }
    [void][IO.Directory]::CreateDirectory($build)
    $oldTemp = $env:TEMP; $oldTmp = $env:TMP
    try {
        $env:TEMP = $build; $env:TMP = $build
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
namespace CodexPortable {
    public sealed class ProcessJobR20 : IDisposable {
        [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
            public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass, SchedulingClass;
        }
        [StructLayout(LayoutKind.Sequential)] struct IoCounters {
            public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
            public ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
        }
        [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {
            public BasicLimits BasicLimitInformation;
            public IoCounters IoInfo;
            public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
        }
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        static extern IntPtr CreateJobObject(IntPtr attributes, string name);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool SetInformationJobObject(IntPtr job, int type, ref ExtendedLimits info, uint size);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool TerminateJobObject(IntPtr job, uint code);
        [DllImport("kernel32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool CloseHandle(IntPtr handle);
        IntPtr handle;
        public ProcessJobR20() {
            handle = CreateJobObject(IntPtr.Zero, null);
            if (handle == IntPtr.Zero) throw new Win32Exception();
            ExtendedLimits limits = new ExtendedLimits();
            limits.BasicLimitInformation.LimitFlags = 0x2000; // KILL_ON_JOB_CLOSE
            if (!SetInformationJobObject(handle, 9, ref limits, (uint)Marshal.SizeOf(typeof(ExtendedLimits)))) {
                int error = Marshal.GetLastWin32Error(); Dispose(); throw new Win32Exception(error);
            }
        }
        public void Attach(IntPtr process) {
            if (!AssignProcessToJobObject(handle, process)) throw new Win32Exception();
        }
        public void Terminate() {
            if (handle != IntPtr.Zero && !TerminateJobObject(handle, 1)) throw new Win32Exception();
        }
        public void Dispose() {
            IntPtr old = handle; handle = IntPtr.Zero;
            if (old != IntPtr.Zero) CloseHandle(old);
            GC.SuppressFinalize(this);
        }
        ~ProcessJobR20() { Dispose(); }
    }
    public sealed class SuspendedChildR20 : IDisposable {
        [StructLayout(LayoutKind.Sequential)] struct SecurityAttributes {
            public int Length; public IntPtr SecurityDescriptor;
            [MarshalAs(UnmanagedType.Bool)] public bool InheritHandle;
        }
        [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct StartupInfo {
            public int cb; public string reserved, desktop, title;
            public uint x, y, xSize, ySize, xChars, yChars, fill, flags;
            public ushort show, reservedBytes; public IntPtr reservedPtr, input, output, error;
        }
        [StructLayout(LayoutKind.Sequential)] struct StartupInfoEx {
            public StartupInfo startup; public IntPtr attributes;
        }
        [StructLayout(LayoutKind.Sequential)] struct ProcessInfo {
            public IntPtr process, thread; public uint pid, tid;
        }
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool CreatePipe(out IntPtr read, out IntPtr write, ref SecurityAttributes sa, uint size);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool SetHandleInformation(IntPtr handle, uint mask, uint flags);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool CreateProcessW(string application, System.Text.StringBuilder command,
            IntPtr processAttributes, IntPtr threadAttributes, bool inherit, uint flags,
            IntPtr environment, string cwd, ref StartupInfoEx startup, out ProcessInfo process);
        [DllImport("kernel32.dll", SetLastError=true)]
        static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool TerminateProcess(IntPtr process, uint code);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool InitializeProcThreadAttributeList(IntPtr list, int count, int flags, ref IntPtr size);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool UpdateProcThreadAttribute(IntPtr list, uint flags, IntPtr attribute,
            IntPtr value, IntPtr size, IntPtr previous, IntPtr returnedSize);
        [DllImport("kernel32.dll")]
        static extern void DeleteProcThreadAttributeList(IntPtr list);
        [DllImport("kernel32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool CloseHandle(IntPtr handle);
        static void Close(ref IntPtr value) { IntPtr h=value; value=IntPtr.Zero; if(h!=IntPtr.Zero) CloseHandle(h); }
        [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
        [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr GetStdHandle(int kind);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool DuplicateHandle(IntPtr sourceProcess, IntPtr source, IntPtr targetProcess,
            out IntPtr duplicate, uint access, bool inherit, uint options);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        static extern IntPtr CreateFile(string name, uint access, uint share, ref SecurityAttributes sa,
            uint disposition, uint attributes, IntPtr template);
        static IntPtr InheritStandardHandle(int kind, bool input) {
            IntPtr source=GetStdHandle(kind), duplicate;
            if(source!=IntPtr.Zero && source!=new IntPtr(-1)) {
                IntPtr process=GetCurrentProcess();
                if(!DuplicateHandle(process,source,process,out duplicate,0,true,2)) throw new Win32Exception();
                return duplicate;
            }
            // A GUI caller may have no standard stream. Supply NUL, never a host file.
            var sa=new SecurityAttributes {Length=Marshal.SizeOf(typeof(SecurityAttributes)),InheritHandle=true};
            duplicate=CreateFile("NUL",input ? 0x80000000u : 0x40000000u,3,ref sa,3,0,IntPtr.Zero);
            if(duplicate==new IntPtr(-1)) throw new Win32Exception();
            return duplicate;
        }
        static System.IO.FileStream Own(ref IntPtr value, System.IO.FileAccess access) {
            var handle = new Microsoft.Win32.SafeHandles.SafeFileHandle(value, true); value=IntPtr.Zero;
            try { return new System.IO.FileStream(handle, access, 4096, false); }
            catch { handle.Dispose(); throw; }
        }
        System.Diagnostics.Process process;
        public System.IO.StreamWriter StandardInput { get; private set; }
        public System.IO.StreamReader StandardOutput { get; private set; }
        public System.IO.StreamReader StandardError { get; private set; }
        public bool HasExited { get { return process.HasExited; } }
        public int ExitCode { get { return process.ExitCode; } }
        public SuspendedChildR20(System.Diagnostics.ProcessStartInfo info, ProcessJobR20 job) {
            bool capture=info.RedirectStandardInput || info.RedirectStandardOutput || info.RedirectStandardError;
            if(capture && !(info.RedirectStandardInput && info.RedirectStandardOutput && info.RedirectStandardError))
                throw new ArgumentException("All three streams must be redirected together.");
            IntPtr childIn=IntPtr.Zero, parentIn=IntPtr.Zero, childOut=IntPtr.Zero, parentOut=IntPtr.Zero;
            IntPtr childErr=IntPtr.Zero, parentErr=IntPtr.Zero, env=IntPtr.Zero, handles=IntPtr.Zero;
            StartupInfoEx start=new StartupInfoEx(); ProcessInfo pi=new ProcessInfo(); bool attributeReady=false;
            try {
                uint flags=0x00000004 | 0x00000400; // CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
                start.startup.cb=Marshal.SizeOf(typeof(StartupInfo));
                if(info.CreateNoWindow) flags |= 0x08000000;
                if(capture) {
                    var sa=new SecurityAttributes {Length=Marshal.SizeOf(typeof(SecurityAttributes)),InheritHandle=true};
                    if(!CreatePipe(out childIn,out parentIn,ref sa,0) ||
                       !CreatePipe(out parentOut,out childOut,ref sa,0) ||
                       !CreatePipe(out parentErr,out childErr,ref sa,0)) throw new Win32Exception();
                    foreach(IntPtr h in new[]{parentIn,parentOut,parentErr})
                        if(!SetHandleInformation(h,1,0)) throw new Win32Exception();
                    StandardInput=new System.IO.StreamWriter(Own(ref parentIn,System.IO.FileAccess.Write),new System.Text.UTF8Encoding(false));
                    StandardOutput=new System.IO.StreamReader(Own(ref parentOut,System.IO.FileAccess.Read),info.StandardOutputEncoding ?? System.Text.Encoding.UTF8);
                    StandardError=new System.IO.StreamReader(Own(ref parentErr,System.IO.FileAccess.Read),info.StandardErrorEncoding ?? System.Text.Encoding.UTF8);
                } else {
                    // Forward existing console or pipe handles explicitly. CREATE_NO_WINDOW
                    // otherwise drops MCP stdio, and generic inheritance leaks other handles.
                    childIn=InheritStandardHandle(-10,true);
                    childOut=InheritStandardHandle(-11,false);
                    childErr=InheritStandardHandle(-12,false);
                }
                {
                    start.startup.flags=0x100; // STARTF_USESTDHANDLES
                    start.startup.input=childIn; start.startup.output=childOut; start.startup.error=childErr;
                    IntPtr size=IntPtr.Zero;
                    InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref size);
                    if(size==IntPtr.Zero) throw new Win32Exception();
                    start.attributes=Marshal.AllocHGlobal(size);
                    if(!InitializeProcThreadAttributeList(start.attributes,1,0,ref size)) throw new Win32Exception();
                    attributeReady=true;
                    handles=Marshal.AllocHGlobal(IntPtr.Size*3);
                    Marshal.WriteIntPtr(handles,0,childIn); Marshal.WriteIntPtr(handles,IntPtr.Size,childOut);
                    Marshal.WriteIntPtr(handles,IntPtr.Size*2,childErr);
                    if(!UpdateProcThreadAttribute(start.attributes,0,new IntPtr(0x20002),handles,
                        new IntPtr(IntPtr.Size*3),IntPtr.Zero,IntPtr.Zero)) throw new Win32Exception();
                    flags |= 0x00080000; // EXTENDED_STARTUPINFO_PRESENT, explicit std-handle allowlist
                    start.startup.cb=Marshal.SizeOf(typeof(StartupInfoEx));
                }
                var keys=new System.Collections.Generic.List<string>();
                foreach(string key in info.EnvironmentVariables.Keys) keys.Add(key);
                keys.Sort(StringComparer.OrdinalIgnoreCase);
                var block=new System.Text.StringBuilder();
                foreach(string key in keys) {
                    string value=info.EnvironmentVariables[key] ?? "";
                    if(key.IndexOf('\0')>=0 || value.IndexOf('\0')>=0) throw new ArgumentException("Invalid environment.");
                    block.Append(key).Append('=').Append(value).Append('\0');
                }
                block.Append('\0'); if(keys.Count==0) block.Append('\0');
                env=Marshal.StringToHGlobalUni(block.ToString());
                if(info.FileName.IndexOf('"')>=0 || info.FileName.IndexOf('\0')>=0) throw new ArgumentException("Invalid executable.");
                var command=new System.Text.StringBuilder("\""+info.FileName+"\" "+info.Arguments);
                if(!CreateProcessW(info.FileName,command,IntPtr.Zero,IntPtr.Zero,true,flags,env,
                    info.WorkingDirectory,ref start,out pi)) throw new Win32Exception();
                // No child instructions execute before it belongs to the kill-on-close job.
                job.Attach(pi.process);
                process=System.Diagnostics.Process.GetProcessById((int)pi.pid);
                // Cache a handle while the child is still suspended: even instant exit is observable.
                IntPtr cached=process.Handle;
                Close(ref childIn); Close(ref childOut); Close(ref childErr);
                if(ResumeThread(pi.thread)==0xffffffff) throw new Win32Exception();
            } catch {
                if(pi.process!=IntPtr.Zero) TerminateProcess(pi.process,1);
                Dispose(); throw;
            } finally {
                Close(ref pi.thread); Close(ref pi.process);
                Close(ref childIn); Close(ref childOut); Close(ref childErr);
                Close(ref parentIn); Close(ref parentOut); Close(ref parentErr);
                if(attributeReady) DeleteProcThreadAttributeList(start.attributes);
                if(start.attributes!=IntPtr.Zero) Marshal.FreeHGlobal(start.attributes);
                if(handles!=IntPtr.Zero) Marshal.FreeHGlobal(handles);
                if(env!=IntPtr.Zero) Marshal.FreeHGlobal(env);
            }
        }
        public void Kill() { process.Kill(); }
        public bool WaitForExit(int milliseconds) { return process.WaitForExit(milliseconds); }
        public void Dispose() {
            try { if(StandardInput!=null) StandardInput.BaseStream.Dispose(); } catch {}
            try { if(StandardOutput!=null) StandardOutput.Dispose(); } catch {}
            try { if(StandardError!=null) StandardError.Dispose(); } catch {}
            try { if(process!=null) process.Dispose(); } catch {}
        }
    }
}
'@ -ErrorAction Stop
    } finally {
        $env:TEMP = $oldTemp; $env:TMP = $oldTmp
        # Only the compiler's own fresh, flat directory is eligible for deletion.
        try {
            # CodeDOM may remove its empty TempFiles directory itself.
            for ($cleanupAttempt = 0; $cleanupAttempt -lt 20 -and (Test-Path -LiteralPath $build); $cleanupAttempt++) {
                try {
                    $dir = Get-Item -LiteralPath $build -Force -ErrorAction Stop
                    if (-not $dir.PSIsContainer -or ($dir.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe compiler output root.' }
                    $compilerSubdirectoryStillOwned = $false
                    foreach ($file in @(Get-ChildItem -LiteralPath $build -Force -ErrorAction Stop)) {
                        if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe compiler output reparse point.' }
                        if ($file.PSIsContainer) { $compilerSubdirectoryStillOwned = $true; break }
                        [IO.File]::Delete($file.FullName)
                    }
                    if ($compilerSubdirectoryStillOwned) {
                        if ($cleanupAttempt -eq 19) { throw 'Compiler output subdirectory was not released in time.' }
                        Start-Sleep -Milliseconds 100
                        continue
                    }
                    [IO.Directory]::Delete($build, $false)
                } catch {
                    if ($_.Exception.Message -like 'Unsafe compiler output*' -or $cleanupAttempt -eq 19) { throw }
                    Start-Sleep -Milliseconds 100
                }
            }
        } catch { Write-Warning ('Process-helper compiler scratch was retained because safe cleanup failed: ' + $_.Exception.Message) }
    }
}

function Invoke-PortableProcess {
    param(
        [Parameter(Mandatory=$true)][Diagnostics.ProcessStartInfo]$StartInfo,
        [Parameter(Mandatory=$true)][string]$PackageRoot,
        [int]$TimeoutMs = 30000,
        [AllowEmptyString()][string]$InputText = '',
        [int]$MaxOutputChars = 4194304
    )
    if ($StartInfo.UseShellExecute) { throw 'Shell execution is not supported by the process supervisor.' }
    if ($TimeoutMs -lt 0 -or $MaxOutputChars -lt 1 -or $MaxOutputChars -gt 16777216 -or $InputText.Length -gt 8388608) { throw 'Invalid process resource limit.' }
    if ($TimeoutMs -eq 0 -and ($StartInfo.RedirectStandardOutput -or $StartInfo.RedirectStandardError -or $StartInfo.RedirectStandardInput)) { throw 'Captured processes require a finite deadline.' }
    Initialize-PortableProcessJob -PackageRoot $PackageRoot
    $job = New-Object CodexPortable.ProcessJobR20
    $process = $null
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $started = $false; $terminated = $false
    $stdout = New-Object Text.StringBuilder
    $stderr = New-Object Text.StringBuilder
    $outBuffer = New-Object char[] 4096; $errBuffer = New-Object char[] 4096
    $outTask = $null; $errTask = $null; $inTask = $null
    $outDone = -not $StartInfo.RedirectStandardOutput
    $errDone = -not $StartInfo.RedirectStandardError
    $inputStage = 2
    try {
        $process = New-Object CodexPortable.SuspendedChildR20 -ArgumentList $StartInfo,$job
        $started = $true
        if (-not $outDone) { $outTask = $process.StandardOutput.ReadAsync($outBuffer, 0, $outBuffer.Length) }
        if (-not $errDone) { $errTask = $process.StandardError.ReadAsync($errBuffer, 0, $errBuffer.Length) }
        if ($StartInfo.RedirectStandardInput) {
            $inTask = $process.StandardInput.WriteAsync($InputText)
            $inputStage = 0
        }
        while ($true) {
            if ($TimeoutMs -gt 0 -and $watch.ElapsedMilliseconds -ge $TimeoutMs) { throw [TimeoutException]::new('Portable child exceeded its total IO deadline.') }
            if ($inputStage -lt 2 -and $inTask.IsCompleted) {
                [void]$inTask.GetAwaiter().GetResult()
                if ($inputStage -eq 0) { $inTask = $process.StandardInput.FlushAsync(); $inputStage = 1 }
                else { $process.StandardInput.Close(); $inputStage = 2 }
            }
            if (-not $outDone -and $outTask.IsCompleted) {
                $count = $outTask.GetAwaiter().GetResult()
                if ($count -eq 0) { $outDone = $true }
                else {
                    if ($stdout.Length + $count -gt $MaxOutputChars) { throw 'Child stdout exceeded its limit.' }
                    [void]$stdout.Append($outBuffer, 0, $count)
                    $outTask = $process.StandardOutput.ReadAsync($outBuffer, 0, $outBuffer.Length)
                }
            }
            if (-not $errDone -and $errTask.IsCompleted) {
                $count = $errTask.GetAwaiter().GetResult()
                if ($count -eq 0) { $errDone = $true }
                else {
                    if ($stderr.Length + $count -gt $MaxOutputChars) { throw 'Child stderr exceeded its limit.' }
                    [void]$stderr.Append($errBuffer, 0, $count)
                    $errTask = $process.StandardError.ReadAsync($errBuffer, 0, $errBuffer.Length)
                }
            }
            if ($process.HasExited) {
                if (-not $terminated) { $job.Terminate(); $terminated = $true }
                if ($outDone -and $errDone) { break }
            }
            Start-Sleep -Milliseconds 10
        }
        return [pscustomobject]@{ ExitCode = $process.ExitCode; StdOut = $stdout.ToString(); StdErr = $stderr.ToString() }
    } catch {
        # Preserve a machine-readable timeout reason without exposing request content.
        if ($_.Exception -is [TimeoutException]) { throw [TimeoutException]::new('Portable child exceeded its total IO deadline.') }
        # A framework/child exception can contain command-line or request content.
        throw 'Portable child failed, timed out, or exceeded an IO limit; sensitive details suppressed.'
    } finally {
        try { $job.Terminate() } catch {}
        try { $job.Dispose() } catch {}
        if ($started) {
            try { if (-not $process.HasExited) { $process.Kill() } } catch {}
            try { [void]$process.WaitForExit(2000) } catch {}
            # Close raw stdin without another blocking StreamWriter flush.
            try { if ($StartInfo.RedirectStandardInput) { $process.StandardInput.BaseStream.Dispose() } } catch {}
            try { if ($StartInfo.RedirectStandardOutput) { $process.StandardOutput.Dispose() } } catch {}
            try { if ($StartInfo.RedirectStandardError) { $process.StandardError.Dispose() } } catch {}
        }
        try { if ($null -ne $process) { $process.Dispose() } } catch {}
        $watch.Stop()
    }
}
