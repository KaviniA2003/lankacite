# LankaCite — project guide for Claude Code

## ⚠️ DEADLINE MODE: final submission + viva in 3 days
Speed beats perfection. Any accuracy above ~85% is good enough — note weak spots as limitations, don't polish.
Do NOT add scope. Claude Code writes all code; long runs go overnight; results tables/figures are produced for the report
as each part finishes. Commit every evening.

## What this project is
Final-year undergraduate research project (BSc CS/AI, NIBM Kandy Innovation Centre; supervisor Prof. Y.P.R.D. Yapa; approved).
The researcher (Kavini) is also a law student and is the only annotator (no external annotators).

**LankaCite** — Sri Lanka's first case-law citation graph, used to (1) find the most influential Sri Lankan judgments,
(2) classify how later judgments treat earlier ones, (3) measure how accurately AI tools cite Sri Lankan case law, and
(4) test whether an open LLM's internal signals reveal when it fabricates a case citation.

**Tool — LankaCite Check** (simple Gradio app): paste any AI legal answer; each Sri Lankan case it cites is marked
✅ real & correctly cited · ⚠️ wrong details · ❌ not found · 🔴 later doubted/overruled.

## Contributions the report must show
1. First Sri Lankan case-law citation graph + most influential judgments (in-degree, PageRank).
2. First Sri Lankan precedent-treatment dataset (~200 labelled citation contexts) + comparison of 2 classifiers.
3. First measurement of AI citation accuracy on Sri Lankan law (ChatGPT + Llama).
4. Internal-signal probe for fabricated legal citations — novel anywhere (Liu, Stammbach & Henderson 2026,
   arXiv:2606.21155, check legal citations externally only, US-only). Null result is acceptable.
5. Working tool.

Key references: Liu et al. 2026; Dahl et al. 2024 (Large Legal Fictions); Magesh et al. 2025; Ferrando et al. ICLR 2025
(entity recognition & hallucination); Orgad et al. ICLR 2025; Azaria & Mitchell 2023; Demir & Canbaz NLLP 2025
(precedent treatment); CaseHOLD (Zheng et al. 2021); SCaLe-QA (Jayawardena et al. 2024); Charlotin AI Hallucination DB.

## 3-day plan
**Tonight (Wed)**
1. Quick citation fixes (≤1 hour): year ranges "(1978-79)" / "[1978/79]"; "1997 [1 SCC 388]"; "(1875) LR 10 QB 111";
   merge `NLR_79-1_421` with `NLR_79_421` (part-volumes → same key); case names before [brackets]; no-volume
   "[2003] Sri L.R. 270". Add tests, re-run, commit.
2. `audit/questions.csv`: 80 Sri Lankan legal questions requiring case citations (FR, land, contract, criminal, labour, admin).
3. Llama-3.2-3B-Instruct locally (transformers, MPS): answer each question with case citations; save answer text AND hidden
   states (all layers, last token of each citation) as .npy. Test on 3 questions, then full run overnight. Resumable.
4. (Kavini) ChatGPT answers to 20 of the questions → `audit/chatgpt_answers.txt`.

**Thursday — treatment classification + Part 1**
- 400 citation contexts selected from the DB (dedup, prioritise SC FR, oversample cue-word negatives) and
  labelled by Claude (Anthropic) — `annotation/silver_labels.csv`. These are **silver labels**, not Kavini's.
  Labels (4): `followed/applied` · `distinguished` · `doubted/overruled` · `neutral`.
- Kavini verifies a 50-item gold set (random sample) in `annotation/gold_check_50.csv` — writes OK or the
  correct label in the `kavini_label` column. That gives a reliability figure (Claude-vs-Kavini agreement).
- Method A: fine-tuned Legal-BERT or DeBERTa-v3-base (MPS). Method B: LLM prompting (zero/few-shot) — MUST use a
  different model from Claude (local Llama-3.2-3B once overnight run finishes, or Groq if a key is available).
  Metrics: macro-F1, per-class F1, confusion matrix. Results table + figure.
- Good-law flag: case gets 🔴 if any later citation is classified doubted/overruled.
- Network analysis (in-degree, PageRank, top 20 judgments, citations to NLR/SLR/foreign over time) + graph figure.

**Friday — audit, probe, tool**
- Automatic checks on all ChatGPT + Llama citations against judgments.db/graph: exists? details correct?
  → audit table (error rate per check per model).
- Kavini re-labels 50 of the 200 → intra-annotator Cohen's κ.
- Probe: labels from the automatic checks (real vs fabricated/wrong); logistic regression per layer; AUROC by layer;
  compare probe vs external checks vs combined. Figure.
- Gradio app (LankaCite Check).

**Saturday** — report polish, screenshots, submission, viva prep.

Drop order if late: probe → good-law flag → network extras. Never drop the tool or the report.

## Hardware
- MacBook Air M4 16 GB (main): training, Llama-3.2-3B with hidden states, app. Keep Mac awake (`caffeinate`) for overnight runs.
- MacBook Neo 8 GB: light work only. Colab Pro: only if the 3B run fails locally (L4, save to Drive).

## Repo layout
```
scraping/collect_judgments.py   DONE
citations/extract_citations.py  DONE (quick fixes tonight); tests in tests/test_citations.py (pytest)
analysis/                       network analysis + graph figure
annotation/                     200 contexts with LLM suggestions, Kavini's labels, re-label set
models/                         treatment classifiers A and B
audit/                          questions, ChatGPT answers, Llama answers, automatic checks
probing/                        hidden states (.npy) + probes
app/                            Gradio app
evaluation/                     results tables + figures for the report
report/
data/                           NOT in git
```

## Running
- `source venv/bin/activate`, then `pip install -r requirements.txt`.
- Step 1: `python3 scraping/collect_judgments.py --years 2009-2025 --out data` (`--limit N` for a test).
- Step 2: `python3 citations/extract_citations.py --db data/judgments.db --out data` (`--limit N` for a test).
- Tests: `python3 -m pytest -q`.
- This folder is its own git repo; the parent `LankaCite/` repo only tracks it as a submodule pointer.

## Data conventions
- `data/judgments.db` table `judgments`: case_id (normalised, e.g. `SC_FR_256_2017`), case_no_raw, parties, judgment_date,
  judge, keywords, listed_year, source, pdf_url, pdf_path, n_pages, n_chars, status, text.
- Case IDs from `normalise_case_no()` in scraping/collect_judgments.py — always reuse it. It also knows SC_CHC, SC_HCCA_LA,
  SC_TAB, SC_WRIT, SC_MISC, SC_EXP, CA_WRIT, CA_PHC. 29 judgments keep `UNPARSED_n` IDs (step 1 not re-run); step 2 maps
  their parsed numbers to the UNPARSED id when linking.
- Decision dates: `judgments.judgment_date` is empty; step 2 reads "Decided on" from the text (found for 1,772/1,891).
- Table `citations`: citing_case, kind (report | case_no | supra), raw, case_name, reporter, foreign_report, year, volume,
  page, case_no, minutes_date, report_key (e.g. `SLR_1997_2_98`, `NLR_71_529`, `Ch_1949_NA_333`, `AIR_1981_SC_852`),
  target, link_method (case_number | case_number+date | case_number_not_in_db | name_fuzzy | report_key_via_name |
  report_key | foreign_report | needs_review), link_score, candidate, start_char (in header-stripped cleaned text), context.
- Graph: `data/citation_graph.json` / `.graphml` (nodes: judgment_in_db | external_case | foreign; edges carry context).

## Status
- [x] Topic approved. Pilot: ChatGPT Q1 → 6/6 real cases, 4/6 wrong citation details.
- [x] Step 1: 1,897 rows — 1,891 ok, 3 download_failed, 3 little_text_maybe_scanned.
- [x] Step 2: 11,972 citations (9,340 report · 2,277 case_no · 355 supra); 20 tests pass (commit 6ba15c6).
      Links: report_key 8,163 · foreign_report 1,388 · case_number_not_in_db 1,205 · case_number+date 528 ·
      case_number 522 · needs_review 87 · name_fuzzy 60 · report_key_via_name 19.
- [x] Step 2 evaluation (50-judgment sample, 322 citations; AI-assisted, verified by Kavini):
      precision 98.8% (317/321), link accuracy 88.6% (39/44). File: evaluation/citations_sample_filled.csv.
      Recall check skipped for time → state as limitation.
- [x] Tonight's quick fixes: year ranges, `1997 [1 SCC 388]`, old `(1875) LR 10 QB 111` series (key `LR_QB_1875_10_111`),
      NLR part-volumes share the volume key (`NLR_79_421`), no-volume `[2003] Sri L.R. 270`, case-name cleanup.
      25 tests pass. Re-run: 12,016 citations (9,383 report · 2,277 case_no · 356 supra); 7,622 with a case name.
- [x] 80 audit questions written; Llama-3.2-3B test on 3 questions worked (27-38 s/q on MPS, citations extracted,
      hidden states saved). Full 80-question run launched in background with `caffeinate -i`.
- [x] Silver labels pass 1 (Claude free-form): followed/applied 256 · neutral 94 · distinguished 33 ·
      doubted/overruled 17. Kavini's gold 50 verified 27/48 (56.2%, kappa 0.318) - Claude over-called
      followed/applied on counsel citations, lists and footnotes.
- [x] Silver labels pass 2 (strict rule: followed/applied only when the CURRENT judge actively applies
      / approves the case; counsel citations, parenthetical lists and footnotes -> neutral).
      221 of 400 labels changed. Final distribution: followed/applied 121 · neutral 261 · distinguished 10 ·
      doubted/overruled 8. Re-score vs gold 50: 32/48 (66.7%, kappa 0.386). File: `annotation/silver_labels.csv`.
      Near-duplicate rows in gold 50 (ids {8871,8836} and {8985,8835} - identical context) collapsed when scoring.
- [x] `annotation/gold_extra_20.csv` - 20 NEW contexts with strong negative/distinguishing cues (none in
      silver_labels.csv) for Kavini to label; will boost the doubted/overruled + distinguished support.
- [x] Llama 77/77 questions answered (3 earlier test + 77 overnight = 80 total; 494 citations with hidden states
      saved to `probing/hidden_states/`). Method B for treatment classification will use Llama-3.2-3B (not Claude).
- [x] ChatGPT audit: 80 answers each for gpt-4o-mini ($0.038) and gpt-4o ($0.366) in `audit/chatgpt_answers.jsonl`.
      gpt-4o-mini initially degenerated on 33/80 at temperature=0 (repeats like "S. S. S. S. ..."); fixed by
      switching to temperature=0.3 + frequency_penalty=0.3 + presence_penalty=0.1 and re-running those 33.
- [x] Silver labels pass 3 (Kavini's rule: followed/applied even inside a list if the judge accepts the proposition;
      only current-court overruling counts as doubted/overruled). followed/applied 113 · neutral 275 · distinguished 8
      · doubted/overruled 4. Gold agreement on the extra 20: 4/20 (cue-word heuristic too lenient; Kavini re-labelled
      many as neutral or followed/applied).
- [x] Combined gold set (50 + 20, deduped contexts = 68): followed/applied 23 · distinguished 4 · doubted/overruled 3 ·
      neutral 38. File: `evaluation/gold.csv`.
- [x] Method A (DistilBERT fine-tuned on 400 silver, test on 68 gold, MPS, 6 epochs, class-weighted CE):
      **macro-F1 0.551**, accuracy 0.735. Per-class F1 - followed/applied 0.634 (23), distinguished 0.750 (4),
      doubted/overruled 0.000 (3), neutral 0.819 (38). File: `evaluation/method_a_distilbert.md`.
- [x] Method B (Llama-3.2-3B zero-shot, same 68 gold): **macro-F1 0.389**, accuracy 0.397. Per-class - followed/applied
      0.565, distinguished 0.276, doubted/overruled 0.400, neutral 0.314. Method B catches rare negatives Method A
      misses, but at low precision. File: `evaluation/method_b_llama.md`.
- [x] Network analysis: 6,597 nodes · 10,085 edges. Top in-degree: Channa Peiris v AG (39), Gamaethige v Siriwardena (36),
      Amal Sudath Silva (34). Top PageRank: Gamaethige (0.00136), Ghany v Dissanayake (0.00105), Haputhantirige v AG (0.00100).
      Files: `evaluation/top20_in_degree.md`, `top20_pagerank.md`, `citations_by_reporter_year.png`, `network_sample.png`.
- [x] External reference index: 2,197 cases scraped from lankalaw.net A-Z indexes (SC 1878-2011 + CA 1809-2011; CA letters
      v/w/x/y/z return 404 - no CA cases on those pages). File: `data/reported_cases_index.csv`.
- [x] AI-citation audit (post-external-index, with claimed principle stored per row):
      | model | verified-correct | verified-correct-external | exists-name-unverified | number-exists-unverified | name-mismatch | wrong-case | real-name-wrong-citation | not-found-anywhere | unverifiable | undecidable | total | verified-rate |
      | gpt-4o | 3 | 0 | 7 | 16 | 5 | 2 | 7 | 89 | 3 | 84 | 216 | 1.4% |
      | gpt-4o-mini | 0 | 0 | 2 | 15 | 0 | 0 | 0 | 82 | 6 | 23 | 128 | 0.0% |
      | llama-3.2-3b | 64 | 0 | 12 | 124 | 99 | 32 | 108 | 40 | 13 | 2 | 494 | 13.0% |
      Sanity: 5/6 pilot citations verified (1/6 is `number-exists-unverified` - case number right, AI gave no name).
      File: `evaluation/audit_results_per_model.md`, examples in `audit_verdict_examples.md`.
- [x] Hallucination probe (Llama-3.2-3B hidden states; clean subset = citations where AI gave a name AND verdict is
      verified-correct / name-mismatch / wrong-case / not-found-anywhere; N=118 (41 real, 77 fake)):
      | probe | input | AUROC |
      | main | layer 20 hidden state, GroupKFold by (q_id, raw) | **1.000** |
      | surface baseline | has_rk, has_cn, has_name, raw-length | 0.670 |
      | shuffled-label control | layer 20, labels permuted | 0.529 |
      | report-key only (N=94) | layer 20 | 0.993 |
      Shuffled control works; surface baseline well below main; probe is detecting more than citation format.
      Caveat: perfect AUROC on N=118 with 3072-dim LR likely over-optimistic on a truly held-out set;
      report as strong signal, not as a tool-ready detector. File: `evaluation/probe.md`.
- [ ] Gradio tool, probe calibration on more data, Kavini's verify_30 + needs_kavini + gold_extra_20 sign-off.
- [ ] Thursday · Friday · Saturday (see plan).

## How to work with Kavini
- Plain, simple language. One clear next task at a time.
- Before a large script, one or two lines on what it will do. Test on small samples first.
- Every script prints a short summary she can paste back. Scripts are re-runnable and save progress.
- Produce report-ready tables (markdown/CSV) and figures (PNG) in evaluation/ as each part finishes.
- Be honest about weaknesses — they go in Limitations. Never commit `data/`.