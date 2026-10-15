$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$copier = Join-Path $PSScriptRoot '../package/Copy-Notices.ps1'
$work = Join-Path ([IO.Path]::GetTempPath()) ('BytepleatNoticeTests-' + [guid]::NewGuid().ToString('N'))
$source = Join-Path $work 'source'
$null = New-Item -ItemType Directory -Path $source
try {
  $file = Join-Path $source 'third-party-licenses/fixture/LICENSE'
  $null = New-Item -ItemType Directory -Path (Split-Path -Parent $file)
  [IO.File]::WriteAllText($file, 'Generated notice fixture' + [char]10)
  $digest = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
  $notice = @{ path='third-party-licenses/fixture/LICENSE'; sha256=$digest }
  $report = @{
    schema_version=1; generated_by='desktop/scripts/collect-desktop-notices.py'
    project=@{name='bytepleat-desktop'; version='0.1.0'}
    target='x86_64-pc-windows-msvc'; cargo_metadata_filter_platform='x86_64-pc-windows-msvc'
    packages=@(@{name='generated-fixture'; version='1'; notices=@($notice)})
    runtime_components=@(); unresolved_gaps=@(@{gap='Generated unresolved fixture'})
    platform_prerequisites=@{status='not bundled'}
  }
  $reportPath = Join-Path $source 'THIRD-PARTY.json'
  function Save-Report { $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportPath -Encoding utf8 }
  function Check-Rejection([string]$Name, [string]$Architecture='x64') {
    $destination = Join-Path $work $Name
    $null = New-Item -ItemType Directory -Path $destination
    $rejected = $false
    try { & $copier -NoticeDirectory $source -DestinationDirectory $destination -Architecture $Architecture }
    catch { $rejected = $true }
    if (-not $rejected) { throw "Expected notice rejection: $Name" }
    if (Test-Path -LiteralPath (Join-Path $destination 'Notices')) { throw "Rejected input published notices: $Name" }
  }
  Save-Report
  $valid = Join-Path $work 'valid'
  $null = New-Item -ItemType Directory -Path $valid
  & $copier -NoticeDirectory $source -DestinationDirectory $valid -Architecture x64
  $published = Join-Path $valid 'Notices'
  if (-not (Test-Path -LiteralPath (Join-Path $published 'LICENSE'))) { throw 'Project license not included' }
  if ((Get-FileHash -LiteralPath (Join-Path $published $notice.path) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $digest) { throw 'Notice bytes changed' }
  $copy = Get-Content -LiteralPath (Join-Path $published 'THIRD-PARTY.json') -Raw | ConvertFrom-Json
  if ($copy.unresolved_gaps[0].gap -ne 'Generated unresolved fixture') { throw 'Source finding lost' }
  Check-Rejection 'wrong-target' 'ARM64'
  $report.project.version='9.0'
  Save-Report
  Check-Rejection 'wrong-version'
  $report.project.version='0.1.0'
  $notice.sha256=('0' * 64)
  Save-Report
  Check-Rejection 'wrong-hash'
  $notice.sha256=$digest
  $notice.path='../outside/LICENSE'
  Save-Report
  Check-Rejection 'traversal'
  $notice.path='third-party-licenses/fixture/LICENSE'
  $report.packages[0].notices=@($notice, $notice)
  Save-Report
  Check-Rejection 'duplicate'
  $report.packages[0].notices=@($notice)
  $escape = Join-Path $source 'escape'
  $null = New-Item -ItemType Junction -Path $escape -Value (Split-Path -Parent $file)
  $notice.path='escape/LICENSE'
  Save-Report
  Check-Rejection 'reparse'
  Write-Host 'Native notice packaging checks passed: valid copy and six rejected inputs.'
} finally {
  Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
