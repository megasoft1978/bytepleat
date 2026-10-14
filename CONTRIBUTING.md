# Contributing

Bug reports, compatibility reports, and focused proposals are welcome through [GitHub Issues](https://github.com/megasoft1978/bytepleat/issues). Please search existing issues first and include the Bytepleat version, operating system and architecture, exact command, and a small reproducible example. Do not attach private or sensitive files.

For code changes, keep patches focused and preserve byte-for-byte restoration. Describe format compatibility changes and security implications. Before opening a pull request, run the relevant checks from the repository root:

```sh
cargo fmt --all -- --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --locked
```

Include the commands you ran and their results. Do not present a single-machine timing result as cross-platform evidence. New dependencies and format behavior should be documented with provenance and limitations. The maintainers review changes through GitHub; there is no separate submission address.
