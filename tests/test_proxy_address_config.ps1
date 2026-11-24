#Requires -Version 5.1
# Run the actual proxy configuration statements, with no network requests
# and a stub for starting a real bridge. Synthetic addresses only.
param([string]$BaselineCommit = '')
$ErrorActionPreference = 'Stop'
$Root=Split-Path -Parent $PSScriptRoot
if ($BaselineCommit) {
    if ($BaselineCommit -notmatch '^[a-f0-9]{40}$') {throw 'Invalid baseline commit'}
    $lines=& git -C $Root show ($BaselineCommit+':run-codex.ps1')
    if ($LASTEXITCODE -ne 0) {throw 'Cannot read baseline'}
    $source=$lines -join "`n"
} else {$source=[IO.File]::ReadAllText((Join-Path $Root 'run-codex.ps1'))}
$source=$source.Replace("`r`n","`n")
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
if ($errors.Count) {throw 'Launcher parse failed'}
$functions=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true))
foreach ($name in @('Convert-ToTomlBool','Format-HostForUri')) {
    $nodes=@($functions | Where-Object Name -eq $name)
    if ($nodes.Count -ne 1) {throw ('Missing function '+$name)}
    . ([scriptblock]::Create($nodes[0].Extent.Text))
}
$start=$source.IndexOf('foreach ($pv in @("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","NO_PROXY"')
$end=$source.IndexOf('$ReasoningEffort = Normalize-ReasoningEffortValue',$start)
if ($start -lt 0 -or $end -le $start) {throw 'Production proxy configuration not found'}
$proxyConfig=[scriptblock]::Create($source.Substring($start,$end-$start))
function Assert-Case {param([bool]$Condition,[string]$Message) if (-not $Condition) {throw $Message}}
$script:BridgeCalls=0
$script:BridgeEnabled=$false
function Start-CodexSocksHttpBridge {
    param([string]$SocksHost,[string]$SocksPort)
    $script:BridgeCalls++
    $script:ObservedHost=$SocksHost
    $script:ObservedPort=$SocksPort
    if ($script:BridgeEnabled) {
        $script:CodexProxyBridgeDisplayUrl='http://127.0.0.1:18088'
        return 'http://127.0.0.1:18088'
    }
    return ''
}
function Run-Proxy {
    param([string]$Protocol,[string]$HostName,[string]$Port,[bool]$Bypass=$true,[bool]$Bridge=$false,[bool]$Enabled=$true)
    $script:CodexProxyBridgeDisplayUrl=''
    $script:BridgeEnabled=$Bridge
    $script:BridgeCalls=0
    $script:ObservedHost=''
    $script:ObservedPort=''
    $env:CODEX_PROXY_ENABLED=$Enabled.ToString()
    $env:CODEX_PROXY_PROTOCOL=$Protocol
    $env:CODEX_PROXY_HOST=$HostName
    $env:CODEX_PROXY_PORT=$Port
    $env:CODEX_PROXY_BYPASS_MODEL=$Bypass.ToString()
    $env:CODEX_PROXY_FOR_SUBPROCESS='false'
    $env:CODEX_BASE_URL='https://model.synthetic.invalid/v1'
    $env:HTTP_PROXY='http://inherited.synthetic.invalid:1'
    $env:HTTPS_PROXY=$env:HTTP_PROXY
    $env:ALL_PROXY=$env:HTTP_PROXY
    $env:NO_PROXY='inherited.synthetic.invalid'
    $SandboxNetworkAccess='false'
    . $proxyConfig
    return [pscustomobject]@{
        Http=$env:HTTP_PROXY; Https=$env:HTTPS_PROXY; All=$env:ALL_PROXY; NoProxy=$env:NO_PROXY
        BridgeCalls=$script:BridgeCalls; BridgeHost=$script:ObservedHost; BridgePort=$script:ObservedPort
    }
}
$names=@('CODEX_PROXY_ENABLED','CODEX_PROXY_PROTOCOL','CODEX_PROXY_HOST','CODEX_PROXY_PORT','CODEX_PROXY_BYPASS_MODEL',
    'CODEX_PROXY_FOR_SUBPROCESS','CODEX_BASE_URL','CODEX_SANDBOX_NETWORK_ACCESS','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY')
$previous=@{}
foreach ($name in $names) {$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
try {
    $http=Run-Proxy -Protocol 'http' -HostName '127.0.0.1' -Port '+10808'
    $directSocks=Run-Proxy -Protocol 'socks5' -HostName '::1' -Port '00010808'
    $bridge=Run-Proxy -Protocol 'socks5' -HostName '[::1]' -Port '+10808' -Bridge $true
    if ($BaselineCommit) {
        Assert-Case ($http.Http -ceq 'http://127.0.0.1:+10808' -and
            $directSocks.All -ceq 'socks5h://[::1]:00010808' -and $bridge.BridgePort -ceq '+10808') 'Old raw port reuse did not reproduce'
        Write-Output 'REPRODUCED validated positive port reused in noncanonical URI and bridge arguments'
        return
    }
    Assert-Case ($http.Http -ceq 'http://127.0.0.1:10808' -and $http.Https -ceq $http.Http -and $http.All -ceq $http.Http -and $http.BridgeCalls -eq 0) 'HTTP canonical port failed'
    Assert-Case ($directSocks.All -ceq 'socks5h://[::1]:10808' -and -not $directSocks.Http -and $directSocks.BridgePort -ceq '10808') 'SOCKS fallback canonical port failed'
    Assert-Case ($bridge.Http -ceq 'http://127.0.0.1:18088' -and $bridge.BridgeHost -ceq '[::1]' -and $bridge.BridgePort -ceq '10808' -and $bridge.BridgeCalls -eq 1) 'Existing bridge routing changed'
    $ordinary=Run-Proxy -Protocol 'http' -HostName 'proxy.synthetic.invalid' -Port '1080'
    Assert-Case ($ordinary.Http -ceq 'http://proxy.synthetic.invalid:1080' -and ($ordinary.NoProxy -split ',') -contains 'model.synthetic.invalid') 'Existing ordinary host, port or model bypass changed'
    $proxied=Run-Proxy -Protocol 'http' -HostName '127.0.0.1' -Port '1080' -Bypass $false
    Assert-Case ($proxied.NoProxy -ceq 'localhost,127.0.0.1,::1') 'Existing explicit model proxy policy changed'
    $off=Run-Proxy -Protocol 'http' -HostName '127.0.0.1' -Port '1080' -Enabled $false
    Assert-Case (-not $off.Http -and -not $off.All -and -not $off.NoProxy -and $off.BridgeCalls -eq 0) 'Disabled proxy inherited host values'
    Write-Output 'PASS canonical ports for HTTP, explicit SOCKS fallback and bridge; ordinary routing, model bypass and disabled proxy unchanged'
} finally {
    foreach ($name in $names) {[Environment]::SetEnvironmentVariable($name,$previous[$name],'Process')}
}
