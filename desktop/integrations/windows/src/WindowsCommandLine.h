#pragma once

#include <string>
#include <cstddef>

namespace bytepleat::windows {
inline std::wstring QuoteArg(const std::wstring& arg) {
    std::wstring out = L"\"";
    std::size_t slashes = 0;
    for (wchar_t c : arg) {
        if (c == L'\\') { ++slashes; continue; }
        if (c == L'\"') { out.append(slashes * 2 + 1, L'\\'); out.push_back(c); slashes = 0; continue; }
        out.append(slashes, L'\\'); slashes = 0; out.push_back(c);
    }
    out.append(slashes * 2, L'\\');
    out.push_back(L'\"');
    return out;
}
}
