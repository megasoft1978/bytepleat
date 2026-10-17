[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateSet('ARM64')][string]$ExpectedArchitecture,
  [Parameter(Mandatory=$true)][string]$AppDirectory,
  [Parameter(Mandatory=$true)][string]$NoticeDirectory,
  [Parameter(Mandatory=$true)][string]$ComTestPath,
  [Parameter(Mandatory=$true)][string]$InvocationProbePath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'PackageSmoke.Helpers.ps1')
if ($env:OS -ne 'Windows_NT') { throw 'Requires Windows; no state changed.' }
$manifest = [xml](Get-Content -LiteralPath (Join-Path $PSScriptRoot '../package/AppxManifest.xml') -Raw)
$minimum = [version]$manifest.Package.Dependencies.TargetDeviceFamily.MinVersion
$osVersion = [version](Get-CimInstance Win32_OperatingSystem).Version
$osVersion = [version]::new($osVersion.Major, $osVersion.Minor, $osVersion.Build, [Math]::Max(0, $osVersion.Revision))
Assert-SmokePrerequisites -ExpectedArchitecture $ExpectedArchitecture -OperatingSystem $env:OS `
  -NativeArchitecture ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()) `
  -ProcessArchitecture ([Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()) `
  -OSVersion $osVersion -MinimumVersion $minimum
# This script is intended for a disposable elevated CI runner, not a user machine.
Assert-SmokeMachineClean
$aliasPath = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\bytepleat-desktop.exe'
if (Test-Path -LiteralPath $aliasPath) { throw 'Refusing to replace a preexisting app execution alias.' }
# Reject classic COM registrations that could shadow the packaged classes.
foreach ($id in @('6C987D21-07A4-4D7B-992C-2E2D6F5D1001', '6C987D22-07A4-4D7B-992C-2E2D6F5D1002',
                  '6C987D23-07A4-4D7B-992C-2E2D6F5D1003', '6C987D24-07A4-4D7B-992C-2E2D6F5D1004')) {
  foreach ($hive in @('HKEY_CURRENT_USER', 'HKEY_LOCAL_MACHINE')) {
    if (Test-Path -LiteralPath "Registry::$hive\Software\Classes\CLSID\{$id}") { throw "Preexisting classic COM registration: $id" }
  }
}
$comTest = (Resolve-Path -LiteralPath $ComTestPath).Path
# Validate probe artifacts before creating any certificate or install state.
Assert-SmokeProbeArchitecture -Path $comTest
$invocationProbe = (Resolve-Path -LiteralPath $InvocationProbePath).Path
Assert-SmokeProbeArchitecture -Path $invocationProbe
$publisher = 'CN=Bytepleat CI ' + [guid]::NewGuid().ToString('N')
$version = $manifest.Package.Identity.Version
$work = Join-Path ([IO.Path]::GetTempPath()) ('BytepleatPackagedSmoke-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $work
$cert = $null
$fullName = $null
$installAttempted = $false
$trustOwned = $false
$process = $null
$probeExitCode = $null
$priorSelectionOne = [Environment]::GetEnvironmentVariable('BYTEPLEAT_SMOKE_SELECTION_1', 'Process')
$priorSelectionTwo = [Environment]::GetEnvironmentVariable('BYTEPLEAT_SMOKE_SELECTION_2', 'Process')
try {
  $cert = New-SelfSignedCertificate -Type Custom -Subject $publisher -KeyUsage DigitalSignature `
    -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 -KeyExportPolicy Exportable `
    -CertStoreLocation 'Cert:\CurrentUser\My' -NotAfter (Get-Date).AddDays(1) `
    -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3', '2.5.29.19={text}')
  $cer = Join-Path $work 'development.cer'
  $pfx = Join-Path $work 'development.pfx'
  $password = [guid]::NewGuid().ToString('N')
  $securePassword = ConvertTo-SecureString $password -AsPlainText -Force
  $null = Export-Certificate -Cert $cert -FilePath $cer
  $null = Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $securePassword
  $trustPath = 'Cert:\LocalMachine\TrustedPeople\' + $cert.Thumbprint
  if (Test-Path -LiteralPath $trustPath) { throw 'Unexpected preexisting certificate thumbprint.' }
  $trustOwned = $true
  $null = Import-Certificate -FilePath $cer -CertStoreLocation 'Cert:\LocalMachine\TrustedPeople'
  # Build a private test package whose application binary is a tiny console
  # receiver. The real packaged Explorer DLL and package alias invoke it; it
  # records argv and exits, avoiding app UI or Explorer desktop automation.
  $invocationApp = Join-Path $work 'invocation-app'
  $null = New-Item -ItemType Directory -Path $invocationApp
  Copy-Item -LiteralPath (Join-Path (Resolve-Path -LiteralPath $AppDirectory).Path 'BytepleatExplorerCommands.dll') -Destination $invocationApp
  Copy-Item -LiteralPath $invocationProbe -Destination (Join-Path $invocationApp 'bytepleat-desktop.exe')
  & (Join-Path $PSScriptRoot '../package/Build-Package.ps1') -AppDirectory $invocationApp `
    -NoticeDirectory $NoticeDirectory -Architecture $ExpectedArchitecture -Publisher $publisher -Sign `
    -CertificatePath $pfx -CertificatePassword $password -OutputDirectory (Join-Path $work 'package')
  $msix = Join-Path $work "package/Bytepleat-$ExpectedArchitecture.msix"
  Write-Host "Smoke MSIX SHA256: $((Get-FileHash -LiteralPath $msix -Algorithm SHA256).Hash); runner OS: $osVersion"
  # Repeat immediately before deployment; never upgrade an existing Bytepleat.
  Assert-SmokeMachineClean
  $installAttempted = $true
  Add-AppxPackage -Path $msix -ErrorAction Stop
  $registered = @(Get-SmokeOwnedPackage -Publisher $publisher -Version $version -ExpectedArchitecture $ExpectedArchitecture)
  if ($registered.Count -ne 1) { throw "Expected exactly one current-user $ExpectedArchitecture smoke package registration." }
  $fullName = $registered[0].PackageFullName
  Write-Host "Registered smoke package: $fullName"
  $installedManifest = Get-AppxPackageManifest -Package $fullName
  $aliases = @($installedManifest.SelectNodes("//*[local-name()='ExecutionAlias']"))
  if ($aliases.Count -ne 1 -or $aliases[0].Alias -cne 'bytepleat-desktop.exe') { throw 'Registered manifest alias mismatch.' }
  $alias = Get-Item -LiteralPath $aliasPath -Force
  if (-not ($alias.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Execution alias is not a reparse point.' }
  # Inspect only; never execute the app alias. fsutil output includes the owning
  # package family and application ID for an AppExecLink, independent of locale.
  $aliasData = & fsutil.exe reparsepoint query $aliasPath 2>&1 | Out-String
  if ($LASTEXITCODE -ne 0) { throw "Could not read execution alias reparse data: $aliasData" }
  Assert-SmokeExecutionAlias -Dump $aliasData -PackageFamilyName $registered[0].PackageFamilyName -ApplicationId 'Bytepleat'
  Write-Host 'Registered manifest and current-user package-family alias reparse point verified (not executed).'
  $selectionOne = Join-Path $work 'selection one-ñ.txt'
  $selectionTwo = Join-Path $work 'selection & two.txt'
  $null = Set-Content -LiteralPath $selectionOne -Value 'first test selection' -NoNewline
  $null = Set-Content -LiteralPath $selectionTwo -Value 'second test selection' -NoNewline
  [Environment]::SetEnvironmentVariable('BYTEPLEAT_SMOKE_SELECTION_1', $selectionOne, 'Process')
  [Environment]::SetEnvironmentVariable('BYTEPLEAT_SMOKE_SELECTION_2', $selectionTwo, 'Process')
  $stdout = Join-Path $work 'com.stdout'
  $stderr = Join-Path $work 'com.stderr'
  $process = Start-Process -FilePath $comTest -NoNewWindow -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
  if (-not $process.WaitForExit(120000)) { throw 'Packaged COM smoke exceeded 120 seconds.' }
  $process.WaitForExit()
  $probeExitCode = if ($null -ne $process.ExitCode) { $process.ExitCode } else { 'unknown' }
  Get-Content -LiteralPath $stdout | Write-Host
  Get-Content -LiteralPath $stderr | Write-Host
  if ($probeExitCode -ne 0) {
    $probeOutput = (@($stdout, $stderr) | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object { Get-Content -LiteralPath $_ -Raw }) -join "`n"
    $hint = if ($probeOutput -match '0x80040154') { "`nHint: packaged COM activation fails from an elevated (High integrity) token on machines with UAC enabled, while Explorer runs at Medium integrity. The package registration is per user; re-run the activation probe from a non-elevated shell or an interactive scheduled task at -RunLevel Limited. See desktop/integrations/windows/README.md." } else { '' }
    throw "Packaged COM smoke failed (exit code $probeExitCode; stdout: $stdout; stderr: $stderr).$hint"
  }
} finally {
  # Attempt every cleanup even if an earlier cleanup fails; fail the step on any
  # cleanup error. No all-user uninstall, wildcard certificate deletion, alias
  # deletion, registry edits, desktop process kill, or shared-directory removal.
  $cleanupErrors = [Collections.Generic.List[string]]::new()
  $cleanup = @(
    { [Environment]::SetEnvironmentVariable('BYTEPLEAT_SMOKE_SELECTION_1', $priorSelectionOne, 'Process'); [Environment]::SetEnvironmentVariable('BYTEPLEAT_SMOKE_SELECTION_2', $priorSelectionTwo, 'Process') },
    { if ($process -and -not $process.HasExited) { $process.Kill(); if (-not $process.WaitForExit(10000)) { throw 'Owned COM probe did not exit after termination.' } }; if ($process) { $process.Dispose() } },
    { if ($installAttempted) { Remove-SmokeOwnedPackage -Publisher $publisher -Version $version -ExpectedFullName $fullName -ExpectedArchitecture $ExpectedArchitecture } },
    { if ($cert -and $trustOwned) { $path = 'Cert:\LocalMachine\TrustedPeople\' + $cert.Thumbprint; if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force } } },
    { if ($cert) { $path = 'Cert:\CurrentUser\My\' + $cert.Thumbprint; if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -DeleteKey -Force } } },
    { Remove-Item -LiteralPath $work -Recurse -Force }
  )
  foreach ($action in $cleanup) {
    try { & $action } catch { $cleanupErrors.Add($_.Exception.Message); Write-Warning "Smoke cleanup: $_" }
  }
  if ($cleanupErrors.Count) { throw ('Smoke cleanup failed: ' + ($cleanupErrors -join '; ')) }
  Write-Host 'Smoke cleanup completed: exact test package, temporary certificate/private key, and private work directory.'
}
