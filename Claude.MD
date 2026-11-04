# LankaCite — project guide for Claude Code

## What this project is
Final-year undergraduate research project (BSc CS/AI, NIBM Kandy Innovation Centre; supervisor Prof. Y.P.R.D. Yapa; approved).
The researcher (Kavini) is also a law student and is the annotator.

**LankaCite** is an AI citator and hallucination checker for Sri Lankan case law. For every Sri Lankan case cited in an
AI-generated legal answer, it reports:
1. **Exists?** — is it a real Sri Lankan case?
2. **Details correct?** — case number, law report, year, court
3. **Supports the claim?** — does the judgment actually say what the AI claims?
4. **Still good law?** — has a later case overruled, doubted or distinguished it? (the citator part)

Underneath is Sri Lanka's first case-law **citation graph** and the first **precedent-treatment dataset**.

Two interfaces (final deliverable, Gradio app on Hugging Face Spaces):
- **Ask LankaCite** — an open LLM answers Sri Lankan legal questions; each cited case gets a live warning
  (✅ verified · ⚠️ details wrong · ❌ not found / doesn't support claim · 🔴 no longer good law).
- **Check an AI answer** — paste an answer from ChatGPT or any AI; external checks only.

## Research contributions (what the report must show)
1. First Sri Lankan case-law citation graph.
2. First Sri Lankan precedent-treatment dataset (~1,000–1,200 labelled citation contexts).
3. **Main result:** comparison of three treatment classifiers, especially on subtle negative treatments (distinguished, doubted).
4. "Good law" status model using Sri Lankan court hierarchy (bench size, SC > CA, pre-1972 Privy Council weight).
5. Four-check verification pipeline.
6. (Optional) internal-signal probe: do open LLMs' hidden states reveal when a cited case is fabricated/wrong?
7. Audit of ChatGPT and an open LLM on Sri Lankan legal citations (error rate per check).

Key gap references: Liu, Stammbach & Henderson (2026) arXiv:2606.21155 — legal hallucination detection is US-only and
external-only, no "good law" check. Ferrando et al. (ICLR 2025) — LLMs internally encode whether they recognise an entity.
Dahl et al. (2024) — LLMs near random on precedent relationships. Demir & Canbaz (NLLP 2025) — precedent treatment
classification. CaseHOLD (Zheng et al. 2021) — explicit overruling is easy (~keyword); subtle treatments are the challenge.

## Scope (keep it tight — 12-week project)
- Supreme Court judgments, 2009–2025, English only (no Sinhala).
- Primary focus for labelling/evaluation: fundamental rights (SC FR) cases; other SC cases kept in the graph.
- Probing: probes + entity-direction analysis only. **No circuit discovery.**
- Drop order if short of time: probe experiment → user test → non-FR cases.

## Hardware / compute
- MacBook Neo (A18 Pro, 8 GB RAM): steps 1–3 (scraping, citations, labelling).
- MacBook Air M4 (16 GB RAM): steps 4–8. PyTorch MPS for fine-tuning; Llama-3.1-8B 4-bit via Ollama or mlx-lm.
- Colab Pro (100 compute units): step 6 with 8B models — prefer L4 GPU, avoid A100, save hidden states to Drive as .npy.
- Keep code light enough for 8 GB where possible (small batches, stream from SQLite, don't load all texts at once if avoidable).
- Free Groq API is acceptable for LLM prompting methods that don't need model internals.

## Repo layout
```
scraping/collect_judgments.py   step 1 — DONE (lankalaw.net year pages; optional supremecourt.lk monthly pages)
citations/extract_citations.py  step 2 — run on full data; tests in tests/test_citations.py (pytest)
annotation/                     step 3 — labelling guide, Label Studio config, exports
models/                         step 4 — treatment classifiers A/B/C, NLI support check
status/                         good-law rules
probing/                        step 6 — hidden-state extraction + probes
app/                            Gradio app
evaluation/                     metrics, audit scripts, results tables
report/
data/                           NOT in git (judgments.db, pdfs/, citation_graph.*, exports)
```

## Data conventions
- `data/judgments.db` (SQLite), table `judgments`: case_id (normalised, e.g. `SC_FR_256_2017`), case_no_raw, parties,
  judgment_date, judge, keywords, listed_year, source, pdf_url, pdf_path, n_pages, n_chars, status, text.
- Case IDs come from `normalise_case_no()` in scraping/collect_judgments.py — always reuse it, never re-implement.
- Table `citations`: citing_case, kind (report | case_no | supra), raw, case_name, reporter (NLR/SLR/CLW/CLR/BLR or foreign),
  foreign_report, year, volume, page, case_no, minutes_date (from "SC Minutes of <date>"), report_key (e.g. `SLR_1997_2_98`,
  `NLR_71_529`, `NLR_79-1_421` for part-volumes, `Ch_1949_NA_333`, `AIR_1981_SC_852`), target, link_method
  (case_number | case_number+date | case_number_not_in_db | name_fuzzy | report_key_via_name | report_key | foreign_report |
  needs_review), link_score, candidate (the guessed judgment for needs_review rows; target stays unlinked), start_char
  (offset in the header-stripped, cleaned text, not the raw text), context (citing sentence ±1 sentence).
- Decision dates: `judgments.judgment_date` is empty; step 2 reads "Decided on" from the text (found for 1,772/1,891).
- `normalise_case_no()` also knows SC_CHC, SC_HCCA_LA, SC_TAB, SC_WRIT, SC_MISC, SC_EXP, CA_WRIT, CA_PHC (added step 2;
  existing IDs unchanged). 29 `UNPARSED_n` judgments would now parse, but step 1 was NOT re-run, so their IDs stay
  `UNPARSED_n`; step 2 maps their parsed number to the UNPARSED id when linking.
- Graph: `data/citation_graph.json` / `.graphml` (nodes: judgment_in_db | external_case | foreign; edges carry context).

## Step plan and status
- [x] 0. Topic approved. Pilot: ChatGPT Q1 of 20 done (6/6 cases real, 4/6 had wrong citation details). Q2–Q20 pending.
- [x] 1. Collect judgments (2009–2025) — done.
- [ ] 2. Extraction run + formats fixed (11,972 citations). Pending: evaluate on `data/citations_sample.csv` (50 judgments: precision, recall,
        linking accuracy); add citation formats found missing in real judgments.
- [ ] 3. Labelling. Labels: `followed/applied` · `distinguished` · `doubted/criticised` · `overruled/per incuriam` ·
        `referred (neutral)`. Build Label Studio config + import file of citation contexts (prioritise SC FR; oversample
        rare negatives via cue words: overruled, per incuriam, not followed, doubt, distinguishable).
        Reliability: Kavini labels (law student); re-label 150 after ~2 weeks (intra-annotator κ); one LLM labels
        150–300 as independent annotator (must be a DIFFERENT LLM from those tested as methods B/C); adjudicate disagreements.
        Also build a **keyword-masked test set** to show models learn meaning, not cue words.
- [ ] 4. Treatment classifiers on the same split: A = fine-tuned Legal-BERT/DeBERTa-v3; B = LLM zero/few-shot
        (Llama-3.1-8B); C = LLM + citation-graph context. Metrics: macro-F1, per-class F1, bootstrap significance.
        Then good-law status rules (overruled by equal/larger bench or higher court → 🔴; doubted/not followed → ⚠️).
- [ ] 5. Verification checks 1–4. Support check: retrieve paragraph (BM25 + bge embeddings) → NLI (DeBERTa-v3-MNLI)
        or LLM judge; evaluate on ~200 hand-labelled claim–paragraph pairs.
- [ ] 6. (Optional) Probe: ~500 citations generated by an open model, labelled via the checks; logistic-regression probe
        on hidden states at citation tokens; AUROC; compare probe vs external checks vs combined.
- [ ] 7. Audit: 50–100 Sri Lankan legal questions to ChatGPT + open model; score every citation on the 4 checks.
        Gradio app with both tabs.
- [ ] 8. Report, open dataset with datasheet, code, presentation.

## How to work with Kavini
- Explain in plain, simple language; she wants to understand what each step does and why.
- Before writing a large script, say briefly what it will do. Test code on small samples first (`--limit`).
- Every step should print a clear summary (counts, status) she can paste back.
- Scripts must be re-runnable (skip work already done) and save progress.
- Be polite to source websites (keep request delays). Never commit `data/`.
- Be honest about weaknesses and limitations — they go in the report.
- Commit with clear messages when a step works.