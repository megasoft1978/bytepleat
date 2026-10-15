# Bytepleat archive benchmarks

This report contains an earlier six-workload suite and a separate standalone reproduction, both measured on one Apple M5 Max Mac running macOS 27.0.1 (ARM64, 18 CPU cores, 64 GiB RAM). These selected results are not a universal ranking and do not establish performance on other hardware, Windows, Linux, Finder, or GUI applications.

## Reproduced macOS run: 2026-10-15

The checked-in public reproduction harness completed on this host with 42 case/method groups, five measured repeats per group, 210 verified measured records, and zero failures. It covered the LZ4 v1.10.0 source tree plus generated 8 MiB text and pseudorandom controls. The full per-method medians and ranges are in the [42-group CSV](benchmarks/macos-reproduction-2026-10-15.csv); tool hashes, corpus pins, compiler, protocol, and skipped rows are in the [run provenance](benchmarks/macos-reproduction-2026-10-15.json).

| Workload and setting | Tool | Archive bytes | Encode median (s) | Decode median (s) |
| --- | --- | ---: | ---: | ---: |
| LZ4 source tree, ZIP Deflate 6 | Bytepleat | 480,556 | 0.03356 | 0.02300 |
| LZ4 source tree, ZIP Deflate 6 | 7-Zip 26.04 | 478,266 | 0.09671 | 0.02586 |
| LZ4 source tree, 7z LZMA2 5 | Bytepleat | 269,846 | 0.24432 | 0.02965 |
| LZ4 source tree, 7z LZMA2 5 | 7-Zip 26.04 | 270,414 | 0.22349 | 0.02707 |
| LZ4 source tree, tar + Zstandard 3 | Bytepleat | 352,317 | 0.02137 | 0.02301 |
| LZ4 source tree, tar + Zstandard 3 | system tar + Zstandard 1.5.7 | 354,834 | 0.01741 | 0.02467 |
| Generated repeated text, ZIP Deflate 6 | Bytepleat | 49,350 | 0.01676 | 0.00577 |
| Generated repeated text, ZIP Deflate 6 | 7-Zip 26.04 | 26,450 | 0.09498 | 0.00917 |

On the LZ4 source tree, Bytepleat ZIP 6 had a 2.9× lower encode median than 7-Zip ZIP 6, with an archive 0.48% larger. Bytepleat 7z was 0.21% smaller than 7-Zip 7z, but its encode and decode medians were about 9% slower. On the generated text control, Bytepleat ZIP 6 was substantially larger than 7-Zip ZIP 6. These results show workload-specific tradeoffs, not a general speed or compression-ratio advantage. The run's quiescence check was not enabled, so host activity may affect timings; the earlier published LZ4 ZIP 6 run also reported a different median on the same nominal host. Treat sub-second timing differences as exploratory.

The local macOS `tar` lacked Zstandard support, so native-tar Zstandard was skipped. This 42-group run did not use RAR; the separate RAR trial run is reported below. Neither run covers Windows or Linux built-in performance or GUI behavior.

### RAR trial reproduction · 2026-10-15

A second run used the checked-in harness with RARLAB's [official RAR 7.23 macOS ARM64 command-line trial](https://www.rarlab.com/download.htm), locally within its [40-day evaluation terms](https://www.rarlab.com/license.htm). The trial binary was not committed or redistributed. Across the LZ4 source tree and two generated 8 MiB controls, the run completed 48 case/method groups and five measured repeats per group; all 240 measured archives restored exact paths, byte counts, hashes, and directory paths. The [RAR comparison CSV](benchmarks/macos-rar-reproduction-2026-10-15.csv) includes all methods from this run, and the [sanitized provenance](benchmarks/macos-rar-reproduction-2026-10-15.json) records tool hashes, run settings, corpus pins, and the RAR trial note.

| LZ4 source tree, measured setting | Tool | Archive bytes | Encode median (s) | Decode median (s) |
| --- | --- | ---: | ---: | ---: |
| ZIP Deflate 6 | Bytepleat | 480,556 | 0.03515 | 0.02165 |
| ZIP Deflate 6 | 7-Zip 26.04 | 478,266 | 0.09703 | 0.02665 |
| 7z LZMA2 5, solid, 16 MiB dictionary | Bytepleat | 269,846 | 0.25404 | 0.02794 |
| 7z LZMA2 5, solid, 16 MiB dictionary | 7-Zip 26.04 | 270,414 | 0.20503 | 0.02466 |
| RAR5 m3, solid, 16 MiB dictionary | RAR 7.23 trial | 298,367 | 0.05941 | 0.02976 |
| RAR5 m5, solid, 16 MiB dictionary | RAR 7.23 trial | 295,577 | 0.08873 | 0.02867 |

On this corpus, Bytepleat 7z made a smaller archive than either RAR setting, while RAR encoded faster than Bytepleat 7z. On the generated repeated-text control, RAR5 m5 produced 519 bytes versus Bytepleat 7z's 1,442 bytes; on the pseudorandom control, RAR5 m5 produced 8,404,415 bytes versus Bytepleat 7z's 8,389,101 bytes. These workload-specific results do not establish an overall winner. RAR itself restored every archive exactly, while 7-Zip 26.04 reported `Unsupported Method` on all six RAR warmup attempts. The harness records that explicit response as an interoperability limitation; other decoder errors still fail the run. Host quiescence was not checked, so timing differences remain exploratory.

## Earlier full-suite result: LZ4 v1.10.0 source tree

This excerpt preserves the earlier six-workload suite's LZ4 result. Its archived raw run and tool binaries are not in this repository; the fresh standalone reproduction above used a separately built Bytepleat executable and a different 7-Zip binary hash, and should be read as a new run rather than a like-for-like rerun of the original binaries. The earlier run reported Bytepleat ZIP Deflate 6 at 0.0484 s median (480,556 bytes), versus 7zz ZIP level 6 at 0.1052 s (478,266 bytes). The external `tar | zstd` pipeline was faster to create (0.0216 s) and nearly the same size (354,817 bytes) as Bytepleat `tar.zst` (352,317 bytes; 0.0280 s). These timings include process startup and filesystem IO.

| Method and measured setting | Archive bytes | Encode seconds | Decode seconds |
|---|---:|---:|---:|
| Bytepleat ZIP, Deflate 6 | 480,556 | 0.0484 | 0.0289 |
| 7zz ZIP, Deflate 6, one thread | 478,266 | 0.1052 | 0.0329 |
| Info-ZIP ZIP, `zip -6` | 491,557 | 0.0351 | 0.0371 |
| Bytepleat 7z, LZMA2 5, solid, 16 MiB dictionary | 269,846 | 0.2931 | 0.0359 |
| 7zz 7z, LZMA2 5, solid, 16 MiB dictionary | 270,404 | 0.2350 | 0.0337 |
| Bytepleat `tar.zst`, Zstandard 3 | 352,317 | 0.0280 | 0.0309 |
| `tar` stream + `zstd` 3, one thread | 354,817 | 0.0216 | 0.0323 |
| RAR5 CLI, m3 | 298,367 | 0.0712 | 0.0389 |

The `ditto` command was included in the 96-group export; consult the CSV for each row. ZIP and 7z labels refer to the measured method settings, not every feature of those formats. Bytepleat implements bounded subsets: classic ZIP Stored/Deflate (no ZIP64, encryption, split volumes, or SFX) and unencrypted single-volume 7z with LZMA2 writing. See [supported formats](formats.md) for boundaries.

## What the other workloads show

On a 576,186-byte mixed public sample (Astropy FITS files, Canterbury text, and selected LZ4 source files), Bytepleat ZIP was 145,756 bytes and 0.0208 s; Info-ZIP was 144,649 bytes and 0.0146 s; 7zz ZIP was 140,099 bytes and 0.0455 s. Bytepleat and 7zz 7z archive sizes were effectively level with each other (117,461 and 117,526 bytes); Bytepleat took 0.1045 s and 7zz 0.0693 s. This sample therefore shows no size advantage for Bytepleat 7z over 7zz 7z.

On the 8,867,840-byte zstd v1.5.7 source-tree control, Bytepleat `tar.zst` was 2,273,158 bytes (0.0377 s), while the external `tar | zstd` pipeline was 2,265,674 bytes (0.0271 s). The pipeline was both faster and slightly smaller here. The same control produced 7z archives around 1.86 MB, but the measured 7z encodes took 1.30–1.45 s. The already-compressed JPEG control and generated 8 MiB fixtures appear separately in the CSV. The generated repeated-text case compresses extremely well and should not be read as a public-corpus result.

RAR rows use RARLAB's macOS ARM64 7.23 evaluation command-line tool. They are not WinRAR GUI measurements and the tool is not included with Bytepleat. RAR writing and extraction are outside Bytepleat's supported formats.

## Measurement and reproduction

Each of the six cases was run once as a warmup and five times as measured for each method: 96 warmup pairs and 480 measured pairs. All 96 case/method groups have five measured repeats; the CSV contains their medians, timing ranges, and available memory measurements. The analysis independently checked 48 warmup archives with cross-decoders. The final run reported zero failures.

Encode timing includes process startup and archive creation IO. Decode timing includes startup and extraction IO. Archive files were fsynced after the encode timer. SHA-256, exact relative paths, byte counts, and directory checks ran outside timers. Archive sizes include wrappers and format metadata, checksums, and internal dictionaries. For pipelines, reported RSS is the sum of each child's wait4 peak and is an upper bound, not a simultaneous peak. Compression thread settings are controlled as listed in the provenance; native extraction thread defaults were not universally overridden. The 7zz encode comparison uses one thread, while macOS utilities such as `ditto` and Info-ZIP use their own defaults. These results compare specific tools and settings, not isolated codec algorithms or a uniform cross-platform “built-in” baseline.

Methods included Bytepleat ZIP Deflate 6/9 and 7z LZMA2 5; 7zz ZIP Deflate 6/9 and 7z LZMA2 5; Bytepleat tar with Zstandard 3, gzip 6, or default LZ4; corresponding external tar pipelines; macOS `ditto -c -k --norsrc`; Apple-modified Info-ZIP `zip -6`; and RAR5 m3/m5. A native-tar Zstandard method was skipped because the installed tar did not advertise that support. See [provenance](benchmarks/provenance.json) for versions, executable and harness hashes, input checksums, public upstream links, license notes, and settings.

The recorded lab invocation was:

```sh
python3 scripts/bench_desktop.py \
  --bytepleat results/desktop-research/released-bytepleat/bytepleat \
  --7zz product/target/tools/7zip/7zz \
  --rar results/desktop-research/rar-evaluation/local-tool/rar \
  --output results/desktop-research/run-002.json
```

This command documents how the verified lab run was produced; its paths are relative to the research lab checkout. The published evidence is the sanitized [96-group CSV](benchmarks/summary.csv) and [bounded provenance record](benchmarks/provenance.json). A smaller [public macOS reproduction](benchmark-reproduction.md) now reruns the pinned LZ4 v1.10.0 source tree plus generated text and random controls. It does not recreate the complete six-case run: the mixed-public, zstd-tar, and JPEG inputs and original full harness remain in the lab. The full CSV result therefore cannot be independently rerun using only this repository; raw logs, binaries, and the complete prepared corpus are not included here.
