#if !defined(_M_ARM64) || defined(_M_ARM64EC)
#error Packaged COM smoke requires a native ARM64 build.
#endif
#include <windows.h>
#include <shobjidl.h>
#include <wrl/client.h>
#include <cstdio>
#include <cwchar>
#include <utility>
#include <vector>

using Microsoft::WRL::ComPtr;

static const CLSID classes[] = {
    {0x6c987d21,0x07a4,0x4d7b,{0x99,0x2c,0x2e,0x2d,0x6f,0x5d,0x10,0x01}},
    {0x6c987d22,0x07a4,0x4d7b,{0x99,0x2c,0x2e,0x2d,0x6f,0x5d,0x10,0x02}},
    {0x6c987d23,0x07a4,0x4d7b,{0x99,0x2c,0x2e,0x2d,0x6f,0x5d,0x10,0x03}},
    {0x6c987d24,0x07a4,0x4d7b,{0x99,0x2c,0x2e,0x2d,0x6f,0x5d,0x10,0x04}},
};
static const wchar_t* titles[] = {
    L"Bytepleat", L"Compress with Bytepleat", L"Extract with Bytepleat", L"Open in Bytepleat"
};

static std::wstring Environment(const wchar_t* name) {
    DWORD size = GetEnvironmentVariableW(name, nullptr, 0);
    if (!size || size > 32767) throw E_INVALIDARG;
    std::wstring value(size, L'\0');
    DWORD copied = GetEnvironmentVariableW(name, value.data(), size);
    if (!copied || copied >= size) throw HRESULT_FROM_WIN32(GetLastError());
    value.resize(copied);
    return value;
}

static void Check(HRESULT hr, const char* operation) {
    if (FAILED(hr)) {
        std::fprintf(stderr, "%s failed: HRESULT 0x%08lX\n", operation, static_cast<unsigned long>(hr));
        throw hr;
    }
}

static void Verify(IExplorerCommand* command, unsigned index) {
    GUID id{};
    Check(command->GetCanonicalName(&id), "GetCanonicalName");
    Check(IsEqualGUID(id, classes[index]) ? S_OK : E_UNEXPECTED, "canonical ID");
    PWSTR title = nullptr;
    HRESULT hr = command->GetTitle(nullptr, &title);
    bool matches = title && std::wcscmp(title, titles[index]) == 0;
    CoTaskMemFree(title);
    Check(hr, "GetTitle");
    Check(matches ? S_OK : E_UNEXPECTED, "title");
    EXPCMDFLAGS flags{};
    Check(command->GetFlags(&flags), "GetFlags");
    Check(flags == (index == 0 ? ECF_HASSUBCOMMANDS : ECF_DEFAULT) ? S_OK : E_UNEXPECTED, "flags");
}

static bool ReadDword(HANDLE file, DWORD& value) {
    DWORD read = 0;
    return ReadFile(file, &value, sizeof(value), &read, nullptr) && read == sizeof(value);
}

static bool ReadString(HANDLE file, std::wstring& value) {
    DWORD chars = 0;
    if (!ReadDword(file, chars) || chars > 32767) return false;
    value.resize(chars);
    if (!chars) return true;
    DWORD read = 0;
    return ReadFile(file, value.data(), chars * sizeof(wchar_t), &read, nullptr) && read == chars * sizeof(wchar_t);
}

static std::vector<std::wstring> ReadCapture(const std::wstring& path) {
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, 0, nullptr, OPEN_EXISTING,
                              FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return {};
    DWORD count = 0;
    std::vector<std::wstring> args;
    bool valid = ReadDword(file, count) && count >= 1 && count <= 4097;
    for (DWORD i = 0; valid && i < count; ++i) {
        std::wstring arg;
        valid = ReadString(file, arg);
        if (valid) args.push_back(std::move(arg));
    }
    CloseHandle(file);
    return valid && args.size() == count ? args : std::vector<std::wstring>{};
}

static void InvokeAndVerify(const CLSID& clsid, const wchar_t* verb,
                            const std::vector<std::wstring>& paths, const std::wstring& capture) {
    DeleteFileW(capture.c_str());
    std::vector<PIDLIST_ABSOLUTE> pidls;
    std::vector<PCIDLIST_ABSOLUTE> idLists;
    pidls.reserve(paths.size());
    idLists.reserve(paths.size());
    for (const auto& path : paths) {
        PIDLIST_ABSOLUTE pidl = nullptr;
        Check(SHParseDisplayName(path.c_str(), nullptr, &pidl, 0, nullptr), "SHParseDisplayName selection");
        pidls.push_back(pidl);
        idLists.push_back(pidl);
    }
    ComPtr<IShellItemArray> items;
    HRESULT hr = SHCreateShellItemArrayFromIDLists(static_cast<UINT>(idLists.size()),
        idLists.data(), items.GetAddressOf());
    for (auto pidl : pidls) CoTaskMemFree(pidl);
    Check(hr, "SHCreateShellItemArrayFromIDLists");
    ComPtr<IExplorerCommand> command;
    Check(CoCreateInstance(clsid, nullptr, CLSCTX_LOCAL_SERVER, IID_PPV_ARGS(command.GetAddressOf())),
          "activate packaged invocation command");
    Check(command->Invoke(items.Get(), nullptr), "packaged IExplorerCommand::Invoke");

    std::vector<std::wstring> actual;
    ULONGLONG deadline = GetTickCount64() + 15000;
    do {
        actual = ReadCapture(capture);
        if (!actual.empty()) break;
        Sleep(50);
    } while (GetTickCount64() < deadline);
    Check(actual.empty() ? HRESULT_FROM_WIN32(ERROR_TIMEOUT) : S_OK, "app execution-alias handoff deadline");
    Check(actual.size() == paths.size() + 3 ? S_OK : E_UNEXPECTED, "handoff argument count");
    size_t exeSeparator = actual[0].find_last_of(L"\\/");
    Check(actual[0].substr(exeSeparator == std::wstring::npos ? 0 : exeSeparator + 1) ==
          L"bytepleat-desktop.exe" ? S_OK : E_UNEXPECTED, "packaged executable identity");
    Check(actual[1] == verb ? S_OK : E_UNEXPECTED, "handoff action");
    Check(actual[2] == L"--" ? S_OK : E_UNEXPECTED, "handoff option terminator");
    for (size_t i = 0; i < paths.size(); ++i)
        Check(actual[i + 3] == paths[i] ? S_OK : E_UNEXPECTED, "handoff selected path");
    std::printf("Packaged %ls command handed %zu selection(s) to the test receiver.\n", verb, paths.size());
}

int main() {
    USHORT processMachine = 0, nativeMachine = 0;
    if (!IsWow64Process2(GetCurrentProcess(), &processMachine, &nativeMachine) ||
        processMachine != IMAGE_FILE_MACHINE_UNKNOWN || nativeMachine != IMAGE_FILE_MACHINE_ARM64) {
        std::fputs("Requires a native ARM64 process and OS.\n", stderr);
        return 1;
    }
    HRESULT hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    if (FAILED(hr)) { std::fprintf(stderr, "CoInitializeEx: 0x%08lX\n", static_cast<unsigned long>(hr)); return 1; }
    int result = 0;
    try {
        // Use Windows package registration and the COM surrogate. No direct
        // DLL loading, registration fallback, or shell UI is used; selections
        // below are test-owned and Invoke is exercised explicitly.
        for (unsigned i = 0; i < 4; ++i) {
            ComPtr<IExplorerCommand> command;
            Check(CoCreateInstance(classes[i], nullptr, CLSCTX_LOCAL_SERVER,
                                   IID_PPV_ARGS(command.GetAddressOf())), "CoCreateInstance");
            Check(command ? S_OK : E_UNEXPECTED, "activated command");
            Verify(command.Get(), i);
            if (i == 0) {
                ComPtr<IEnumExplorerCommand> enumerator;
                Check(command->EnumSubCommands(enumerator.GetAddressOf()), "EnumSubCommands");
                Check(enumerator ? S_OK : E_UNEXPECTED, "enumerator");
                for (unsigned child = 1; child <= 3; ++child) {
                    ComPtr<IExplorerCommand> item;
                    ULONG fetched = 0;
                    hr = enumerator->Next(1, item.GetAddressOf(), &fetched);
                    Check(hr == S_OK && fetched == 1 && item ? S_OK : E_UNEXPECTED, "Next child");
                    Verify(item.Get(), child);
                }
                ComPtr<IExplorerCommand> extra;
                ULONG fetched = 0;
                hr = enumerator->Next(1, extra.GetAddressOf(), &fetched);
                Check(hr == S_FALSE && fetched == 0 && !extra ? S_OK : E_UNEXPECTED, "enumeration end");
            }
        }
        std::puts("Packaged COM smoke passed: four class activations and exactly three flyout children.");
        std::wstring first = Environment(L"BYTEPLEAT_SMOKE_SELECTION_1");
        std::wstring second = Environment(L"BYTEPLEAT_SMOKE_SELECTION_2");
        DWORD captureSize = GetFullPathNameW(first.c_str(), 0, nullptr, nullptr);
        Check(captureSize && captureSize <= 32767 ? S_OK : E_INVALIDARG, "capture path size");
        std::wstring capture(captureSize, L'\0');
        DWORD captureChars = GetFullPathNameW(first.c_str(), captureSize, capture.data(), nullptr);
        Check(captureChars && captureChars < captureSize ? S_OK : E_INVALIDARG, "capture path resolution");
        capture.resize(captureChars);
        size_t separator = capture.find_last_of(L"\\/");
        Check(separator != std::wstring::npos ? S_OK : E_INVALIDARG, "capture path parent");
        capture.resize(separator + 1);
        capture += L".bytepleat-smoke-argv.bin";
        InvokeAndVerify(classes[1], L"--create", {first, second}, capture);
        InvokeAndVerify(classes[2], L"--extract", {first}, capture);
        InvokeAndVerify(classes[3], L"--open", {first}, capture);
        std::puts("Packaged Explorer invocation smoke passed without launching the desktop UI.");
    } catch (HRESULT) { result = 1; }
    CoUninitialize();
    return result;
}
