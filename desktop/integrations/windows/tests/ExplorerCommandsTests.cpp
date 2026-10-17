#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shobjidl.h>
#include <shellapi.h>
#include <shlobj.h>
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
    assert(enumerator->Skip(1) == S_FALSE); // requests one item beyond the end
    assert(enumerator->Skip(0) == S_OK);
    assert(enumerator->Next(1, &last, nullptr) == S_FALSE);
    assert(enumerator->Reset() == S_OK);
    assert(enumerator->Next(1, &last, nullptr) == S_OK && last);
    last->Release();
    last = nullptr;
    // Reset affects only this enumerator; the clone remains at the end.
    assert(clone->Next(1, &last, nullptr) == S_FALSE);
    assert(clone->Reset() == S_OK);
    assert(clone->Next(1, &last, nullptr) == S_OK && last);
    last->Release();
    // GetState on real files: a .zip is reported by Explorer as a compressed folder (SFGAO_FOLDER) but must
    // still enable Extract and Open; a directory, even one named like an archive, must not.
    {
        assert(SUCCEEDED(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED)));
        wchar_t tmp[MAX_PATH];
        const DWORD tmpLength = GetTempPathW(MAX_PATH, tmp);
        assert(tmpLength > 0 && tmpLength < MAX_PATH);
        const std::wstring dir = std::wstring(tmp) + L"bytepleat-getstate-" + std::to_wstring(GetCurrentProcessId());
        assert(CreateDirectoryW(dir.c_str(), nullptr));
        auto touch = [&](const std::wstring& path) {
            HANDLE h = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
            assert(h != INVALID_HANDLE_VALUE);
            DWORD written = 0;
            assert(WriteFile(h, "PK\x05\x06", 4, &written, nullptr));
            CloseHandle(h);
        };
        const std::wstring zip = dir + L"\\a.zip", sevenZ = dir + L"\\a.7z", tarGz = dir + L"\\a.tar.gz", txt = dir + L"\\a.txt", folderZip = dir + L"\\folder.zip";
        touch(zip); touch(sevenZ); touch(tarGz); touch(txt);
        assert(CreateDirectoryW(folderZip.c_str(), nullptr));
        IEnumExplorerCommand* stateEnum = nullptr;
        assert(SUCCEEDED(root->EnumSubCommands(&stateEnum)) && stateEnum);
        IExplorerCommand* all[3] = {};
        ULONG got = 0;
        assert(stateEnum->Next(3, all, &got) == S_OK && got == 3);  // Compress, Extract, Open
        auto stateOf = [&](IExplorerCommand* command, const std::wstring& path) {
            IShellItem* item = nullptr;
            assert(SUCCEEDED(SHCreateItemFromParsingName(path.c_str(), nullptr, IID_PPV_ARGS(&item))));
            IShellItemArray* array = nullptr;
            assert(SUCCEEDED(SHCreateShellItemArrayFromShellItem(item, IID_PPV_ARGS(&array))));
            EXPCMDSTATE state = ECS_ENABLED;
            assert(SUCCEEDED(command->GetState(array, FALSE, &state)));
            array->Release();
            item->Release();
            return state;
        };
        for (const auto& archive : {zip, sevenZ, tarGz})
            for (int i = 0; i < 3; ++i) assert(stateOf(all[i], archive) == ECS_ENABLED);
        assert(stateOf(all[0], txt) == ECS_ENABLED);
        assert(stateOf(all[1], txt) == ECS_DISABLED && stateOf(all[2], txt) == ECS_DISABLED);
        assert(stateOf(all[0], folderZip) == ECS_ENABLED);
        assert(stateOf(all[1], folderZip) == ECS_DISABLED && stateOf(all[2], folderZip) == ECS_DISABLED);
        for (int i = 0; i < 3; ++i) all[i]->Release();
        stateEnum->Release();
        DeleteFileW(zip.c_str()); DeleteFileW(sevenZ.c_str()); DeleteFileW(tarGz.c_str()); DeleteFileW(txt.c_str());
        RemoveDirectoryW(folderZip.c_str());
        RemoveDirectoryW(dir.c_str());
        CoUninitialize();
    }
    commands[0]->Release(); commands[1]->Release();
    clone->Release(); enumerator->Release(); root->Release(); factory->Release();
    assert(canUnload() == S_OK);
    assert(FreeLibrary(module));
    return 0;
}
