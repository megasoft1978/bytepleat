#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shobjidl.h>
#include <shellapi.h>
#include <shlwapi.h>
#include <atomic>
#include <algorithm>
#include <cwchar>
#include <new>
#include <string>
#include <vector>
#include "WindowsCommandLine.h"

// Package manifest CLSIDs. Keep these in sync with package/AppxManifest.xml.
static const CLSID CLSID_BytepleatFlyout = {0x6c987d21,0x07a4,0x4d7b,{0x99,0x2c,0x2e,0x2d,0x6f,0x5d,0x10,0x01}};
static const CLSID CLSID_BytepleatCompress = {0x6c987d22,0x07a4,0x4d7b,{0x99,0x2c,0x2e,0x2d,0x6f,0x5d,0x10,0x02}};
static const CLSID CLSID_BytepleatExtract = {0x6c987d23,0x07a4,0x4d7b,{0x99,0x2c,0x2e,0x2d,0x6f,0x5d,0x10,0x03}};
static const CLSID CLSID_BytepleatOpen = {0x6c987d24,0x07a4,0x4d7b,{0x99,0x2c,0x2e,0x2d,0x6f,0x5d,0x10,0x04}};
static std::atomic<long> g_objects{0};
static std::atomic<long> g_locks{0};

enum class Action { Flyout, Compress, Extract, Open };

// The app package installs this executable alias. Resolve only beneath the
// current user's WindowsApps alias directory; never search PATH or use a shell.
static HRESULT ResolveAppAlias(std::wstring& path) {
    DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", nullptr, 0);
    if (!n || n > 32767) return HRESULT_FROM_WIN32(ERROR_ENVVAR_NOT_FOUND);
    std::wstring base(n, L'\0');
    DWORD got = GetEnvironmentVariableW(L"LOCALAPPDATA", base.data(), n);
    if (!got || got >= n) return HRESULT_FROM_WIN32(ERROR_ENVVAR_NOT_FOUND);
    base.resize(got);
    path = base + L"\\Microsoft\\WindowsApps\\bytepleat-desktop.exe";
    DWORD attrs = GetFileAttributesW(path.c_str());
    return attrs != INVALID_FILE_ATTRIBUTES && !(attrs & FILE_ATTRIBUTE_DIRECTORY)
        ? S_OK : HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND);
}

static HRESULT Launch(Action action, IShellItemArray* items) {
    if (!items) return E_INVALIDARG;
    DWORD count = 0;
    HRESULT hr = items->GetCount(&count);
    if (FAILED(hr) || count == 0 || count > 4096) return FAILED(hr) ? hr : E_INVALIDARG;
    SFGAOF attributes = 0;
    hr = items->GetAttributes(SIATTRIBFLAGS_AND, SFGAO_FILESYSTEM, &attributes);
    if (FAILED(hr) || !(attributes & SFGAO_FILESYSTEM)) return FAILED(hr) ? hr : E_INVALIDARG;
    std::vector<std::wstring> paths;
    paths.reserve(count);
    for (DWORD i = 0; i < count; ++i) {
        IShellItem* item = nullptr;
        hr = items->GetItemAt(i, &item);
        if (FAILED(hr)) return hr;
        PWSTR raw = nullptr;
        hr = item->GetDisplayName(SIGDN_FILESYSPATH, &raw);
        item->Release();
        if (FAILED(hr) || !raw) { CoTaskMemFree(raw); return FAILED(hr) ? hr : E_UNEXPECTED; }
        try { paths.emplace_back(raw); } catch (...) { CoTaskMemFree(raw); return E_OUTOFMEMORY; }
        CoTaskMemFree(raw);
    }
    const wchar_t* verb = action == Action::Compress ? L"--create" : action == Action::Extract ? L"--extract" : L"--open";
    std::wstring params = verb;
    params += L" --";
    for (const auto& p : paths) { params.push_back(L' '); params += bytepleat::windows::QuoteArg(p); }
    std::wstring exe;
    hr = ResolveAppAlias(exe);
    if (FAILED(hr)) return hr;
    // CreateProcess accepts at most 32767 UTF-16 code units including the executable.
    if (exe.size() + params.size() + 4 >= 32767) return HRESULT_FROM_WIN32(ERROR_FILENAME_EXCED_RANGE);
    SHELLEXECUTEINFOW sei{};
    sei.cbSize = sizeof(sei);
    sei.fMask = SEE_MASK_NOASYNC | SEE_MASK_FLAG_NO_UI;
    sei.lpFile = exe.c_str();
    sei.lpParameters = params.c_str();
    sei.nShow = SW_SHOWNORMAL;
    if (ShellExecuteExW(&sei)) return S_OK;
    DWORD error = GetLastError();
    return error ? HRESULT_FROM_WIN32(error) : E_FAIL;
}

class Command final : public IExplorerCommand {
public:
    explicit Command(Action action) : action_(action), refs_(1) { ++g_objects; }
    IFACEMETHODIMP QueryInterface(REFIID riid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (riid == IID_IUnknown || riid == IID_IExplorerCommand) { *out = static_cast<IExplorerCommand*>(this); AddRef(); return S_OK; }
        return E_NOINTERFACE;
    }
    IFACEMETHODIMP_(ULONG) AddRef() override { return static_cast<ULONG>(InterlockedIncrement(&refs_)); }
    IFACEMETHODIMP_(ULONG) Release() override {
        ULONG n = static_cast<ULONG>(InterlockedDecrement(&refs_));
        if (!n) delete this;
        return n;
    }
    IFACEMETHODIMP GetTitle(IShellItemArray*, LPWSTR* title) override {
        if (!title) return E_POINTER;
        const wchar_t* t = action_ == Action::Flyout ? L"Bytepleat" : action_ == Action::Compress ? L"Compress with Bytepleat" : action_ == Action::Extract ? L"Extract with Bytepleat" : L"Open in Bytepleat";
        return SHStrDupW(t, title);
    }
    IFACEMETHODIMP GetIcon(IShellItemArray*, LPWSTR* icon) override { if (!icon) return E_POINTER; *icon = nullptr; return E_NOTIMPL; }
    IFACEMETHODIMP GetToolTip(IShellItemArray*, LPWSTR* tip) override { if (!tip) return E_POINTER; *tip = nullptr; return E_NOTIMPL; }
    IFACEMETHODIMP GetCanonicalName(GUID* id) override {
        if (!id) return E_POINTER;
        *id = action_ == Action::Flyout ? CLSID_BytepleatFlyout : action_ == Action::Compress ? CLSID_BytepleatCompress : action_ == Action::Extract ? CLSID_BytepleatExtract : CLSID_BytepleatOpen;
        return S_OK;
    }
    IFACEMETHODIMP GetState(IShellItemArray* items, BOOL, EXPCMDSTATE* state) override {
        if (!state) return E_POINTER;
        *state = ECS_DISABLED;
        if (action_ == Action::Flyout) { *state = ECS_ENABLED; return S_OK; }
        if (!items) return S_OK;
        DWORD count = 0;
        HRESULT hr = items->GetCount(&count);
        if (FAILED(hr)) return hr;
        if (!count || count > 4096 || ((action_ == Action::Extract || action_ == Action::Open) && count != 1)) return S_OK;
        SFGAOF attrs = 0;
        hr = items->GetAttributes(SIATTRIBFLAGS_AND, SFGAO_FILESYSTEM, &attrs);
        if (FAILED(hr) || !(attrs & SFGAO_FILESYSTEM)) return FAILED(hr) ? hr : S_OK;
        if (action_ == Action::Compress) { *state = ECS_ENABLED; return S_OK; }
        IShellItem* item = nullptr;
        hr = items->GetItemAt(0, &item);
        if (FAILED(hr)) return hr;
        SFGAOF itemAttrs = 0;
        hr = item->GetAttributes(SFGAO_FILESYSTEM, &itemAttrs);
        if (FAILED(hr) || !(itemAttrs & SFGAO_FILESYSTEM)) { item->Release(); return FAILED(hr) ? hr : S_OK; }
        PWSTR raw = nullptr;
        hr = item->GetDisplayName(SIGDN_FILESYSPATH, &raw);
        item->Release();
        if (FAILED(hr) || !raw) { CoTaskMemFree(raw); return S_OK; }
        // Explorer reports a .zip as SFGAO_FOLDER (a compressed folder), so the shell attributes cannot tell
        // an archive from a directory. Ask the file system instead.
        const DWORD fileAttrs = GetFileAttributesW(raw);
        if (fileAttrs == INVALID_FILE_ATTRIBUTES || (fileAttrs & FILE_ATTRIBUTE_DIRECTORY)) { CoTaskMemFree(raw); return S_OK; }
        const wchar_t* ext = PathFindExtensionW(raw);
        bool supported = ext && (_wcsicmp(ext, L".zip") == 0 || _wcsicmp(ext, L".7z") == 0);
        size_t pathLength = wcslen(raw);
        if (!supported && pathLength >= 7) supported = _wcsicmp(raw + pathLength - 7, L".tar.gz") == 0;
        if (!supported && pathLength >= 8) supported = _wcsicmp(raw + pathLength - 8, L".tar.zst") == 0 || _wcsicmp(raw + pathLength - 8, L".tar.lz4") == 0;
        CoTaskMemFree(raw);
        if (supported) *state = ECS_ENABLED;
        return S_OK;
    }
    IFACEMETHODIMP Invoke(IShellItemArray* items, IBindCtx*) override { if (action_ == Action::Flyout) return E_NOTIMPL; try { return Launch(action_, items); } catch (...) { return E_OUTOFMEMORY; } }
    IFACEMETHODIMP GetFlags(EXPCMDFLAGS* flags) override { if (!flags) return E_POINTER; *flags = action_ == Action::Flyout ? ECF_HASSUBCOMMANDS : ECF_DEFAULT; return S_OK; }
    IFACEMETHODIMP EnumSubCommands(IEnumExplorerCommand** out) override;
private:
    ~Command() { --g_objects; }
    Action action_;
    volatile LONG refs_;
};

class CommandEnum final : public IEnumExplorerCommand {
public:
    CommandEnum() : refs_(1), index_(0) { ++g_objects; }
    IFACEMETHODIMP QueryInterface(REFIID riid, void** out) override { if (!out) return E_POINTER; *out=nullptr; if (riid==IID_IUnknown || riid==IID_IEnumExplorerCommand) { *out=this; AddRef(); return S_OK; } return E_NOINTERFACE; }
    IFACEMETHODIMP_(ULONG) AddRef() override { return static_cast<ULONG>(InterlockedIncrement(&refs_)); }
    IFACEMETHODIMP_(ULONG) Release() override { ULONG n=static_cast<ULONG>(InterlockedDecrement(&refs_)); if (!n) delete this; return n; }
    IFACEMETHODIMP Next(ULONG c, IExplorerCommand** out, ULONG* fetched) override {
        if (!out || (c != 1 && !fetched)) return E_POINTER;
        for (ULONG i = 0; i < c; ++i) out[i] = nullptr;
        ULONG n=0;
        while (n<c && index_<3) { Action a = index_==0 ? Action::Compress : index_==1 ? Action::Extract : Action::Open; out[n]=new (std::nothrow) Command(a); if (!out[n]) { if (fetched) *fetched=n; return E_OUTOFMEMORY; } ++index_; ++n; }
        if (fetched) *fetched=n;
        return n==c ? S_OK : S_FALSE;
    }
    IFACEMETHODIMP Skip(ULONG c) override { ULONG remaining = static_cast<ULONG>(3 - index_); index_ += static_cast<LONG>(std::min(c, remaining)); return c <= remaining ? S_OK : S_FALSE; }
    IFACEMETHODIMP Reset() override { index_=0; return S_OK; }
    IFACEMETHODIMP Clone(IEnumExplorerCommand** out) override { if (!out) return E_POINTER; *out=nullptr; auto* e=new (std::nothrow) CommandEnum; if (!e) return E_OUTOFMEMORY; e->index_=index_; *out=e; return S_OK; }
private:
    ~CommandEnum() { --g_objects; }
    volatile LONG refs_;
    LONG index_;
};
IFACEMETHODIMP Command::EnumSubCommands(IEnumExplorerCommand** out) { if (!out) return E_POINTER; *out=nullptr; if (action_!=Action::Flyout) return E_NOTIMPL; *out=new (std::nothrow) CommandEnum; return *out ? S_OK : E_OUTOFMEMORY; }

class Factory final : public IClassFactory {
public:
    explicit Factory(Action action): action_(action), refs_(1) { ++g_objects; }
    IFACEMETHODIMP QueryInterface(REFIID riid,void** out) override { if(!out)return E_POINTER; *out=nullptr; if(riid==IID_IUnknown||riid==IID_IClassFactory){*out=this;AddRef();return S_OK;} return E_NOINTERFACE; }
    IFACEMETHODIMP_(ULONG) AddRef() override { return static_cast<ULONG>(InterlockedIncrement(&refs_)); }
    IFACEMETHODIMP_(ULONG) Release() override { ULONG n=static_cast<ULONG>(InterlockedDecrement(&refs_));if(!n)delete this;return n; }
    IFACEMETHODIMP CreateInstance(IUnknown* outer,REFIID riid,void** out) override { if(!out)return E_POINTER; *out=nullptr; if(outer)return CLASS_E_NOAGGREGATION; auto* c=new(std::nothrow) Command(action_); if(!c)return E_OUTOFMEMORY; HRESULT hr=c->QueryInterface(riid,out); c->Release(); return hr; }
    IFACEMETHODIMP LockServer(BOOL lock) override {
        if (lock) { ++g_locks; return S_OK; }
        long current = g_locks.load();
        while (current > 0) { if (g_locks.compare_exchange_weak(current, current - 1)) return S_OK; }
        return E_UNEXPECTED;
    }
private: ~Factory(){--g_objects;} Action action_; volatile LONG refs_;
};

BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID) { if(reason==DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance); return TRUE; }
STDAPI DllGetClassObject(REFCLSID clsid,REFIID riid,void** out) {
    if (!out) return E_POINTER;
    *out = nullptr;
    Action a;
    if(IsEqualCLSID(clsid,CLSID_BytepleatFlyout)) a=Action::Flyout;
    else if(IsEqualCLSID(clsid,CLSID_BytepleatCompress)) a=Action::Compress;
    else if(IsEqualCLSID(clsid,CLSID_BytepleatExtract)) a=Action::Extract;
    else if(IsEqualCLSID(clsid,CLSID_BytepleatOpen)) a=Action::Open;
    else return CLASS_E_CLASSNOTAVAILABLE;
    auto* f=new(std::nothrow) Factory(a); if(!f)return E_OUTOFMEMORY; HRESULT hr=f->QueryInterface(riid,out); f->Release(); return hr;
}
STDAPI DllCanUnloadNow() { return g_objects.load()==0 && g_locks.load()==0 ? S_OK : S_FALSE; }
