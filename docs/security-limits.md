# Security and limits

Arqlet processes compressed data and archive-controlled metadata. Keep it current, review the limits below, and use private vulnerability reporting as described in [SECURITY.md](../SECURITY.md). These controls reduce accepted input scope; they do not establish an aggregate memory quota, formal security proof, or security certification.

## Defaults

- Decoded byte-stream output: 1 GiB (`--max-output` can change the cap).
- Zstandard window: 128 MiB (`--max-window-log 27` by default).
- Archive entries: 100,000; path depth: 64; both can be changed with command options.
- ZIP compressed input: 1 GiB; classic ZIP entry ceiling: 65,534.
- 7z metadata: 100,000 entries and 64 coder nodes; header: 16 MiB; dictionary: 128 MiB by default and maximum.
- Pco compressed input: 1 GiB; decoded chunks and total output are bounded.

The caps govern specific accepted inputs and decoded output. They do not guarantee a fixed peak memory use across all inputs or platforms.

## Filesystem and publication behavior

Inputs are retained. Named file outputs are written to a temporary file and published after successful completion; an existing output requires `--force`. Stream output to stdout may be partial when an error occurs.

Extraction requires a new destination, stages and validates the archive, and accepts only regular files and directories. Links, special/sparse files, traversal, unsafe paths, and aliases are rejected. Publication of a populated directory across multiple filesystem operations is best-effort, not a portable atomic transaction; a failure during publication can briefly expose partial files.

Archives preserve file bytes and relative paths, not complete filesystem metadata. Permissions, owner, links, extended attributes, and portable timestamps are not preserved. Tar metadata overrides are restricted; see [formats](formats.md#folder-archives).

## Format-specific boundaries

ZIP support is classic Stored/Deflate only. ZIP64, encryption, split volumes, SFX, and unsupported methods are rejected. 7z support is unencrypted, single-volume, with a bounded set of decoder methods; it is not arbitrary 7z compatibility. RAR is not decoded by Arqlet. Pco requires a correct explicit numeric type.

Frame checksums can detect accidental corruption. They do not authenticate data or protect against malicious replacement. `info` inspects metadata and does not validate complete payload integrity; use `test` or extraction to decode and validate.
