[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$PackageFullName)
$ErrorActionPreference = 'Stop'
$ownedPackages = @(Get-AppxPackage -PackageTypeFilter Main | Where-Object { $_.PackageFullName -ceq $PackageFullName })
if ($ownedPackages.Count -ne 1 -or $ownedPackages[0].Name -cne 'Bytepleat.Desktop') {
  throw 'PackageFullName must identify exactly one registered Bytepleat.Desktop package for the current user.'
}
Remove-AppxPackage -Package $ownedPackages[0].PackageFullName
