#Requires -Version 5.1
param(
    [Parameter(Mandatory=$true)][int]$TargetProcessId,
    [ValidateSet('Tree','Invoke','SetValue')][string]$Action = 'Tree',
    [string]$AutomationId = '',
    [string]$ValueBase64 = '',
    [ValidateRange(1,500)][int]$MaxNodes = 150,
    [switch]$AllowChanges,
    [switch]$TaskAuthorized
)
$ErrorActionPreference = 'Stop'
if (-not $TaskAuthorized) { throw 'An explicitly selected desktop task is required.' }
if ($TargetProcessId -le 0) { throw 'Select a positive target process ID.' }
if ($Action -ne 'Tree' -and -not $AllowChanges) { throw 'A modifying action requires -AllowChanges.' }
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Windows UI Automation is required.' }
# The supervisor decodes captured stdout as UTF-8; Windows PowerShell otherwise
# uses the host OEM code page and can corrupt non-ASCII control names.
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$process = Get-Process -Id $TargetProcessId -ErrorAction Stop
$windowHandle = $process.MainWindowHandle
if ($windowHandle -eq [IntPtr]::Zero) { throw 'The selected process has no main window.' }
$window = [Windows.Automation.AutomationElement]::FromHandle($windowHandle)
if ($null -eq $window -or $window.Current.ProcessId -ne $TargetProcessId) {
    throw 'The selected window no longer belongs to that process.'
}
$walker = [Windows.Automation.TreeWalker]::ControlViewWalker
$queue = New-Object System.Collections.Queue
$queue.Enqueue($window)
$rows = New-Object System.Collections.ArrayList
$matchingControls = New-Object System.Collections.ArrayList
$seen = 0
$truncated = $false
while ($queue.Count -gt 0 -and $seen -lt $MaxNodes) {
    $element = $queue.Dequeue()
    $seen++
    $current = $element.Current
    # Do not inspect embedded UI belonging to a different process.
    if ($current.ProcessId -ne $TargetProcessId) { continue }
    if (-not $current.IsPassword) {
        [void]$rows.Add([ordered]@{
            automationId = $current.AutomationId
            name = $current.Name
            controlType = $current.ControlType.ProgrammaticName
            enabled = $current.IsEnabled
            offscreen = $current.IsOffscreen
        })
        if ($AutomationId -and $current.AutomationId -ceq $AutomationId) {
            [void]$matchingControls.Add($element)
        }
    }
    $child = $walker.GetFirstChild($element)
    while ($null -ne $child -and ($queue.Count + $seen) -lt $MaxNodes) {
        $queue.Enqueue($child)
        $child = $walker.GetNextSibling($child)
    }
    if ($null -ne $child) { $truncated = $true }
}
if ($queue.Count -gt 0) { $truncated = $true }
if ($Action -eq 'Tree') {
    [ordered]@{
        processId = $TargetProcessId
        windowHandle = $windowHandle.ToInt64()
        nodes = @($rows.ToArray())
        truncated = [bool]$truncated
    } | ConvertTo-Json -Depth 5
    exit 0
}
if (-not $AutomationId -or $matchingControls.Count -ne 1 -or $truncated) {
    throw 'Select one unique AutomationId in a complete bounded tree; no action was taken.'
}
$target = $matchingControls[0]
if ($target.Current.ProcessId -ne $TargetProcessId -or $target.Current.IsPassword -or
    -not $target.Current.IsEnabled -or $target.Current.IsOffscreen) {
    throw 'The selected control is no longer eligible for this action.'
}
if ($Action -eq 'Invoke') {
    $pattern = $target.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern)
    $pattern.Invoke()
} else {
    $pattern = $target.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern)
    if ($pattern.Current.IsReadOnly) { throw 'The selected control is read-only.' }
    $value = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($ValueBase64))
    $pattern.SetValue($value)
}
@{ processId = $TargetProcessId; action = $Action; automationId = $AutomationId; performed = $true } |
    ConvertTo-Json
