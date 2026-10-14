# Arqlet contributor instructions

Arqlet is a Rust CLI using standard byte and archive formats. Keep the documented compatibility and lossless byte-restoration contract.

- Read the relevant src/ module and tests/ before changing it.
- Use scoped rg searches; exclude target/, .ci-results/ and dependency source unless needed.
- Check cargo fmt --all -- --check, cargo clippy --locked --all-targets -- -D warnings and cargo test --locked for Rust changes.
- Packaging tools require Python 3.10 or newer; run python -m unittest discover -s scripts/tests -v.
- Changes to parsers, limits, unsafe paths or output publication need meaningful regression coverage.
- Retain third-party licenses and the local sevenz-rust2 patch; do not upgrade dependencies silently.
- Documentation and the static site must match actual release capabilities and verified platform evidence.
- Do not add downloaded corpora, credentials, personal data, caches or build outputs to the repository.
- Separate correctness/interoperability checks from performance benchmarks and include all pipeline costs in measurements.
- Keep each parallel task's file ownership distinct. Publishing/tagging is a maintainer operation.
