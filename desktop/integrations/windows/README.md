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

The package script stages the manifest and the three generated PNG icons from `desktop/src-tauri/icons` into the package's required `Assets` paths. The actual app executable and COM DLL are copied from `AppDirectory` into the package so MakeAppx validates their referenced paths. This is a full MSIX package, not an external-location sparse package. It reads the PE machine type of both the app and DLL and rejects a mismatch with `-Architecture` before setting `ProcessorArchitecture`.

On Windows with the Windows SDK `makeappx.exe` available, run the unsigned path to make MakeAppx validate and pack the actual manifest and assets. This validates package structure/schema only; the result is unsigned, not trusted, and not installable:

```powershell
./package/Build-Package.ps1 -AppDirectory 'C:\path\to\Bytepleat' -Architecture x64
```

Signing is opt-in and requires a certificate supplied by the operator. The certificate subject must match `-Publisher`; the script neither creates a certificate nor installs trust. A signed package is still not trusted or registered automatically:

```powershell
./package/Build-Package.ps1 -AppDirectory 'C:\path\to\Bytepleat' `
  -Publisher 'CN=Publisher from supplied certificate' -Architecture ARM64 `
  -Sign -CertificatePath 'C:\certs\bytepleat.pfx' -CertificatePassword $env:BYTEPLEAT_PFX_PASSWORD
./package/Install-BytepleatPackage.ps1 -PackagePath ./package/out/Bytepleat-ARM64.msix
```

Installation is an explicit current-user `Add-AppxPackage` operation. Remove only the exact package full name reported by Windows:

```powershell
Get-AppxPackage -Name Bytepleat.Desktop | Select-Object Name, PackageFullName
./package/Uninstall-BytepleatPackage.ps1 -PackageFullName '<exact PackageFullName>'
```

Uninstall checks the exact package full name and owned package identity before removal. No wildcard package removal, all-user operation, global COM registry entry, or system-wide installation is used. The package scripts do not publish a production signature or claim Windows certification.

## Non-Windows static checks

```sh
python -m unittest discover -s integrations/windows/tests -v
```

These Python checks cover manifest structure and packaging source only. They are not Windows SDK schema validation. No native Windows build, package validation, or Explorer interaction result is claimed until the corresponding Windows CI job provides evidence.

## Microsoft references

- [Packaged desktop app File Explorer context menus](https://learn.microsoft.com/windows/apps/desktop/modernize/integrate-packaged-app-with-file-explorer)
- [Sparse packages](https://learn.microsoft.com/windows/apps/dev-tools/winapp-cli/guides/sparse)
- [Manual desktop MSIX packaging](https://learn.microsoft.com/windows/msix/desktop/desktop-to-uwp-manual-conversion)
- [uap:VisualElements manifest schema](https://learn.microsoft.com/uwp/schemas/appxpackage/uapmanifestschema/element-uap-visualelements)
- [Application manifest schema](https://learn.microsoft.com/uwp/schemas/appxpackage/uapmanifestschema/element-application)
- [IShellItemArray::GetAttributes](https://learn.microsoft.com/windows/win32/api/shobjidl_core/nf-shobjidl_core-ishellitemarray-getattributes)
