# AI industry research corpus

[English](README.md) · [简体中文](README.zh-CN.md)

Optional historical research material about AI companies, products, models and industry developments, prepared from pinned versions of `aiknowledge-cli` and `ai-knowledge-graph`. Download [ai-industry-v1.zip](https://github.com/rrrrrredy/agent-trajectory-data/releases/download/ai-industry-corpus-v1/ai-industry-v1.zip), extract it and open `README.zh-CN.md` to choose a document, or `recovered/README.zh-CN.md` for the five selected recoveries. The [release page](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/ai-industry-corpus-v1) also provides SHA-256 checksums and the inventory. No retrieval service or Toolkit installation is needed.

The delivery includes readable documents, a JSONL catalog, normalized version metadata, unchanged original records, per-occurrence lineage, title-keyed excerpts, derived graph records, and an archive of every tracked input file. Differing versions remain separate; a reading copy chooses one existing record rather than assembling an article from unmatched versions. Generated summaries and metadata-generated text are explicitly separate from stored captures. Original date fields do not establish publication dates. Cleanup grants no additional redistribution or training rights.

`existing-source-map.jsonl` associates the material with Toolkit's frozen source pack, whose original files are retained unchanged. Materials, task-specific source packs, evaluation tasks and actual runs remain different units. This delivery adds no evaluation tasks, model runs or training demonstrations and does not change historical results. Future tasks can explicitly select the recovered material as a new input version.

See the [Chinese guide](README.zh-CN.md) for file layout and use, [inventory summary](inventory-summary.json) for counts, and [recovery notes](recovery-notes.zh-CN.md) for selected findings and remaining gaps.

To rebuild, place the two source repositories and `research-toolkit` beside this repository, with the pinned commits available, then run:

```bash
python scripts/build_ai_industry_corpus.py --inputs .. --output artifacts/ai-industry-v1
```

The standard-library-only script reuses existing immutable dataset writers and reads pinned Git objects without contacting original sites or models. Existing output directories are never overwritten. Raw deliverables follow the repository's existing `artifacts/` convention, outside the tracked source tree. The unchanged package is published as the separate `ai-industry-corpus-v1` prerelease, retaining historical versions and unverified labels without replacing the runtime dataset's latest release. This optional corpus adds neither a default Toolkit dependency nor cross-project retrieval.
