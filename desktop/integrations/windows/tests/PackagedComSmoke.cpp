#if !defined(_M_ARM64) || defined(_M_ARM64EC)
#error Packaged COM smoke requires a native ARM64 build.
#endif
#include <windows.h>
#include <shobjidl.h>
#include <wrl/client.h>
#include <cstdio>
#include <cwchar>

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
        // Use Windows package registration and the COM surrogate. No LoadLibrary,
        // registration fallback, shell UI, selection, or Invoke call is allowed.
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
        std::puts("Packaged COM smoke passed: four class activations and exactly three flyout children; no invocation.");
    } catch (HRESULT) { result = 1; }
    CoUninitialize();
    return result;
}
