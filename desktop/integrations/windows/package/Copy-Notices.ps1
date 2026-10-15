[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$NoticeDirectory,
  [Parameter(Mandatory=$true)][string]$DestinationDirectory,
  [Parameter(Mandatory=$true)][ValidateSet('x64','ARM64')][string]$Architecture
)
$ErrorActionPreference = 'Stop'
$sourceRoot = (Resolve-Path -LiteralPath $NoticeDirectory).Path
$destinationRoot = (Resolve-Path -LiteralPath $DestinationDirectory).Path
if (((Get-Item -LiteralPath $sourceRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'NoticeDirectory must not be a symlink or reparse point.' }
$reportPath = Join-Path $sourceRoot 'THIRD-PARTY.json'
if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) { throw 'NoticeDirectory must contain generated THIRD-PARTY.json.' }
$reportItem = Get-Item -LiteralPath $reportPath -Force
if (($reportItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'THIRD-PARTY.json must not be a symlink or reparse point.' }
if ($reportItem.Length -gt 2MB) { throw 'THIRD-PARTY.json exceeds the bounded 2 MiB limit.' }
try { $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json -ErrorAction Stop }
catch { throw "Could not parse THIRD-PARTY.json: $($_.Exception.Message)" }
$expectedTarget = if ($Architecture -eq 'x64') { 'x86_64-pc-windows-msvc' } else { 'aarch64-pc-windows-msvc' }
if ($report.schema_version -ne 1 -or $report.generated_by -ne 'desktop/scripts/collect-desktop-notices.py') { throw 'THIRD-PARTY.json must use desktop collector schema_version 1.' }
if ($report.project.name -ne 'bytepleat-desktop' -or $report.project.version -ne '0.1.0') { throw 'Notice report must identify Cargo project bytepleat-desktop version 0.1.0.' }
if ($report.target -ne $expectedTarget -or $report.cargo_metadata_filter_platform -ne $expectedTarget) { throw "Notice report target must exactly match $Architecture ($expectedTarget)." }
if ($null -eq $report.packages -or $null -eq $report.runtime_components -or $null -eq $report.unresolved_gaps -or $null -eq $report.platform_prerequisites) { throw 'Generated report is missing required inventory or gap fields.' }

# Validate every manifest path before copying any file. Only explicit inventory paths are used.
$entries = [Collections.Generic.List[object]]::new()
foreach ($component in @($report.packages) + @($report.runtime_components)) {
  foreach ($notice in @($component.notices) + @($component.vendored_component_notices)) {
    if ($null -ne $notice) { $entries.Add($notice) }
  }
}
if ($entries.Count -gt 4096) { throw 'Notice inventory exceeds the bounded 4096-file limit.' }
$seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$totalBytes = [int64]0
$validated = [Collections.Generic.List[object]]::new()
foreach ($entry in $entries) {
  $relative = [string]$entry.path
  $digest = [string]$entry.sha256
  if ([string]::IsNullOrWhiteSpace($relative) -or $relative.Contains('\') -or $relative.Contains(':') -or $relative.StartsWith('/') -or $relative -match '[\x00-\x1f]') { throw "Unsafe notice path: '$relative'" }
  $parts = $relative.Split('/')
  if (@($parts | Where-Object { $_ -eq '' -or $_ -eq '.' -or $_ -eq '..' }).Count -gt 0) { throw "Unsafe notice path: '$relative'" }
  if (-not $seen.Add($relative)) { throw "Duplicate notice path: '$relative'" }
  if ($digest -notmatch '^[0-9a-fA-F]{64}$') { throw "Notice entry lacks a valid SHA256 digest: '$relative'" }
  $candidate = $sourceRoot
  foreach ($part in $parts) {
    $candidate = Join-Path $candidate $part
    if (-not (Test-Path -LiteralPath $candidate)) { throw "Notice file is missing: '$relative'" }
    $item = Get-Item -LiteralPath $candidate -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Notice path contains a symlink or reparse point: '$relative'" }
  }
  if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Notice path is not a regular file: '$relative'" }
  $item = Get-Item -LiteralPath $candidate -Force
  if ($item.Length -gt 8MB) { throw "Notice file exceeds 8 MiB: '$relative'" }
  $totalBytes += $item.Length
  if ($totalBytes -gt 64MB) { throw 'Notice inventory exceeds the bounded 64 MiB total.' }
  $actual = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash
  if ($actual -ne $digest.ToUpperInvariant()) { throw "Notice SHA256 mismatch: '$relative'" }
  $validated.Add([pscustomobject]@{ Source=$candidate; Relative=$relative })
}
$license = Join-Path $PSScriptRoot '..\..\..\..\LICENSE'
$license = (Resolve-Path -LiteralPath $license).Path
$licenseItem = Get-Item -LiteralPath $license -Force
if (($licenseItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $licenseItem.Length -gt 2MB) { throw 'Repository LICENSE must be a regular file no larger than 2 MiB.' }
$noticesRoot = Join-Path $destinationRoot 'Notices'
if (Test-Path -LiteralPath $noticesRoot) { throw 'Destination already contains Notices; refusing to replace it.' }
$null = New-Item -ItemType Directory -Path $noticesRoot
Copy-Item -LiteralPath $license -Destination (Join-Path $noticesRoot 'LICENSE')
foreach ($file in $validated) {
  $target = Join-Path $noticesRoot ($file.Relative.Replace('/', [IO.Path]::DirectorySeparatorChar))
  $parent = Split-Path -Parent $target
  $null = New-Item -ItemType Directory -Force -Path $parent
  Copy-Item -LiteralPath $file.Source -Destination $target
}
# Copy the source report as-is: unresolved gaps, legal-clearance wording, and source findings stay intact.
Copy-Item -LiteralPath $reportPath -Destination (Join-Path $noticesRoot 'THIRD-PARTY.json')
Write-Host "Included root LICENSE and $($validated.Count) verified target-specific notice files in Notices/."
