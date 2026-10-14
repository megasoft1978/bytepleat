#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shobjidl.h>
#include <shellapi.h>
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <string>
#include <vector>
#include "../src/WindowsCommandLine.h"

static const CLSID CLSID_BytepleatFlyout = {0x6c987d21,0x07a4,0x4d7b,{0x99,0x2c,0x2e,0x2d,0x6f,0x5d,0x10,0x01}};

int wmain(int argc, wchar_t** argv) {
    assert(argc == 2);
    const std::vector<std::wstring> paths = {L"C:\\Folder With Spaces\\file.txt", L"C:\\ユニコード\\résumé.txt", L"C:\\a\"b\\file", L"C:\\ends-with-slash\\"};
    std::wstring line = L"app.exe --create --";
    for (const auto& path : paths) { line += L" "; line += bytepleat::windows::QuoteArg(path); }
    int parsedCount = 0;
    LPWSTR* parsed = CommandLineToArgvW(line.c_str(), &parsedCount);
    assert(parsed && parsedCount == static_cast<int>(paths.size()) + 3);
    assert(std::wstring(parsed[1]) == L"--create" && std::wstring(parsed[2]) == L"--");
    for (size_t i = 0; i < paths.size(); ++i) assert(paths[i] == parsed[i + 3]);
    LocalFree(parsed);

    HMODULE module = LoadLibraryW(argv[1]);
    assert(module);
    using GetClassObject = HRESULT (STDAPICALLTYPE*)(REFCLSID, REFIID, void**);
    auto getClassObject = reinterpret_cast<GetClassObject>(GetProcAddress(module, "DllGetClassObject"));
    using CanUnload = HRESULT (STDAPICALLTYPE*)();
    auto canUnload = reinterpret_cast<CanUnload>(GetProcAddress(module, "DllCanUnloadNow"));
    assert(getClassObject);
    assert(canUnload);
    IClassFactory* factory = nullptr;
    assert(SUCCEEDED(getClassObject(CLSID_BytepleatFlyout, IID_IClassFactory, reinterpret_cast<void**>(&factory))));
    assert(factory);
    assert(factory->LockServer(TRUE) == S_OK);
    assert(factory->LockServer(FALSE) == S_OK);
    assert(canUnload() == S_FALSE);
    IExplorerCommand* root = nullptr;
    assert(SUCCEEDED(factory->CreateInstance(nullptr, IID_IExplorerCommand, reinterpret_cast<void**>(&root))));
    IEnumExplorerCommand* enumerator = nullptr;
    assert(SUCCEEDED(root->EnumSubCommands(&enumerator)) && enumerator);
    IExplorerCommand* commands[2] = {};
    ULONG fetched = 0;
    assert(enumerator->Next(2, commands, &fetched) == S_OK && fetched == 2);
    IEnumExplorerCommand* clone = nullptr;
    assert(SUCCEEDED(enumerator->Clone(&clone)) && clone);
    IExplorerCommand* last = nullptr;
    assert(clone->Next(1, &last, nullptr) == S_OK && last);
    last->Release();
    last = nullptr;
    assert(clone->Next(1, &last, nullptr) == S_FALSE);
    assert(enumerator->Skip(1) == S_OK);
    assert(enumerator->Skip(1) == S_OK); // exactly reaches the end
    assert(enumerator->Skip(0) == S_OK);
    assert(enumerator->Next(1, &last, nullptr) == S_FALSE);
    commands[0]->Release(); commands[1]->Release();
    clone->Release(); enumerator->Release(); root->Release(); factory->Release();
    assert(canUnload() == S_OK);
    assert(FreeLibrary(module));
    return 0;
}
