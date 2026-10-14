# Supported formats

“Supported” describes the bounded subset Arqlet implements. A format label alone does not guarantee that every file of that type is accepted.

| Format | Write | Read / validate | Important boundary |
|---|---|---|---|
| Zstandard byte stream | Yes | Yes | Standard frames; only this codec supports multiple threads. |
| gzip byte stream | Yes | Yes | Standard streams; concatenated frames supported. |
| LZ4 frame | Yes | Yes | Concatenated LZ4 frames are rejected. |
| Pco standalone numeric stream | Yes | Yes, with explicit type | Little-endian `i32`, `u32`, `i64`, `u64`, `f32`, or `f64`; no type inference. |
| tar + Zstandard/gzip/LZ4 | Yes | Yes | `pack` requires a directory; regular files/directories only. |
| ZIP | Yes | Yes, bounded | Classic ZIP Stored/Deflate only; no ZIP64, encryption, split volumes, or SFX. |
| 7z | Yes | Yes, bounded | Writer uses LZMA2. Reader supports bounded Copy, LZMA, LZMA2, and implemented BCJ/Delta filters. |
| RAR | No | No | Magic may be recognized in `info`; extraction is not integrated. |

## Byte-stream codecs

The byte commands preserve arbitrary input bytes. Compression defaults to Zstandard; decode detects the frame by its contents. Zstandard/gzip concatenated frames are supported. LZ4 concatenated frames are deliberately rejected. Native frame checksums detect accidental corruption, not tampering or authenticity.

## Folder archives

### tar with a byte codec

Arqlet writes ordinary tar streams carried by Zstandard, gzip, or LZ4. `pack` accepts a directory; `unpack` extracts regular files and directories. UTF-8, portable path names are required. Links, special and sparse files, unsafe paths, and path aliases are rejected. Extraction validates into staging before publication. Multi-file publication is best-effort and may expose partial files briefly if publication fails.

### ZIP

Arqlet reads and writes classic ZIP using Stored or Deflate. ZIP64, encrypted entries, AES, multi-disk archives, self-extracting prefixes, trailing payloads, unsupported compression methods, and legacy non-UTF-8 codepages are outside the supported subset or rejected. Entry count is capped at 65,534; compressed input is capped at 1 GiB. Names must be UTF-8-flagged for non-ASCII, or ASCII. `info` reports bounded metadata, not full payload integrity; use `test` or extraction to decode entries and check them.

### 7z

The writer creates unencrypted, single-volume 7z archives with LZMA2, solid by default, or independent blocks with `--no-solid`. The default dictionary is 16 MiB; it can be set from 4 KiB through 128 MiB. ZIP/7z encoding is single-threaded.

The reader accepts bounded unencrypted single-volume archives using implemented Copy, LZMA, LZMA2, BCJ-family, and Delta methods. It does not promise support for arbitrary 7z coder graphs, every codec, encryption, split volumes, links, or special metadata. Metadata is limited to 100,000 entries and 64 coder nodes. Default `--max-header` is 16 MiB and `--max-dictionary` is 128 MiB. Use `test` for full decoding; `info` does not validate all payload bytes.

## Typed Pco buffers

Pco mode reads little-endian fixed-width words with an explicitly supplied type: `i32`, `u32`, `i64`, `u64`, `f32`, or `f64`. Input must end on a complete word. It uses the existing standalone Pco stream, with no Arqlet envelope, CSV parsing, or automatic type inference. Decode and test require the matching type. Float bit patterns are retained by the typed conversion path.

## Preservation boundaries

Archive extraction restores regular-file contents and relative paths, and supports empty directories. It is not a full filesystem backup: permissions, ownership, links, extended attributes, and portable timestamps are not preserved. Archive names and attributes may have format-specific portability limits. See [security and limits](security-limits.md).
