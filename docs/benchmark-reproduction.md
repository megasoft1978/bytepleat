# Public macOS benchmark reproduction

This reproduces the public LZ4 v1.10.0 source-tree case. Its small pin manifest is committed beside the scripts. Preparation writes only to a new directory outside the repository. It downloads the upstream GitHub `v1.10.0` tag archive, rejects unsafe paths, extracts only regular files, renames the source root to `lz4-v1.10.0`, and rebuilds the byte-pinned 1,843,200-byte deterministic USTAR: component-wise sorted relative paths, uid/gid 0, empty uname/gname, mtime 0, and normalized file mode `0644` (matching the original corpus preparation). It requires SHA-256 `fd33f2ea8f797d4d02452e80f1819a472f584471bc7b1fa09c0a17099b5f43f3`, then records and verifies the extracted file path/size/SHA-256 manifest. The downloaded GitHub tarball bytes are not pinned; the derived benchmark archive and every extracted regular file are checked.

```sh
python3 scripts/benchmarks/prepare_public.py /tmp/bytepleat-public-corpus
```

Run the benchmark on macOS with the Bytepleat and 7-Zip executables available. Give `--output` a new path outside the repository. Final mode uses five measured repeats plus one warmup, shuffled method order, per-process timeout and peak-RSS measurement, file-sync cost outside encode timing, pipeline creation/decompression costs inside timing, and exact path/size/SHA-256/directory verification. The JSON result records host and tool versions/hashes, commands, randomized order, failures, and summaries.

```sh
python3 scripts/benchmarks/bench_macos.py \
  --bytepleat /path/to/bytepleat --7zz /path/to/7zz \
  --prepared /tmp/bytepleat-public-corpus \
  --output /tmp/bytepleat-macos-results.json
```

`--allow-smoke --repeats 1` runs only generated fixtures, needs no prepared corpus, and is not a public-corpus result. Both modes require macOS, the Bytepleat executable, and 7-Zip (`7zz`). The other rows use these host tools when available; unavailable rows are explicitly recorded as skipped:

| Method rows | Additional requirement |
| --- | --- |
| Bytepleat ZIP/7z and tar+zstd/gzip/lz4 | Bytepleat executable; external `zstd`, `gzip`, and `lz4` for the matching pipeline rows |
| 7zz ZIP/7z | `7zz` executable |
| `ditto-zip` | macOS `/usr/bin/ditto` |
| `infozip-6` | `/usr/bin/zip` and `/usr/bin/unzip` |
| `native-tar-zstd-3` | `/usr/bin/tar` built with `--zstd` support |
| `rar5-m3` and `rar5-m5` | Optional caller-supplied `rar` executable plus `--rar-license-note`; otherwise both rows are recorded as omitted |

RAR is never downloaded or bundled. Supply `--rar-license-note` with an accurate description of your local permission or evaluation terms; the result records that note, the executable path, version output, and SHA-256. The harness does not determine whether those terms authorize use. Tool versions and hashes for the macOS rows are captured in each JSON result. This reproducer does not monitor other project workers; run only when the host is otherwise idle if you need comparable performance measurements.

The prepared command intentionally materializes the LZ4 workload only. The companion harness runs that public source tree and two generated 8 MiB controls; the earlier desktop suite's mixed-public, zstd-tar, and JPEG cases require additional inputs and are outside this standalone reproduction. A five-repeat run completed on 2026-10-15: see the [measured CSV](benchmarks/macos-reproduction-2026-10-15.csv), [sanitized provenance](benchmarks/macos-reproduction-2026-10-15.json), and [scoped analysis](benchmarks.md#reproduced-macos-run-2026-10-15). It is one macOS ARM64 result and does not establish Windows/Linux performance or a general ranking. Offline fixture tests use generated archives only and never fetch corpora or invoke RAR:

```sh
python3 -m unittest discover -s scripts/benchmarks -p 'test_prepare_public.py' -v
```
