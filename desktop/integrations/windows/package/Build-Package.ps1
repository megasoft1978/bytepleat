[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$AppDirectory,
  [string]$NoticeDirectory,
  [string]$Publisher = 'CN=Bytepleat Development',
  [string]$CertificatePath,
  [string]$CertificatePassword,
  [switch]$Sign,
  [switch]$SchemaOnly,
  [string]$OutputDirectory = "$PSScriptRoot\out",
  [ValidateSet('x64','ARM64')][string]$Architecture = 'x64'
)
$ErrorActionPreference = 'Stop'
if ($SchemaOnly -and $Sign) { throw '-SchemaOnly cannot be combined with -Sign.' }
if (-not $SchemaOnly -and [string]::IsNullOrWhiteSpace($NoticeDirectory)) {
  throw 'Regular package builds require -NoticeDirectory containing the matching generated target notice artifact.'
}
if ($SchemaOnly -and -not [string]::IsNullOrWhiteSpace($NoticeDirectory)) {
  throw '-SchemaOnly cannot be combined with -NoticeDirectory.'
}
$out = [IO.Path]::GetFullPath($OutputDirectory)
$null = New-Item -ItemType Directory -Force -Path $out
$finalMsix = Join-Path $out "Bytepleat-$Architecture.msix"
if ([IO.File]::Exists($finalMsix) -or [IO.Directory]::Exists($finalMsix)) { throw "Refusing to overwrite existing package output: $finalMsix" }
$app = (Resolve-Path -LiteralPath $AppDirectory).Path
foreach ($required in @('bytepleat-desktop.exe','BytepleatExplorerCommands.dll')) {
  if (-not (Test-Path -LiteralPath (Join-Path $app $required) -PathType Leaf)) { throw "AppDirectory must contain $required" }
}
function Get-PeMachine([string]$Path) {
  $stream = [IO.File]::OpenRead($Path)
  try {
    $reader = [IO.BinaryReader]::new($stream)
    if ($reader.ReadUInt16() -ne 0x5A4D) { throw "Not a PE executable: $Path" }
    $stream.Position = 0x3c
    $peOffset = $reader.ReadUInt32()
    if ($peOffset -gt ($stream.Length - 6)) { throw "Invalid PE header: $Path" }
    $stream.Position = $peOffset
    if ($reader.ReadUInt32() -ne 0x00004550) { throw "Invalid PE signature: $Path" }
    return $reader.ReadUInt16()
  } finally { $stream.Dispose() }
}
function Find-WindowsSdkTool([string]$Name) {
  $kitsRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10'
  $candidates = [Collections.Generic.List[string]]::new()
  $binRoot = Join-Path $kitsRoot 'bin'
  if (Test-Path -LiteralPath $binRoot -PathType Container) {
    $versions = @(Get-ChildItem -LiteralPath $binRoot -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match '^\d+(?:\.\d+){2,3}$' } |
      Sort-Object { [version]$_.Name } -Descending)
    foreach ($version in $versions) {
      foreach ($architecture in @('x64','arm64','x86')) { $candidates.Add((Join-Path $version.FullName "$architecture\$Name")) }
    }
  }
  $candidates.Add((Join-Path $kitsRoot "App Certification Kit\$Name"))
  foreach ($candidate in $candidates) { if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate } }
  throw "Could not find $Name in installed Windows Kits 10 SDK directories under '$kitsRoot'. Install the Windows SDK component; this script does not download tools."
}
$expectedMachine = if ($Architecture -eq 'x64') { 0x8664 } else { 0xAA64 }
foreach ($binary in @('bytepleat-desktop.exe','BytepleatExplorerCommands.dll')) {
  $machine = Get-PeMachine (Join-Path $app $binary)
  if ($machine -ne $expectedMachine) { throw "$binary PE machine 0x$('{0:X4}' -f $machine) does not match requested $Architecture package architecture." }
}
if ($Sign -and (-not $CertificatePath -or $null -eq $CertificatePassword)) {
  throw 'Signing requires both CertificatePath and CertificatePassword.'
}
$manifest = Join-Path $PSScriptRoot 'AppxManifest.xml'
$xml = [xml](Get-Content -LiteralPath $manifest -Raw)
$xml.Package.Identity.Publisher = $Publisher
$xml.Package.Identity.ProcessorArchitecture = $Architecture.ToLowerInvariant()
$work = Join-Path $out (".BytepleatPackage-" + [guid]::NewGuid().ToString('N'))
$stage = Join-Path $work 'payload'
$workMsix = Join-Path $work "Bytepleat-$Architecture.msix"
$null = New-Item -ItemType Directory -Path $stage
try {
  foreach ($binary in @('bytepleat-desktop.exe','BytepleatExplorerCommands.dll')) {
    Copy-Item -LiteralPath (Join-Path $app $binary) -Destination (Join-Path $stage $binary)
  }
  $assets = Join-Path $stage 'Assets'
  $null = New-Item -ItemType Directory -Path $assets
  $iconSource = Join-Path $PSScriptRoot '..\..\..\src-tauri\icons'
  foreach ($name in @('Square150x150Logo.png','Square44x44Logo.png','StoreLogo.png')) {
    $source = Join-Path $iconSource $name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Required generated app icon not found: $source" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $assets $name)
  }
  if (-not $SchemaOnly) { & (Join-Path $PSScriptRoot 'Copy-Notices.ps1') -NoticeDirectory $NoticeDirectory -DestinationDirectory $stage -Architecture $Architecture }
  $xml.Save((Join-Path $stage 'AppxManifest.xml'))
  $makeappx = Find-WindowsSdkTool 'MakeAppx.exe'
  & $makeappx pack /d $stage /p $workMsix
  if ($LASTEXITCODE -ne 0) { throw "MakeAppx schema/package validation failed ($LASTEXITCODE)" }
  if ($Sign) {
    $cert = (Resolve-Path -LiteralPath $CertificatePath).Path
    $signtool = Find-WindowsSdkTool 'SignTool.exe'
    & $signtool sign /fd SHA256 /f $cert /p $CertificatePassword $workMsix
    if ($LASTEXITCODE -ne 0) { throw "SignTool failed ($LASTEXITCODE)" }
  }
  # Same-volume move is atomic and fails if another process created the destination.
  [IO.File]::Move($workMsix, $finalMsix)
  if ($SchemaOnly) {
    Write-Host "Created schema-only development package $finalMsix. No notice inventory was included; this historical-payload probe is not a distribution package and validates schema/payload only, not installation."
  } elseif ($Sign) {
    Write-Host "Created signed package $finalMsix. Signing does not install certificate trust or register the package."
  } else {
    Write-Host "Created unsigned package $finalMsix. MakeAppx package validation passed; this package is not installable until properly signed and trusted."
  }
} finally {
  Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
