# Isolated mocks only: safe to run on non-Windows PowerShell, no Appx operations.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'PackageSmoke.Helpers.ps1')
$script:packages = @()
$script:removed = @()
function Get-AppxPackage { param([switch]$AllUsers, [string]$Name, [string]$ErrorAction) $script:packages }
function Remove-AppxPackage {
  param([string]$Package, [string]$ErrorAction)
  $script:removed += $Package
  if (-not $script:retain) { $script:packages = @($script:packages | Where-Object { $_.PackageFullName -cne $Package }) }
}
function Expect-Rejection([scriptblock]$Action) {
  $rejected = $false
  try { & $Action } catch { $rejected = $true }
  if (-not $rejected) { throw 'Expected refusal.' }
}
function Fixture([string]$Publisher='CN=unique-test', [string]$Name='Bytepleat.Desktop', [string]$Arch=$architecture, [string]$Version='0.1.0.0', [string]$FullName='exact-test-full-name') {
  [pscustomobject]@{ Name=$Name; Publisher=$Publisher; Architecture=$Arch; Version=[version]$Version; PackageFullName=$FullName }
}
foreach ($architecture in @('x64', 'ARM64')) {
  $script:packages = @()
  $script:removed = @()
  $script:retain = $false
  Assert-SmokeMachineClean
  $unrelated = Fixture -Publisher 'CN=unrelated' -FullName 'unrelated-full-name'
  $script:packages = @($unrelated)
  Expect-Rejection { Assert-SmokeMachineClean }
  Remove-SmokeOwnedPackage 'CN=unique-test' '0.1.0.0' '' -ExpectedArchitecture $architecture
  if ($script:removed.Count) { throw 'Removed unrelated publisher.' }
  foreach ($package in @((Fixture -Name 'Other.App'), (Fixture -Arch $(if ($architecture -eq 'x64') { 'ARM64' } else { 'X64' })), (Fixture -Version '9.0.0.0'))) {
    $script:packages = @($package)
    Remove-SmokeOwnedPackage 'CN=unique-test' '0.1.0.0' '' -ExpectedArchitecture $architecture
    if ($script:removed.Count) { throw 'Removed nonmatching identity.' }
  }
  $script:packages = @($unrelated, (Fixture))
  Expect-Rejection { Remove-SmokeOwnedPackage 'CN=unique-test' '0.1.0.0' 'different-full-name' -ExpectedArchitecture $architecture }
  if ($script:removed.Count) { throw 'Removed changed full name.' }
  $script:packages = @((Fixture), (Fixture -FullName 'duplicate'))
  Expect-Rejection { Remove-SmokeOwnedPackage 'CN=unique-test' '0.1.0.0' '' -ExpectedArchitecture $architecture }
  if ($script:removed.Count) { throw 'Removed ambiguous identity.' }
  foreach ($expected in @('exact-test-full-name', '')) {
    # Empty expected name covers registration followed by Add-AppxPackage failure.
    $script:packages = @($unrelated, (Fixture))
    $script:removed = @()
    Remove-SmokeOwnedPackage 'CN=unique-test' '0.1.0.0' $expected -ExpectedArchitecture $architecture
    if ($script:removed.Count -ne 1 -or $script:removed[0] -cne 'exact-test-full-name' -or
        $script:packages.Count -ne 1 -or $script:packages[0] -ne $unrelated) { throw 'Exact ownership cleanup failed.' }
  }
  $script:retain = $true
  $script:packages = @((Fixture))
  Expect-Rejection { Remove-SmokeOwnedPackage 'CN=unique-test' '0.1.0.0' 'exact-test-full-name' -ExpectedArchitecture $architecture }
  Write-Host 'Smoke ownership regression checks passed: preexisting refusal, exact/partial-install cleanup, unrelated identities, changed/ambiguous full names, cleanup failure.'
}
# All prerequisites must reject before any package/certificate/work-directory mutation.
Assert-SmokePrerequisites ARM64 Windows_NT Arm64 Arm64 ([version]'10.0.26200.0') ([version]'10.0.26200.0')
foreach ($case in @(
  @('ARM64', 'Windows_NT', 'Arm64', 'Arm64', '10.0.26100.0', '10.0.26200.0'),
  @('ARM64', 'Windows_NT', 'Arm64', 'X64', '10.0.26200.0', '10.0.26200.0'),
  @('ARM64', 'Windows_NT', 'X64', 'Arm64', '10.0.26200.0', '10.0.26200.0'),
  @('x64', 'Windows_NT', 'X64', 'X64', '10.0.26200.0', '10.0.26200.0'),
  @('ARM64', 'Unix', 'Arm64', 'Arm64', '10.0.26200.0', '10.0.26200.0'),
  @('ARM64', 'Windows_NT', 'Arm64', 'Arm64', '10.0.26200.0', '10.0.26100.0'),
  @('ARM64', 'Windows_NT', 'Arm64', 'Arm64', '10.0.26200.0', '10.0.26300.0')
)) {
  Expect-Rejection { Assert-SmokePrerequisites $case[0] $case[1] $case[2] $case[3] ([version]$case[4]) ([version]$case[5]) }
}
Write-Host 'Native ARM64 and OS minimum prerequisite regression checks passed.'

# Synthetic PE fixtures only; never execute a binary or touch Appx state.
$work = Join-Path ([IO.Path]::GetTempPath()) ('BytepleatProbeFixture-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $work
try {
  $path = Join-Path $work 'probe.bin'
  $valid = [byte[]]::new(128)
  $valid[0] = 0x4d; $valid[1] = 0x5a; $valid[0x3c] = 64
  $valid[64] = 0x50; $valid[65] = 0x45
  $valid[68] = 0x64; $valid[69] = 0xaa
  [IO.File]::WriteAllBytes($path, $valid)
  Assert-SmokeProbeArchitecture $path
  foreach ($mutation in @('x64', 'ARM64EC', 'signature', 'offset', 'truncated', 'dos')) {
    $bytes = $valid.Clone()
    switch ($mutation) {
      'x64' { $bytes[68] = 0x64; $bytes[69] = 0x86 }
      'ARM64EC' { $bytes[68] = 0x41; $bytes[69] = 0xa6 }
      'signature' { $bytes[64] = 0 }
      'offset' { $bytes[0x3c] = 127 }
      'truncated' { $bytes = [byte[]]::new(1) }
      'dos' { $bytes[0] = 0 }
    }
    [IO.File]::WriteAllBytes($path, $bytes)
    Expect-Rejection { Assert-SmokeProbeArchitecture $path }
  }
} finally { Remove-Item -LiteralPath $work -Recurse -Force }
Write-Host 'ARM64 probe PE architecture and malformed-header checks passed.'

# Exercise the exact offset-prefixed hex representation returned by fsutil.
$family = 'Bytepleat.Desktop_0123456789abcdef'
$aliasStrings = @($family, "$family!Bytepleat", 'C:\Program Files\WindowsApps\Bytepleat.Desktop_0.1.0.0_arm64__0123456789abcdef\bytepleat-desktop.exe', '0')
function New-AppExecLinkDump([string[]]$Strings, [uint32]$Version=3, [string]$Tag='0x8000001b') {
  $buffer = [Collections.Generic.List[byte]]::new()
  $buffer.AddRange([BitConverter]::GetBytes($Version))
  foreach ($value in $Strings) {
    $buffer.AddRange([Text.Encoding]::Unicode.GetBytes($value))
    $buffer.Add(0); $buffer.Add(0)
  }
  $lines = [Collections.Generic.List[string]]::new()
  $lines.Add("Reparse Tag Value : $Tag")
  $lines.Add('Reparse Data:')
  for ($offset = 0; $offset -lt $buffer.Count; $offset += 16) {
    $count = [Math]::Min(16, $buffer.Count - $offset)
    $hex = [Collections.Generic.List[string]]::new()
    for ($i = 0; $i -lt $count; $i++) { $hex.Add($buffer[$offset + $i].ToString('x2')) }
    $lines.Add(('{0:X4}:  {1}  {2}' -f $offset, ($hex -join ' '), ('.' * $count)))
  }
  return $lines -join "`n"
}
$validAlias = New-AppExecLinkDump $aliasStrings
Assert-SmokeExecutionAlias -Dump $validAlias -PackageFamilyName $family -ApplicationId 'Bytepleat'
$aliasCase = 0
foreach ($badAlias in @(
  (New-AppExecLinkDump $aliasStrings 3 '0xA000000C'),
  (New-AppExecLinkDump @('Bytepleat.Desktop_other', "$family!Bytepleat", $aliasStrings[2], '0')),
  (New-AppExecLinkDump @($family, "$family!WrongApp", $aliasStrings[2], '0')),
  (New-AppExecLinkDump $aliasStrings 2),
  (($validAlias -split "`n" | Select-Object -SkipLast 1) -join "`n"),
  ($validAlias -replace '(?m)^0000:.*$', 'invalid hex row'),
  ($validAlias -replace '(?m)^0010:', '0000:')
)) {
  $aliasCase++
  try { Assert-SmokeExecutionAlias -Dump $badAlias -PackageFamilyName $family -ApplicationId 'Bytepleat' }
  catch { continue }
  throw "Expected invalid execution alias fixture $aliasCase to be rejected."
}
Write-Host 'Execution alias reparse regression checks passed: valid package/app target and wrong tag, identity, app ID, version, truncation, malformed hex.'
