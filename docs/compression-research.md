# Compression research and design decision

Updated 2026-10-15. This is a targeted evidence review, not an exhaustive survey of compression literature or source repositories.

## Question

Would a new Bytepleat-specific codec or archive format materially improve the balance of speed, compressed size, compatibility, and safe integration across heterogeneous files?

## Search and screening

The `science-paper-search` helper used the OpenAlex title/abstract index on 2026-10-15. The feasibility lab retains four semantic/keyword searches, an ANS related-work search, and DOI/OpenAlex work lookups under `results/desktop-research/bytepleat-literature-2026-10-15/`; that private local evidence bundle is not included in this public repository. Search themes covered LZ77 plus entropy coding, software codec trade-offs, ANS, and per-file codec selection for heterogeneous collections. Results were screened by title and abstract; the ANS preprint, related-work records, Pco, and primary format specifications were checked against original sources. IEEE Xplore blocked direct automated access for the DCC 2024 selection paper, so its reported quantitative result below is abstract-level evidence only. Search ranking is discovery evidence, not proof of paper quality, implementation quality, or literature completeness. The result set contains unrelated and weakly relevant work; this is an exploratory review, not a systematic or exhaustive survey.

## Findings that transfer

| Idea | Primary evidence | Relevance to Bytepleat |
| --- | --- | --- |
| Lempel–Ziv parsing finds repeated sequences without requiring a known source model. | Ziv and Lempel, [“A Universal Algorithm for Sequential Data Compression”](https://doi.org/10.1109/TIT.1977.1055714), *IEEE Transactions on Information Theory* 23(3), 1977. | A durable general-purpose foundation, but not evidence that a new encoder will beat mature implementations. The parse strategy, window, match finder, and entropy coder still determine real trade-offs. |
| Asymmetric numeral systems (ANS) provide a family of entropy coders with a different speed/rate trade-off from Huffman and arithmetic coding. | Duda, [“Asymmetric numeral systems: entropy coding combining speed of Huffman coding with compression rate of arithmetic coding”](https://arxiv.org/abs/1311.2540), 2013 preprint. Zstandard's [RFC 8878](https://www.rfc-editor.org/rfc/rfc8878.html) specifies FSE and Huffman entropy coding in its existing format. | Combining LZ-style sequences with a modern entropy coder is already present in a mature interoperable codec. Reimplementing that combination in a new Bytepleat format has no demonstrated advantage in the current measurements. |
| Specialized preprocessing can improve numeric sequences whose distributions fit the model. | Lončarić, Jeppesen, and Zinberg, [“Pcodec: Better Compression for Numerical Sequences”](https://arxiv.org/abs/2502.06112), DOI [10.48550/arXiv.2502.06112]; implementation: [pcodec/pcodec](https://github.com/pcodec/pcodec). | The paper's abstract reports results on six columnar datasets and describes a method aimed at numerical sequences. Bytepleat exposes Pco only for explicit little-endian numeric types; this evidence does not transfer to arbitrary files, ZIP entries, or archives. |

### Related algorithmic work

| Idea | Primary evidence | Relevance to Bytepleat |
| --- | --- | --- |
| Entropy-coder setup and probability-table description affect small-input cost and achievable rate. | Duda, [“Encoding of probability distributions for Asymmetric Numeral Systems”](https://arxiv.org/abs/2106.06438), 2021; Pieprzyk et al., [“The Compression Optimality of Asymmetric Numeral Systems”](https://doi.org/10.3390/e25040672), 2023. | These papers identify active math and modeling questions, but the current project has not isolated entropy coding as its bottleneck. A new entropy coder would need same-container ablations and end-to-end model/signaling costs. |
| A selector may choose different existing codecs for heterogeneous files. | Burtchell and Burtscher, [“Using Machine Learning to Predict Effective Compression Algorithms for Heterogeneous Datasets”](https://doi.org/10.1109/DCC58796.2024.00026), DCC 2024. The local literature record's abstract reports an average ratio 97.8% of the best method over nearly 9,000 files in that paper's setup. | This is a directly relevant hypothesis, not a comparable Bytepleat result. The full paper was not independently read here; its abstract's corpus and methods must not be generalized to this product. |

## Reusable implementations and formats

- [facebook/zstd](https://github.com/facebook/zstd): established general-purpose byte-stream codec and reference implementation; Zstandard frames are already available through Bytepleat.
- [ip7z/7zip](https://github.com/ip7z/7zip): established multi-format archiver and LZMA/LZMA2 implementation; current measurements include the 7zz CLI.
- [lz4/lz4](https://github.com/lz4/lz4): LZ4 frame implementation and specification; current measurements include its public source tree.
- [pcodec/pcodec](https://github.com/pcodec/pcodec): specialized numeric stream implementation; Bytepleat already uses the Pco stream for typed numeric input.

These projects are useful compatibility and comparison points. Reuse still requires version, license, and dependency review; the repository tracks shipped dependency notices in [`THIRD-PARTY.json`](../THIRD-PARTY.json).

## Decision from current measurements

Keep the existing standard-container and codec layers. Do not add a proprietary archive format or claim a new codec is faster or smaller yet. The current benchmark is one Apple M5 Max/macOS run over six selected workloads. It shows concrete trade-offs: the external `tar | zstd` pipeline had lower encode times on the two reported source-tree samples; it was slightly smaller on the Zstandard source tree, while Bytepleat `tar.zst` was slightly smaller on the LZ4 source tree. ZIP/7z results also vary by workload and tool. The complete scope and missing public rerun inputs are in the [benchmark report](benchmarks.md).

The next experiment should test a per-file selector among existing encoders, not introduce a new codec. The feasibility lab's falsifiable proposal sets a stronger bar: at least 10,000 files and 1 GiB from multiple public sources; split by project into training, validation, and held-out sets; compare fixed Bytepleat default, Deflate-6, LZMA2-5, Zstandard-3, and Stored; and report a per-file best-method oracle as an explicitly unattainable upper bound. A deterministic sample-and-select policy can be compared with a learned predictor only if all probe work is charged.

Include every method ID, selection record, dictionary/model byte, ZIP header, checksum, probe read, scratch write, and final archive byte. Verify exact paths, sizes, and hashes for every file. Report encode/decode wall time, CPU, RSS, scratch IO, archive ratio, per-project distributions, and project-bootstrap confidence intervals. The proposal's acceptance gate is: at least 5% less total archive data than fixed default with the 95% project-bootstrap interval's lower bound at least 2%; encode time at most 1.5×, decode at most 1.1×, and peak RSS at most 1.25× the baseline; zero integrity mismatches; and all selector/metadata/probe costs included. Missing any bound rejects the proposed opportunity at this scope.

The simplest first implementation candidate is an adaptive ZIP entry choice between existing interoperable Stored and Deflate methods, measured against fixed Deflate and fixed Stored on source/text, already-compressed media, and generated incompressible controls. It does not need a proprietary format, but it is only a subset of the broader selector study. Other ideas, such as dictionaries across related small files, need end-to-end accounting for training, storage, distribution, and decode setup before implementation.

## Reproducibility boundary

The checked-in [benchmark CSV](benchmarks/summary.csv) and [provenance](benchmarks/provenance.json) support inspection of the recorded run. The harness, raw logs, prepared corpora, and some executables remain in the separate research lab and are not independently reproducible from this repository. Publish a pinned harness and fixture manifest before using that run as a release-level comparison.
