#include <windows.h>
#include <shellapi.h>
#include <cstdio>
#include <string>
#include <cwchar>

// Test-only package application. The packaged Explorer command starts the
// app execution alias; this receiver records the parsed argv and exits without
// showing a window. The parent smoke test owns the temporary capture path.
int wmain() {
    int argc = 0;
    LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv || argc < 4 || argc > 4097 || std::wcscmp(argv[2], L"--") != 0) {
        if (argv) LocalFree(argv);
        return 4;
    }
    // Derive the capture location from the first selected file. This avoids
    // relying on custom environment variables propagating through the package
    // COM surrogate and ShellExecute activation boundary.
    DWORD pathSize = GetFullPathNameW(argv[3], 0, nullptr, nullptr);
    if (!pathSize || pathSize > 32767) { LocalFree(argv); return 2; }
    std::wstring capture(pathSize, L'\0');
    DWORD pathChars = GetFullPathNameW(argv[3], pathSize, capture.data(), nullptr);
    if (!pathChars || pathChars >= pathSize) { LocalFree(argv); return 3; }
    capture.resize(pathChars);
    size_t separator = capture.find_last_of(L"\\/");
    if (separator == std::wstring::npos) { LocalFree(argv); return 3; }
    capture.resize(separator + 1);
    capture += L".bytepleat-smoke-argv.bin";
    HANDLE file = CreateFileW(capture.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
                              FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) { LocalFree(argv); return 5; }
    DWORD count = static_cast<DWORD>(argc), written = 0;
    bool ok = WriteFile(file, &count, sizeof(count), &written, nullptr) && written == sizeof(count);
    for (int i = 0; ok && i < argc; ++i) {
        DWORD chars = static_cast<DWORD>(wcslen(argv[i]));
        ok = WriteFile(file, &chars, sizeof(chars), &written, nullptr) && written == sizeof(chars);
        if (ok && chars) {
            DWORD bytes = chars * sizeof(wchar_t);
            ok = WriteFile(file, argv[i], bytes, &written, nullptr) && written == bytes;
        }
    }
    if (ok) ok = FlushFileBuffers(file) != FALSE;
    CloseHandle(file);
    LocalFree(argv);
    return ok ? 0 : 6;
}
