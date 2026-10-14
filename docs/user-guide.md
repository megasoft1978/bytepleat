# User guide

## Install and invoke

See the [README](../README.md) for source builds, release packages, and installation. Run `bytepleat --help` or `bytepleat <command> --help` for the options available in your installed build.

## Byte streams

`compress` accepts a file or `-` for stdin. It defaults to Zstandard and derives the named output extension from the selected format when `-o` is omitted. `decompress` detects the input format from its contents; set `-o` to choose a destination name.

```sh
bytepleat compress data.bin
bytepleat compress data.bin --format gzip -o data.gz
bytepleat compress data.bin --format lz4 -o data.lz4
bytepleat decompress data.bin.zst -o restored.bin
bytepleat test data.bin.zst
bytepleat info data.bin.zst --json
bytepleat checksum restored.bin --json
```

Pipes use `-` explicitly:

```sh
bytepleat compress - -o - < data.bin > data.zst
bytepleat decompress - -o - < data.zst > restored.bin
```

The `--preset` values are `fast`, `balanced`, and `compact`. They map to Zstandard levels 1/3/9 and gzip levels 1/6/9; `--level` overrides the preset where supported. LZ4 has one supported level. Only Zstandard supports multiple threads; `--threads 0` selects the available CPU count for Zstandard.

Named file outputs are staged and published after successful completion. Existing output paths fail unless `--force` is supplied. Standard output is a stream: on an error it may already contain partial bytes. `info` inspects bounded metadata and does not validate the entire compressed stream; use `test` to decode and validate it.

## Folder archives

```sh
bytepleat pack photos -o photos.tar.zst --deterministic
bytepleat pack photos --format gzip -o photos.tar.gz
bytepleat pack photos --format lz4 -o photos.tar.lz4
bytepleat pack photos --format zip -o photos.zip
bytepleat pack report.pdf --format zip --stored -o report.zip
bytepleat pack photos --format 7z --solid --level 5 --dictionary 16777216 -o photos.7z
bytepleat pack photos --format 7z --no-solid -o photos-independent.7z
bytepleat unpack photos.zip -o extracted-photos
bytepleat unpack photos.7z -o extracted-photos
bytepleat unpack photos.tar.zst -o extracted-photos
```

Tar formats require a directory. ZIP and 7z accept one regular file or a directory. ZIP supports Stored and Deflate; `--stored` selects Stored. The 7z writer uses LZMA2, defaults to solid blocks and a 16 MiB dictionary, and supports `--no-solid`. See [format details](formats.md) for read compatibility and restrictions.

Packing rejects an output inside the input tree. Extraction requires a new destination. Only regular files and directories are supported; links, special files, and unsafe paths are rejected. Extraction stages and validates data before publication, but publishing multiple files is not a portable atomic directory transaction. Limits can be tuned with `--max-entries`, `--max-output`, and `--max-depth`; 7z decoding also accepts `--max-dictionary` and `--max-header`.

## Typed numeric buffers

Pco mode works on explicitly typed little-endian numeric words, not CSV or general files:

```sh
bytepleat compress samples.i32le --format pco --type i32 -o samples.pco
bytepleat test samples.pco --type i32
bytepleat decompress samples.pco --type i32 -o restored.i32le
```

Supported types are `i32`, `u32`, `i64`, `u64`, `f32`, and `f64`. Supply the matching `--type` during decode and test; input length must align to the selected word size. Pco is its existing standalone format, not an Bytepleat-specific wrapper. See [formats](formats.md#typed-pco-buffers).

## Limits and metadata

Default decoded output is capped at 1 GiB, and the default Zstandard window limit is 128 MiB. Archive entry, depth, header, and dictionary bounds are also applied. These are input and output limits, not an aggregate process-memory quota. Bytepleat is not a filesystem backup tool: permissions, owner, extended attributes, links, and portable timestamps are not preserved. Review [security and limits](security-limits.md) before using untrusted inputs.
