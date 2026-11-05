"""
LankaCite - Audit + probe data: Llama-3.2-3B-Instruct answers the 80 audit questions with case citations.

For every question it saves
  audit/llama_answers.jsonl                one line per question: q_id, area, question, answer, n_tokens, seconds
  probing/hidden_states/<q_id>.npy         hidden states at the LAST token of each citation in the answer,
                                           shape (n_citations, n_layers+1, hidden) float16 (layer 0 = embeddings)
  probing/hidden_states/citations.jsonl    one line per citation: q_id, idx (row in the .npy), raw, report_key,
                                           case_no, case_name, char_start, char_end, token_index
Citations are found with the same extractor as step 2 (citations/extract_citations.py), so they can be checked
against judgments.db later (exists? details correct?) to label real vs fabricated for the probe.

Re-runnable: questions already in llama_answers.jsonl are skipped, so a crash or Ctrl-C loses at most one question.

Model: unsloth/Llama-3.2-3B-Instruct (ungated copy of meta-llama/Llama-3.2-3B-Instruct, identical weights).
Greedy decoding (do_sample=False) so the run is reproducible.

Run:
  python3 audit/run_llama.py --limit 3            # test on 3 questions
  caffeinate -i python3 audit/run_llama.py        # full run (keeps the Mac awake)
"""

import argparse
import csv
import json
import os
import re
import sys
import time

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "citations"))
sys.path.insert(0, os.path.join(ROOT, "scraping"))
from extract_citations import extract_from_judgment  # noqa: E402

MODEL = "unsloth/Llama-3.2-3B-Instruct"
SYSTEM = ("You are a legal research assistant specialising in Sri Lankan law. Answer the question accurately. "
          "Support every legal proposition with Sri Lankan case law, giving the full citation for each case: "
          "case name, year, law report, volume and page (for example: Perera v. Attorney General (1992) 1 Sri LR 199), "
          "or the Supreme Court case number (for example: SC FR 256/2017).")


def find_spans(answer: str, cits: list[dict]) -> list[tuple[int, int]]:
    """Character span of each citation in the ORIGINAL answer (the extractor works on whitespace-cleaned text)."""
    spans, pos = [], 0
    for c in cits:
        rx = r"\s*".join(re.escape(tok) for tok in c["raw"].split())
        m = re.compile(rx).search(answer, pos) or re.compile(rx).search(answer)
        spans.append((m.start(), m.end()) if m else (None, None))
        if m:
            pos = m.start() + 1
    return spans


def token_char_ends(tok, ids: list[int]) -> list[int]:
    """End character (in the decoded answer) of each generated token."""
    ends, prev = [], ""
    for i in range(len(ids)):
        s = tok.decode(ids[: i + 1], skip_special_tokens=True)
        ends.append(len(s))
        prev = s
    return ends


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=os.path.join(ROOT, "audit", "questions.csv"))
    ap.add_argument("--answers", default=os.path.join(ROOT, "audit", "llama_answers.jsonl"))
    ap.add_argument("--hs-dir", default=os.path.join(ROOT, "probing", "hidden_states"))
    ap.add_argument("--limit", type=int, default=0, help="only the first N questions (test)")
    ap.add_argument("--max-new-tokens", type=int, default=700)
    args = ap.parse_args()

    with open(args.questions, encoding="utf-8") as f:
        questions = list(csv.DictReader(f))
    if args.limit:
        questions = questions[: args.limit]
    done = set()
    if os.path.exists(args.answers):
        with open(args.answers, encoding="utf-8") as f:
            done = {json.loads(line)["q_id"] for line in f if line.strip()}
    todo = [q for q in questions if q["q_id"] not in done]
    print(f"1) {len(questions)} questions, {len(done & {q['q_id'] for q in questions})} already done, {len(todo)} to do")
    if not todo:
        return
    os.makedirs(args.hs_dir, exist_ok=True)
    # drop citation rows of a question that crashed half-way (it is redone below)
    cpath = os.path.join(args.hs_dir, "citations.jsonl")
    if os.path.exists(cpath):
        with open(cpath, encoding="utf-8") as f:
            keep = [line for line in f if line.strip() and json.loads(line)["q_id"] in done]
        with open(cpath, "w", encoding="utf-8") as f:
            f.writelines(keep)

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float16).to(device).eval()
    print(f"2) {MODEL} loaded on {device} in {time.time() - t0:.0f}s "
          f"({model.config.num_hidden_layers} layers, hidden size {model.config.hidden_size})")

    total_cits = 0
    for k, q in enumerate(todo, 1):
        t0 = time.time()
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": q["question"]}]
        prompt_ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt",
                                             return_dict=True)["input_ids"].to(device)
        with torch.no_grad():
            out = model.generate(prompt_ids, max_new_tokens=args.max_new_tokens, do_sample=False,
                                 temperature=None, top_p=None, pad_token_id=tok.eos_token_id)
        gen = out[0, prompt_ids.shape[1]:].tolist()
        while gen and gen[-1] in (tok.eos_token_id, *tok.convert_tokens_to_ids(["<|eot_id|>"])):
            gen = gen[:-1]
        answer = tok.decode(gen, skip_special_tokens=True)

        # citations in the answer (same extractor as step 2), and the last generated token of each
        cits = [c for c in extract_from_judgment(f"LLAMA_{q['q_id']}", answer) if c["kind"] != "supra"]
        spans = find_spans(answer, cits)
        ends = token_char_ends(tok, gen)
        rows, tok_idx = [], []
        for c, (a, b) in zip(cits, spans):
            if a is None:
                continue
            ti = next((i for i, e in enumerate(ends) if e >= b), len(gen) - 1)
            rows.append(dict(q_id=q["q_id"], idx=len(rows), raw=c["raw"], report_key=c["report_key"],
                             case_no=c["case_no"], case_name=c["case_name"], char_start=a, char_end=b,
                             token_index=ti))
            tok_idx.append(prompt_ids.shape[1] + ti)

        # one forward pass over prompt + answer: hidden states of every layer at those tokens
        if tok_idx:
            full = torch.tensor([prompt_ids[0].tolist() + gen], device=device)
            with torch.no_grad():
                hs = model(full, output_hidden_states=True).hidden_states   # (layers+1) x [1, seq, hidden]
            arr = torch.stack([h[0, tok_idx] for h in hs], dim=1).to(torch.float16).cpu().numpy()
            del hs
        else:
            arr = np.zeros((0, model.config.num_hidden_layers + 1, model.config.hidden_size), np.float16)
        np.save(os.path.join(args.hs_dir, f"{q['q_id']}.npy"), arr)
        with open(os.path.join(args.hs_dir, "citations.jsonl"), "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        # answer written LAST, so a question only counts as done once its hidden states are saved
        with open(args.answers, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(q_id=q["q_id"], area=q["area"], question=q["question"], answer=answer,
                                    n_tokens=len(gen), n_citations=len(rows), seconds=round(time.time() - t0, 1)),
                               ensure_ascii=False) + "\n")
        total_cits += len(rows)
        if device == "mps":
            torch.mps.empty_cache()
        print(f"   [{k}/{len(todo)}] {q['q_id']}: {len(gen)} tokens, {len(rows)} citations, {time.time() - t0:.0f}s",
              flush=True)

    print(f"3) Done: {len(todo)} questions answered, {total_cits} citations with hidden states saved.")
    print(f"   Answers: {args.answers}\n   Hidden states: {args.hs_dir}/<q_id>.npy + citations.jsonl")


if __name__ == "__main__":
    main()
