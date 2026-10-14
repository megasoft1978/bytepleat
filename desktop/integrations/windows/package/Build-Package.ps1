[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$AppDirectory,
  [string]$Publisher = 'CN=Bytepleat Development',
  [string]$CertificatePath,
  [string]$CertificatePassword,
  [switch]$Sign,
  [string]$OutputDirectory = "$PSScriptRoot\out",
  [ValidateSet('x64','ARM64')][string]$Architecture = 'x64'
)
$ErrorActionPreference = 'Stop'
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
      foreach ($architecture in @('x64','arm64','x86')) {
        $candidates.Add((Join-Path $version.FullName "$architecture\$Name"))
      }
    }
  }
  $candidates.Add((Join-Path $kitsRoot "App Certification Kit\$Name"))
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
  }
  throw "Could not find $Name in installed Windows Kits 10 SDK directories under '$kitsRoot'. Install the Windows SDK component; this script does not download tools."
}
$expectedMachine = if ($Architecture -eq 'x64') { 0x8664 } else { 0xAA64 }
foreach ($binary in @('bytepleat-desktop.exe','BytepleatExplorerCommands.dll')) {
  $machine = Get-PeMachine (Join-Path $app $binary)
  if ($machine -ne $expectedMachine) { throw "$binary PE machine 0x$('{0:X4}' -f $machine) does not match requested $Architecture package architecture." }
}
if ($Sign -and (-not $CertificatePath -or $null -eq $CertificatePassword)) {
  throw 'Signing requires both CertificatePath and CertificatePassword. Omit -Sign for unsigned schema/package validation.'
}
$manifest = Join-Path $PSScriptRoot 'AppxManifest.xml'
$xml = [xml](Get-Content -LiteralPath $manifest -Raw)
$xml.Package.Identity.Publisher = $Publisher
$xml.Package.Identity.ProcessorArchitecture = $Architecture.ToLowerInvariant()
$stage = Join-Path ([IO.Path]::GetTempPath()) ("BytepleatPackage-" + [guid]::NewGuid().ToString('N'))
$out = [IO.Path]::GetFullPath($OutputDirectory)
$null = New-Item -ItemType Directory -Path $stage
$null = New-Item -ItemType Directory -Force -Path $out
try {
  # Include the actual payload so MakeAppx can validate executable and COM paths.
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
  $xml.Save((Join-Path $stage 'AppxManifest.xml'))
  $msix = Join-Path $out "Bytepleat-$Architecture.msix"
  $makeappx = Find-WindowsSdkTool 'MakeAppx.exe'
  & $makeappx pack /d $stage /p $msix /o
  if ($LASTEXITCODE -ne 0) { throw "MakeAppx schema/package validation failed ($LASTEXITCODE)" }
  if ($Sign) {
    $cert = (Resolve-Path -LiteralPath $CertificatePath).Path
    $signtool = Find-WindowsSdkTool 'SignTool.exe'
    & $signtool sign /fd SHA256 /f $cert /p $CertificatePassword $msix
    if ($LASTEXITCODE -ne 0) { throw "SignTool failed ($LASTEXITCODE)" }
    Write-Host "Created signed package $msix. Signing does not install certificate trust or register the package."
  } else {
    Write-Host "Created unsigned package $msix. MakeAppx package validation passed; this package is not installable until properly signed and trusted."
  }
} finally {
  Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
