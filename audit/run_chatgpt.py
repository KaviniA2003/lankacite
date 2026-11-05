"""
LankaCite - ChatGPT audit. Answer every question in audit/questions.csv with the OpenAI API.

Prompt wording matches the pilot (Q1): assist a Sri Lankan lawyer, cite >=3 Sri Lankan decisions
with full case name, citation, year and principle. Fresh conversation per question, no web.

Writes audit/chatgpt_answers.jsonl one line per answer: q_id, area, question, model, date,
answer, prompt_tokens, completion_tokens, usd. Re-runnable: already-answered (q_id, model) pairs
are skipped.

Usage:
  python3 audit/run_chatgpt.py --model gpt-4o-mini --limit 2
  python3 audit/run_chatgpt.py --model gpt-4o-mini
  python3 audit/run_chatgpt.py --model gpt-4o
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
load_dotenv(os.path.join(ROOT, "..", ".env"))   # /Users/kaviniamandi/Documents/lankacite/.env

SYSTEM = (
    "You are assisting a Sri Lankan lawyer with legal research. "
    "Answer the question accurately and support every legal proposition with Sri Lankan case law. "
    "Cite at least three Sri Lankan court decisions, giving for each the full case name, citation "
    "(law report with volume, year and page, or Supreme Court case number), the year, and the "
    "principle for which the case is cited. Do not browse the web."
)

# USD per 1M tokens (Nov 2025 published list; update if OpenAI changes pricing).
PRICE = {
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
    "gpt-4o":      {"in": 2.50, "out": 10.00},
}


def key_of(row: dict) -> tuple:
    return (row["q_id"], row["model"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=os.path.join(ROOT, "audit", "questions.csv"))
    ap.add_argument("--answers", default=os.path.join(ROOT, "audit", "chatgpt_answers.jsonl"))
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=1500)
    ap.add_argument("--only", default="", help="comma-separated q_ids to re-answer (drops them first)")
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--frequency-penalty", type=float, default=0.3)
    ap.add_argument("--presence-penalty", type=float, default=0.1)
    args = ap.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not set (looked in /Users/kaviniamandi/Documents/lankacite/.env)")
    if args.model not in PRICE:
        print(f"warning: no price table for {args.model}; cost will be 0", file=sys.stderr)

    with open(args.questions, encoding="utf-8") as f:
        questions = list(csv.DictReader(f))
    if args.limit:
        questions = questions[: args.limit]

    retry_ids = {s.strip() for s in args.only.split(",") if s.strip()} if args.only else set()
    done = set()
    if os.path.exists(args.answers):
        kept = []
        with open(args.answers, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                if retry_ids and d["model"] == args.model and d["q_id"] in retry_ids:
                    continue  # drop so we re-answer it
                kept.append(line)
                done.add((d["q_id"], d["model"]))
        if retry_ids:
            with open(args.answers, "w", encoding="utf-8") as f:
                f.writelines(kept)
            print(f"0) dropped {len(retry_ids)} prior answers for {args.model}")
    todo = [q for q in questions if (q["q_id"], args.model) not in done
            and (not retry_ids or q["q_id"] in retry_ids)]
    print(f"1) {len(questions)} questions, {len(done)} already in file, {len(todo)} to do for {args.model}")
    if not todo:
        _print_total(args.answers, args.model)
        return

    client = OpenAI()
    total_in = total_out = 0
    total_cost = 0.0
    for k, q in enumerate(todo, 1):
        t0 = time.time()
        try:
            resp = client.chat.completions.create(
                model=args.model,
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": q["question"]}],
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                frequency_penalty=args.frequency_penalty,
                presence_penalty=args.presence_penalty,
            )
        except Exception as e:
            print(f"   [{k}/{len(todo)}] {q['q_id']}: ERROR {type(e).__name__}: {e}", flush=True)
            continue
        answer = resp.choices[0].message.content or ""
        u = resp.usage
        p = PRICE.get(args.model, {"in": 0, "out": 0})
        usd = u.prompt_tokens * p["in"] / 1e6 + u.completion_tokens * p["out"] / 1e6
        total_in += u.prompt_tokens
        total_out += u.completion_tokens
        total_cost += usd
        with open(args.answers, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(q_id=q["q_id"], area=q["area"], question=q["question"],
                                    model=args.model,
                                    date=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    answer=answer,
                                    prompt_tokens=u.prompt_tokens,
                                    completion_tokens=u.completion_tokens,
                                    usd=round(usd, 6)), ensure_ascii=False) + "\n")
        print(f"   [{k}/{len(todo)}] {q['q_id']}: {u.prompt_tokens} in + {u.completion_tokens} out "
              f"= ${usd:.4f} ({time.time()-t0:.1f}s)", flush=True)

    print(f"2) this run ({args.model}): {total_in} in + {total_out} out = ${total_cost:.4f}")
    _print_total(args.answers, args.model)


def _print_total(path, model):
    total = 0.0
    n = 0
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                if d["model"] == model:
                    total += d.get("usd", 0)
                    n += 1
    print(f"3) {model}: {n} answers in file, cumulative ${total:.4f}")


if __name__ == "__main__":
    main()
