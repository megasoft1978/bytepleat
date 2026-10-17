## Orchestration (yowork + codex)
Follow the global protocol: Sonnet/Sol plans+reviews, Haiku/Luna implement in parallel (skill `orchestrate`). Details: ~/.claude-work/CLAUDE.md, ~/.codex/AGENTS.md.
- Verify: `cargo fmt --all -- --check && cargo clippy --locked --all-targets -- -D warnings && cargo test --locked && python -m unittest discover -s scripts/tests -v` (Python 3.10+)
- Browser/UI test: n/a locally (site/ is static; desktop-ui-smoke runs in CI)
- Push policy: publishing/tagging is maintainer-only (AGENTS.md); otherwise commit+push when review CLEAN and tests pass
- Project overrides: parser, limit and unsafe-path changes need regression tests; keep third-party licenses and local sevenz-rust2 patch; no silent dependency upgrades
