# Bytepleat archive benchmarks

This report compares Bytepleat with command-line archive tools on one Apple M5 Max Mac running macOS 27.0.1 (ARM64, 18 CPU cores, 64 GiB RAM). It reports six selected workloads, not a universal ranking. It does not establish performance on other hardware, Windows, Linux, Finder, or GUI applications.

## Selected result: LZ4 v1.10.0 source tree

On a 1,674,742-byte public LZ4 source tree, Bytepleat ZIP at Deflate level 6 produced a 480,556-byte archive in 0.048 s, with a 0.029 s median decode. 7zz ZIP at level 6 produced 478,266 bytes in 0.105 s, with a 0.033 s decode. In this workload Bytepleat ZIP was close in size and faster in this run. The external `tar | zstd` pipeline was faster to create (0.022 s) and nearly the same size (354,817 bytes) as Bytepleat `tar.zst` (352,317 bytes; 0.028 s). Those timings include process startup and filesystem IO.

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

Each of the six cases was run once as a warmup and five times as measured for each method: 96 warmup pairs and 480 measured pairs. The analysis independently checked 48 warmup archives with cross-decoders. All 96 case/method groups have five verified repeats; the final run has zero failures. The CSV contains all 96 groups, medians, timing ranges, and available memory measurements.

Encode timing includes process startup and archive creation IO. Decode timing includes startup and extraction IO. Archive files were fsynced after the encode timer. SHA-256, exact relative paths, byte counts, and directory checks ran outside timers. Archive sizes include wrappers and format metadata, checksums, and internal dictionaries. For pipelines, reported RSS is the sum of each child's wait4 peak and is an upper bound, not a simultaneous peak. Compression thread settings are controlled as listed in the provenance; native extraction thread defaults were not universally overridden.

Methods included Bytepleat ZIP Deflate 6/9 and 7z LZMA2 5; 7zz ZIP Deflate 6/9 and 7z LZMA2 5; Bytepleat tar with Zstandard 3, gzip 6, or default LZ4; corresponding external tar pipelines; macOS `ditto -c -k --norsrc`; Apple-modified Info-ZIP `zip -6`; and RAR5 m3/m5. A native-tar Zstandard method was skipped because the installed tar did not advertise that support. See [provenance](benchmarks/provenance.json) for versions, executable and harness hashes, input checksums, public upstream links, license notes, and settings.

The recorded lab invocation was:

```sh
python3 scripts/bench_desktop.py \
  --bytepleat results/desktop-research/released-bytepleat/bytepleat \
  --7zz product/target/tools/7zip/7zz \
  --rar results/desktop-research/rar-evaluation/local-tool/rar \
  --output results/desktop-research/run-002.json
```

This command is provided to document how the verified lab run was produced; its paths are relative to the research lab checkout. The original full reproducibility harness and inputs are retained in the lab and are not linked as a public download. The published evidence is the sanitized [96-group CSV](benchmarks/summary.csv) and [bounded provenance record](benchmarks/provenance.json). No raw logs, binaries, or corpora are included here.
