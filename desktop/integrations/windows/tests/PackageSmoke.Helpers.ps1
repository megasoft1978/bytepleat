# Pure prerequisite check, also exercised by non-Windows mocks.
function Assert-SmokePrerequisites(
  [string]$ExpectedArchitecture, [string]$OperatingSystem,
  [string]$NativeArchitecture, [string]$ProcessArchitecture,
  [version]$OSVersion, [version]$MinimumVersion
) {
  if ($ExpectedArchitecture -cne 'ARM64' -or $OperatingSystem -cne 'Windows_NT' -or
      $NativeArchitecture -ine $ExpectedArchitecture -or $ProcessArchitecture -ine $ExpectedArchitecture) {
    throw 'Requires native Windows ARM64 OS and PowerShell process; emulation is not accepted.'
  }
  if (-not $MinimumVersion -or $MinimumVersion -lt [version]'10.0.26200.0' -or
      -not $OSVersion -or $OSVersion -lt $MinimumVersion) {
    throw "Runner OS $OSVersion is below package minimum $MinimumVersion (floor 10.0.26200.0); no installation attempted."
  }
}

# Shared with the cleanup regression fixture. Never remove by package wildcard.
function Assert-SmokeMachineClean {
  $existing = @(Get-AppxPackage -AllUsers -Name 'Bytepleat.Desktop' -ErrorAction Stop)
  if ($existing.Count -ne 0) { throw 'Refusing smoke test: a preexisting Bytepleat.Desktop package is present.' }
}

function Get-SmokeOwnedPackage([string]$Publisher, [string]$Version,
  [Parameter(Mandatory=$true)][ValidateSet('x64','ARM64')][string]$ExpectedArchitecture) {
  $owned = @(Get-AppxPackage -Name 'Bytepleat.Desktop' -ErrorAction Stop | Where-Object {
    $_.Name -ceq 'Bytepleat.Desktop' -and $_.Publisher -ceq $Publisher -and
    $_.Version.ToString() -ceq $Version -and $_.Architecture.ToString() -ieq $ExpectedArchitecture
  })
  if ($owned.Count -gt 1) { throw 'Ambiguous smoke package ownership; refusing removal.' }
  return $owned
}

function Remove-SmokeOwnedPackage([string]$Publisher, [string]$Version, [string]$ExpectedFullName,
  [Parameter(Mandatory=$true)][ValidateSet('x64','ARM64')][string]$ExpectedArchitecture) {
  $owned = @(Get-SmokeOwnedPackage -Publisher $Publisher -Version $Version -ExpectedArchitecture $ExpectedArchitecture)
  if ($owned.Count -eq 0) { return }
  # A failed Add-AppxPackage can still register the unique test publisher. In that
  # case capture its exact full name here, never fall back to removing by Name.
  $fullName = $owned[0].PackageFullName
  if ([string]::IsNullOrWhiteSpace($fullName) -or ($ExpectedFullName -and $fullName -cne $ExpectedFullName)) {
    throw 'Smoke package full name changed; refusing removal.'
  }
  Remove-AppxPackage -Package $fullName -ErrorAction Stop
  if (@(Get-SmokeOwnedPackage -Publisher $Publisher -Version $Version -ExpectedArchitecture $ExpectedArchitecture).Count -ne 0) {
    throw "Smoke package cleanup did not unregister $fullName"
  }
}

function Assert-SmokeProbeArchitecture([string]$Path) {
  $stream = [IO.File]::OpenRead($Path)
  try {
    $reader = [IO.BinaryReader]::new($stream)
    if ($reader.ReadUInt16() -ne 0x5A4D) { throw 'Probe is not a PE executable.' }
    $stream.Position = 0x3c
    $offset = $reader.ReadUInt32()
    if ($offset -gt ($stream.Length - 6)) { throw 'Invalid probe PE offset.' }
    $stream.Position = $offset
    if ($reader.ReadUInt32() -ne 0x00004550 -or $reader.ReadUInt16() -ne 0xAA64) {
      throw 'Probe must be a native ARM64 PE executable.'
    }
  } finally { $stream.Dispose() }
}

# fsutil prints AppExecLink payload bytes as offset-prefixed hex rows. Parse the
# dump as bytes and validate the version-3 four-string list; searching its
# rendered hex text for package names would silently test the wrong thing.
function Assert-SmokeExecutionAlias([string]$Dump, [string]$PackageFamilyName, [string]$ApplicationId) {
  if ($Dump -notmatch '(?i)0x8000001b') { throw 'Alias is not an AppExecLink reparse point.' }
  $bytes = [Collections.Generic.List[byte]]::new()
  $expectedOffset = 0
  foreach ($line in ($Dump -split "`r?`n")) {
    if ($line -match '(?i)(?:^|\s)(?<offset>[0-9a-f]{4}):(?<data>.*)$') {
      if ([Convert]::ToInt32($Matches.offset, 16) -ne $expectedOffset) { throw 'AppExecLink hex rows have a missing, duplicate, or out-of-order offset.' }
      foreach ($token in ($Matches.data.Trim() -split '\s+')) {
        if ($token -cmatch '^[0-9a-fA-F]{2}$') { $bytes.Add([Convert]::ToByte($token, 16)) }
        else { break }
      }
      if ($bytes.Count -le $expectedOffset) { throw 'AppExecLink hex row does not contain any data bytes.' }
      $expectedOffset = $bytes.Count
    }
  }
  if ($bytes.Count -lt 14 -or (($bytes.Count - 4) % 2) -ne 0) { throw "AppExecLink reparse data is truncated or has an invalid UTF-16 length ($($bytes.Count) bytes parsed)." }
  if ($bytes[$bytes.Count - 2] -ne 0 -or $bytes[$bytes.Count - 1] -ne 0) { throw 'AppExecLink string list is missing its final UTF-16 terminator.' }
  if ([BitConverter]::ToUInt32($bytes.ToArray(), 0) -ne 3) { throw 'Unsupported AppExecLink reparse data version.' }
  $payload = [Text.Encoding]::Unicode.GetString($bytes.ToArray(), 4, $bytes.Count - 4)
  $strings = @($payload.Split([char]0) | Where-Object { $_.Length -gt 0 })
  if ($strings.Count -ne 4) { throw "Expected the four version-3 AppExecLink strings; found $($strings.Count)." }
  if ($strings[0] -cne $PackageFamilyName -or $strings[1] -cne "$PackageFamilyName!$ApplicationId") {
    throw 'Execution alias package identity or application ID does not match the installed package.'
  }
  if ($strings[2] -notmatch '(?i)[\\/]bytepleat-desktop\.exe$' -or $strings[3] -cne '0') {
    throw 'Execution alias executable path or desktop application type is unexpected.'
  }
}
