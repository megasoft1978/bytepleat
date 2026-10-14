# Windows File Explorer integration

This directory contains the native `IExplorerCommand` DLL and full MSIX source for the Bytepleat Tauri desktop executable. The package identity declares one File Explorer flyout with **Compress with Bytepleat**, **Extract with Bytepleat**, and **Open in Bytepleat** children. Commands pass the complete multi-selection using the Windows `CommandLineToArgvW` quoting convention.

## Build and native checks

Use Visual Studio 2022 with the C++ workload, Windows 11 SDK, and CMake 3.24 or newer. Configure and compile both architectures with the matching generator platform:

```powershell
cmake -S . -B build-x64 -A x64
cmake --build build-x64 --config Release
ctest --test-dir build-x64 -C Release --output-on-failure
cmake -S . -B build-arm64 -A ARM64
cmake --build build-arm64 --config Release
```

The x64 CTest executable uses `CommandLineToArgvW` and loads the just-built DLL to exercise its exported class factory and COM enumerator. ARM64 builds compile the same test executable for compile coverage; CTest does not try to run it on a non-ARM64 host. These checks do not prove Explorer behavior or package installation.

The app alias must be registered by the package as `bytepleat-desktop.exe`. The shell extension resolves it only under the current user's `%LOCALAPPDATA%\Microsoft\WindowsApps` alias directory. It does not search `PATH`, invoke a shell, or traverse archive contents. `GetState` uses selection count, filesystem attributes, and a bounded extension check. It enables compression for filesystem selections and extraction/open only for one file with a supported archive suffix.

The DLL uses the dynamic MSVC runtime. The package payload must contain the matching architecture build of `bytepleat-desktop.exe`, its Tauri runtime files, and `BytepleatExplorerCommands.dll`; provision the matching supported Visual C++ runtime as required by that build. x64 and ARM64 DLLs are not interchangeable.

## Package validation and signing

The package script stages the manifest and the three generated PNG icons from `desktop/src-tauri/icons` into the package's required `Assets` paths. It copies the app executable and COM DLL from `AppDirectory`, checks their PE machine type, and rejects a mismatch with `-Architecture`. This is a full MSIX package, not an external-location sparse package.

Every regular package build requires `-NoticeDirectory` pointing to the output directory from `desktop/scripts/collect-desktop-notices.py`. The report must be schema 1 for Cargo project `bytepleat-desktop` version `0.1.0`, and its target must match the package exactly: `x86_64-pc-windows-msvc` for `x64` or `aarch64-pc-windows-msvc` for `ARM64`. The packager checks each listed relative path and SHA256, rejects traversal, backslashes and symlink/reparse points, and enforces file-count and size bounds. It includes the repository `LICENSE`, only the inventoried Cargo and runtime notice files, and the unmodified `THIRD-PARTY.json` under `Notices/`. That report retains unresolved gaps and its source findings; it is an informational inventory and does not claim legal clearance or runtime verification. The packager does not recursively copy arbitrary input-directory contents.

Example regular build with a previously generated matching artifact:

```powershell
./package/Build-Package.ps1 -AppDirectory 'C:\path\to\Bytepleat' `
  -NoticeDirectory 'C:\path\to\windows-x64-notices' -Architecture x64
```

`-SchemaOnly` is an explicit developer probe for a historical payload that predates notice artifacts. It can omit notices, cannot be combined with `-Sign` or `-NoticeDirectory`, and prints that the result is not a distribution package. It checks MakeAppx schema and payload only; it does not validate installation or Explorer behavior. A normal build does not have this exception.

MakeAppx builds into a private temporary work directory outside the staged payload. Optional signing happens there, then the completed MSIX is moved to the final output path without replacement. An existing final path causes an error. The temporary directory is removed on success or failure. The script does not create certificates, establish certificate trust, or install/register packages. Keep signing passwords in the calling environment; they are not written to a report.

On Windows with the Windows SDK `makeappx.exe` available, run a regular unsigned package build with the matching notice artifact. This validates package structure/schema only; the result is unsigned, not trusted, and not installable:

```powershell
./package/Build-Package.ps1 -AppDirectory 'C:\path\to\Bytepleat' `
  -NoticeDirectory 'C:\path\to\windows-x64-notices' -Architecture x64
```

Signing is opt-in and requires a certificate supplied by the operator. The certificate subject must match `-Publisher`; the script neither creates a certificate nor installs trust. A signed package is still not trusted or registered automatically:

```powershell
./package/Build-Package.ps1 -AppDirectory 'C:\path\to\Bytepleat' `
  -NoticeDirectory 'C:\path\to\windows-arm64-notices' `
  -Publisher 'CN=Publisher from supplied certificate' -Architecture ARM64 `
  -Sign -CertificatePath 'C:\certs\bytepleat.pfx' -CertificatePassword $env:BYTEPLEAT_PFX_PASSWORD
./package/Install-BytepleatPackage.ps1 -PackagePath ./package/out/Bytepleat-ARM64.msix
```

Installation is an explicit current-user `Add-AppxPackage` operation. A successful package build alone does not establish installation or runtime behavior. Remove only the exact package full name reported by Windows:

```powershell
Get-AppxPackage -Name Bytepleat.Desktop | Select-Object Name, PackageFullName
./package/Uninstall-BytepleatPackage.ps1 -PackageFullName '<exact PackageFullName>'
```

Uninstall checks the exact package full name and owned package identity before removal. No wildcard package removal, all-user operation, global COM registry entry, or system-wide installation is used. The package scripts do not publish a production signature or claim Windows certification.

## Non-Windows static checks

```sh
python -m unittest discover -s integrations/windows/tests -v
```

These Python checks cover manifest structure and static packaging-source properties only. They are not a PowerShell runtime fixture test, Windows SDK schema validation, installation test, or Explorer interaction test. Native Windows CI can validate compilation and MakeAppx packaging on its configured runner. Actual behavior still requires installation and exercise on Windows 11; a CI package result does not establish native Explorer behavior or broad Windows compatibility. This alpha integration has no runtime verification claim unless a specific run supplies that evidence.

## Microsoft references

- [Packaged desktop app File Explorer context menus](https://learn.microsoft.com/windows/apps/desktop/modernize/integrate-packaged-app-with-file-explorer)
- [Sparse packages](https://learn.microsoft.com/windows/apps/dev-tools/winapp-cli/guides/sparse)
- [Manual desktop MSIX packaging](https://learn.microsoft.com/windows/msix/desktop/desktop-to-uwp-manual-conversion)
- [uap:VisualElements manifest schema](https://learn.microsoft.com/uwp/schemas/appxpackage/uapmanifestschema/element-uap-visualelements)
- [Application manifest schema](https://learn.microsoft.com/uwp/schemas/appxpackage/uapmanifestschema/element-application)
- [IShellItemArray::GetAttributes](https://learn.microsoft.com/windows/win32/api/shobjidl_core/nf-shobjidl_core-ishellitemarray-getattributes)
