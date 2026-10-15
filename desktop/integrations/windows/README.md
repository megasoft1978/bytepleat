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

## ARM64 packaged integration smoke

The separate `windows-arm64-packaged-smoke` job in `.github/workflows/desktop.yml`
uses `windows-11-arm` for native ARM64 installation and runtime checks. It
downloads the existing ARM64 executable, matching notice inventory, and Explorer
DLL/console probe artifacts from the same workflow run, and copies only the exact
app and DLL into the package input directory. The regular x64/ARM64 unsigned
MakeAppx validation jobs and artifacts are unchanged. `Build-Package.ps1` builds
a separate signed development MSIX with a unique CI publisher and a one-day
self-signed code-signing certificate. It stays in a private temporary directory
and is not uploaded. The disposable runner requires administrator rights for
the temporary certificate trust entry; installation uses current-user
`Add-AppxPackage`, without provisioning other users.

`tests/Invoke-PackagedSmoke.ps1 -ExpectedArchitecture ARM64` fails closed unless
the OS and PowerShell process are both native ARM64, the probe is an ARM64 PE,
and the OS satisfies the manifest minimum, unchanged at `10.0.26200.0`.
GitHub's [public Windows 11 ARM64 runner image inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows11-Arm64-Readme.md)
reports OS `10.0.26200` for `windows-11-arm`; the script checks the actual runner
version on every run before creating test state. It refuses any preexisting
`Bytepleat.Desktop` package across users, an existing execution alias, or classic
COM registrations for the manifest CLSIDs.

The [Windows 11 ARM64 packaged integration smoke passed in CI](https://github.com/megasoft1978/bytepleat/actions/runs/38754501942)
against source tree `2a4295b17c0cfb9793887e3b512e3e26fb494554`, identical to
merged commit `5f45d4ce02d483c86655754fe25f92452d2b9b18`. It verifies package
registration, alias activation, packaged COM enumeration, and command invocation
with argument handoff to a test receiver. The script:

- Creates a certificate in `CurrentUser\My`, exports temporary PFX/CER files,
  and imports only its public certificate into `LocalMachine\TrustedPeople`.
- Builds and installs the signed ARM64 package; checks its exact name, unique
  publisher, version, architecture, and current-user package full name.
- Checks the registered manifest's execution alias and the WindowsApps alias
  reparse point's package family with `fsutil` before command invocation.
- Runs `BytepleatPackagedComSmoke.exe` with a 120-second deadline. This console
  test uses `CoCreateInstance(CLSCTX_LOCAL_SERVER)` for all four manifest CLSIDs,
  checks `IExplorerCommand` canonical IDs, titles and flags, and enumerates
  exactly the three expected flyout children. It then calls the packaged
  Compress command with two real temporary file selections and Extract/Open
  with one selection each. The test package substitutes a tiny ARM64 console
  receiver for the GUI executable; the receiver captures parsed arguments and
  exits. The test verifies each action flag, `--` terminator, and every path,
  including spaces and Unicode, without launching Bytepleat's UI or controlling
  Explorer. It uses Windows packaged COM registration and the real installed
  app-execution alias; it does not load the DLL directly. This proves packaged
  COM invocation and command-line handoff to the test receiver, not that the
  production GUI consumes the arguments correctly or that a visible Explorer
  menu renders and invokes successfully.
- In `finally`, terminates only its own probe if needed, uninstalls only the exact
  current-user package matching the unique test identity (including registration
  after a failed installation), removes the exact temporary certificate
  thumbprint from both stores and its private key, and deletes only its private
  work directory. Cleanup attempts continue after errors and any cleanup error
  fails the step. As with any `finally`, forced runner termination can prevent
  cleanup; the outer step has a ten-minute timeout and runs on a disposable VM.

The workflow logs the runner OS version, signed test MSIX SHA256, exact package
full name, individual checks, and cleanup result. The passing run establishes
current-user development installation, registration/alias inspection, packaged
COM activation/enumeration, and argument handoff to its test receiver on that
native ARM64 runner. It neither launches nor controls the runner desktop,
displays Explorer menus, verifies production GUI startup, establishes consumer
signing trust, nor establishes x64 installed-package behavior.

The ownership regression fixture uses mocks only and also runs on non-Windows
PowerShell:

```powershell
pwsh -NoProfile -File ./tests/PackageSmokeCleanupTests.ps1
```

## Non-Windows static checks

```sh
python -m unittest discover -s integrations/windows/tests -v
```

These Python checks cover manifest structure and static packaging-source properties only. They are not a PowerShell runtime fixture test, Windows SDK schema validation, installation test, or Explorer interaction test. Native Windows CI validates compilation and MakeAppx packaging on its configured runner; the passing ARM64 smoke above adds current-user installation and packaged COM checks. Interactive Explorer behavior and broad Windows compatibility still require separate evidence.

## Microsoft references

- [Packaged desktop app File Explorer context menus](https://learn.microsoft.com/windows/apps/desktop/modernize/integrate-packaged-app-with-file-explorer)
- [Sparse packages](https://learn.microsoft.com/windows/apps/dev-tools/winapp-cli/guides/sparse)
- [Manual desktop MSIX packaging](https://learn.microsoft.com/windows/msix/desktop/desktop-to-uwp-manual-conversion)
- [uap:VisualElements manifest schema](https://learn.microsoft.com/uwp/schemas/appxpackage/uapmanifestschema/element-uap-visualelements)
- [Application manifest schema](https://learn.microsoft.com/uwp/schemas/appxpackage/uapmanifestschema/element-application)
- [IShellItemArray::GetAttributes](https://learn.microsoft.com/windows/win32/api/shobjidl_core/nf-shobjidl_core-ishellitemarray-getattributes)

- [Development package certificate and temporary trust](https://learn.microsoft.com/windows/msix/package/create-certificate-package-signing)
- [GitHub Windows 11 ARM64 runner image and OS version](https://github.com/actions/runner-images/blob/main/images/windows/Windows11-Arm64-Readme.md)
