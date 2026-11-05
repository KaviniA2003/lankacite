"""LankaCite Check - a Gradio app.

Paste any AI legal answer. For every Sri Lankan case citation we show:
  citation | AI's case name | verdict (icon) | real case name (where known) | principle

Verdict icons:
  ✅  verified against our corpus or the external lankalaw index
  ⚠️  number or name exists but we cannot fully confirm
  ❌  wrong case / not found anywhere
  🔴  the cited case was later doubted or overruled by a Sri Lankan court

Second tab: top-20 most-cited judgments + the network figure.

Launch:  source venv/bin/activate && python3 app/lankacite_check.py
"""
import os
import re
import sqlite3
import sys
import time

import gradio as gr
import joblib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "audit"))
sys.path.insert(0, os.path.join(ROOT, "citations"))
sys.path.insert(0, os.path.join(ROOT, "scraping"))

from extract_citations import extract_from_judgment  # noqa: E402
from check_citations import (  # noqa: E402
    classify, extra_case_nos, attach_name_from_text, extract_principle,
    sl_citation, all_cits, report_names, judgments_by_id, cn_names, ext_by_key,
)

DB = os.path.join(ROOT, "data", "judgments.db")

# ----- precompute "is doubted" flag for every target in the graph -------
# A target gets 🔴 if any later citation's context contains overrule/per-incuriam cues.
OVERRULE_RE = re.compile(
    r"\b(overrul(?:e|ed|ing)|per\s+incuriam|no\s+longer\s+good\s+law|"
    r"cannot\s+be\s+treated\s+as\s+good\s+law|wrongly\s+decided|disapprov(?:ed|e|ing))\b",
    re.I)
doubted = set()
con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
for r in con.execute("SELECT target, context FROM citations WHERE context IS NOT NULL"):
    if r["target"] and OVERRULE_RE.search(r["context"]):
        doubted.add(r["target"])
con.close()
print(f"{len(doubted)} judgments flagged as later doubted/overruled by cue-word scan")


ICON = {
    "verified-correct":            "✅ verified",
    "verified-correct-external":   "✅ verified (external index)",
    "exists-name-unverified":      "⚠️ key exists, name not in DB",
    "number-exists-unverified":    "⚠️ number exists, AI gave no name",
    "name-mismatch":               "❌ wrong case at that number",
    "wrong-case":                  "❌ wrong case (external)",
    "real-name-wrong-citation":    "❌ real name but wrong citation",
    "not-found-anywhere":          "❌ not found anywhere",
    "unverifiable":                "⚠️ after 2011, cannot verify",
    "undecidable":                 "⚠️ partial info",
}


def db_real_name(c):
    rk = c.get("report_key") or ""
    cn = c.get("case_no") or ""
    if cn and cn in judgments_by_id:
        return judgments_by_id[cn]["parties"] or ""
    if rk and rk in report_names:
        return next(iter(report_names[rk]), "")
    if cn and cn in cn_names:
        return next(iter(cn_names[cn]), "")
    if rk and rk in ext_by_key:
        return ext_by_key[rk][0][0]
    return ""


def check_answer(text):
    if not text or not text.strip():
        return []
    cits = [c for c in extract_from_judgment("APP", text) if c.get("kind") != "supra"]
    seen = {c["raw"] for c in cits}
    for c in extra_case_nos(text):
        if c["raw"] not in seen:
            attach_name_from_text(c, text)
            cits.append(c)
    rows = []
    for c in cits:
        if not sl_citation(c):
            continue
        v, reason = classify(c)
        tgt = c.get("case_no") or c.get("report_key") or ""
        icon = ICON.get(v, v)
        if tgt in doubted and v.startswith("verified"):
            icon = "🔴 verified but later doubted/overruled"
        rows.append([c["raw"], c.get("case_name") or "-", icon,
                     db_real_name(c) or "-", extract_principle(text, c["raw"])[:160] or "-"])
    return rows


# ----- top-20 tab ------------------------------------------------------
import csv
top_rows = []
with open(os.path.join(ROOT, "evaluation", "top20_in_degree.csv")) as f:
    for i, r in enumerate(csv.DictReader(f), 1):
        top_rows.append([i, r["parties"][:70], r["year"], r["kind"], r["in_degree"]])

NETWORK_PNG = os.path.join(ROOT, "evaluation", "network_sample.png")

# ===== Ask LankaCite tab - lazy Llama + probe =====
PROBE_PATH = os.path.join(ROOT, "probing", "probe.joblib")
LLAMA_MODEL_ID = "unsloth/Llama-3.2-3B-Instruct"
SYSTEM_PROMPT = ("You are a legal research assistant specialising in Sri Lankan law. Answer the "
                 "question accurately. Support every legal proposition with Sri Lankan case law, "
                 "giving the full citation for each case: case name, year, law report, volume and "
                 "page (for example: Perera v. Attorney General (1992) 1 Sri LR 199), or the "
                 "Supreme Court case number (for example: SC FR 256/2017).")
# Regex for completed citations (same families the extractor recognises)
CIT_LIVE_RE = re.compile(
    r"(?P<rep>\((?:19|20)\d{2}\)\s*\d*\s*(?:Sri\s*L\.?R\.?|NLR|BLR)\s*\d+|"
    r"\[(?:19|20)\d{2}\]\s*\d*\s*(?:Sri\s*L\.?R\.?|NLR|BLR)\s*\d+|"
    r"\d+\s+NLR\s+\d+)|"
    r"(?P<cn>S\.?\s*C\.?\s*(?:F\.?\s*R\.?|Appeal|HCCA|Writ|CHC|TAB)?\s*\(?(?:FR|Appeal)?\)?\s*/?\s*\d{1,5}\s*/\s*(?:19|20)\d{2})",
    re.I)

_llama = {"tok": None, "model": None, "device": None, "layer": None, "clf": None}


def _load_llama():
    if _llama["model"] is not None:
        return
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    probe = joblib.load(PROBE_PATH)
    _llama["clf"] = probe["clf"]
    _llama["layer"] = probe["layer"]
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(LLAMA_MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(LLAMA_MODEL_ID, dtype=torch.float16).to(device).eval()
    _llama.update({"tok": tok, "model": model, "device": device, "torch": torch})
    print(f"Llama loaded on {device}, probe layer {probe['layer']}")


def _score(hs: np.ndarray) -> float:
    return float(_llama["clf"].predict_proba(hs.reshape(1, -1))[:, 0][0])  # P(fake)


def _risk_label(p_fake):
    pct = int(round(p_fake * 100))
    if p_fake >= 0.6:
        return f"⚠️ high risk ({pct}%)"
    if p_fake >= 0.35:
        return f"⚠️ medium ({pct}%)"
    return f"✓ low ({pct}%)"


def _render_live(text, scored):
    if not scored:
        return "_no completed citation yet_"
    lines = ["| citation | internal-signal |", "|---|---|"]
    for raw, info in scored.items():
        lines.append(f"| `{raw}` | {info['risk']} |")
    return "\n".join(lines)


def _final_table(text, scored):
    cits = [c for c in extract_from_judgment("ASK", text) if c.get("kind") != "supra"]
    seen_raw = {c["raw"] for c in cits}
    for c in extra_case_nos(text):
        if c["raw"] not in seen_raw:
            attach_name_from_text(c, text)
            cits.append(c)
    rows = []
    verified = high = 0
    for c in cits:
        if not sl_citation(c):
            continue
        v, _ = classify(c)
        tgt = c.get("case_no") or c.get("report_key") or ""
        icon = ICON.get(v, v)
        if tgt in doubted and v.startswith("verified"):
            icon = "🔴 verified but later doubted/overruled"
            verified += 1
        elif v.startswith("verified"):
            verified += 1
        # match probe score by raw
        score_info = scored.get(c["raw"])
        risk = score_info["risk"] if score_info else "-"
        if score_info and score_info["p_fake"] >= 0.6:
            high += 1
        rows.append([c["raw"], c.get("case_name") or "-", risk, icon,
                     db_real_name(c) or "-"])
    summary = f"**{verified} of {len(rows)} citations verified; {high} high-risk.**"
    return rows, summary


def ask_lankacite(question):
    if not question or not question.strip():
        yield "", "_no question_", [], ""
        return
    _load_llama()
    torch = _llama["torch"]
    tok = _llama["tok"]; model = _llama["model"]; dev = _llama["device"]
    layer = _llama["layer"]

    msgs = [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}]
    prompt_ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt",
                                         return_dict=True)["input_ids"].to(dev)
    eos = tok.eos_token_id
    eot = tok.convert_tokens_to_ids("<|eot_id|>")

    # prime with prompt (single forward pass to build cache)
    with torch.no_grad():
        out = model(input_ids=prompt_ids, use_cache=True, output_hidden_states=False)
    past = out.past_key_values
    next_id = int(out.logits[0, -1].argmax())

    gen_ids = []
    hs_per_token = []
    token_char_end = []     # end position (in decoded answer) of each generated token
    scored = {}             # raw -> {p_fake, risk}
    answer = ""
    t0 = time.time()
    MAX_NEW = 700
    for step in range(MAX_NEW):
        if next_id in (eos, eot):
            break
        gen_ids.append(next_id)
        tok_text = tok.decode([next_id], skip_special_tokens=True)
        answer += tok_text
        token_char_end.append(len(answer))

        # forward one token with cache; keep hidden state at probe layer
        inp = torch.tensor([[next_id]], device=dev)
        with torch.no_grad():
            out = model(input_ids=inp, past_key_values=past, use_cache=True,
                        output_hidden_states=True)
        past = out.past_key_values
        hs = out.hidden_states[layer][0, -1].float().cpu().numpy()
        hs_per_token.append(hs)
        next_id = int(out.logits[0, -1].argmax())

        # check for completed citations in the text so far
        for m in CIT_LIVE_RE.finditer(answer):
            raw = m.group(0)
            if raw in scored:
                continue
            # only treat as 'completed' if at least one token later exists (so the LLM moved on)
            if m.end() > len(answer) - 3:
                continue
            # find the generated-token index whose end >= m.end()
            tok_i = next((i for i, e in enumerate(token_char_end) if e >= m.end()), None)
            if tok_i is None:
                continue
            p_fake = _score(hs_per_token[tok_i])
            scored[raw] = {"p_fake": p_fake, "risk": _risk_label(p_fake)}
            yield answer, _render_live(answer, scored), [], ""

        if step % 8 == 0:
            yield answer, _render_live(answer, scored), [], ""

    elapsed = time.time() - t0
    table, summary = _final_table(answer, scored)
    footer = (f"{summary}  ·  generated in {elapsed:.1f}s · {len(gen_ids)} tokens · "
              f"**Internal-signal risk is an experimental early warning "
              f"(probe trained on ~120 citations). External verification is the final check.**")
    yield answer, _render_live(answer, scored), table, footer

# ----- example answers --------------------------------------------------
EX_PILOT = (
    "Six real Sri Lankan authorities on Article 126 are: "
    "Wijerathna v Sri Lanka Ports Authority SC FR 256/2017; "
    "Dayaratne v National Savings Bank SC 452/2001; "
    "Perera v Dissanayake SC FR 55/2017; "
    "Perera v Cyril Ranatunga [1993] 1 Sri LR 39; "
    "Ratnayake v Attorney General [1997] 2 Sri LR 98; "
    "Randeniya SC FR 322/2011."
)

EX_GPT = (
    "Under Article 126 of the Sri Lankan Constitution, a fundamental rights application must be filed "
    "within one month. 1. Kariapper v. Wijesinha (1977) 79 NLR 409: the Supreme Court emphasised strict "
    "adherence to the time limit. 2. Siriwardena v. Rodrigo (1986) 1 SLR 384: the Court held the one-month "
    "period is mandatory but delay may be excused in exceptional circumstances. "
    "3. Gamaethige v Siriwardena (1988) 1 SLR 384: the Court reiterated that the time limit runs from the "
    "date of infringement."
)

EX_LLAMA = (
    "The Supreme Court has dealt with cases of torture under Article 11 of the Constitution. "
    "1. Ranjan v. Attorney General (2005) 1 SLR 1: the Court held the police had committed torture. "
    "2. Sampath v. Attorney General (2007) 2 SLR 1: compensation of LKR 1,000,000 was awarded. "
    "3. Jayasuriya v. Attorney General (2011) 3 SLR 1: the Court found the arrest arbitrary."
)


with gr.Blocks(title="LankaCite Check") as app:
    gr.Markdown("# LankaCite Check\n"
                "Paste an AI legal answer. Every Sri Lankan case citation is checked against "
                "`data/judgments.db` (2009-2025), the citation graph, and the lankalaw.net A-Z index.")
    with gr.Tab("Check an answer"):
        with gr.Row():
            with gr.Column():
                txt = gr.Textbox(lines=14, label="Paste AI answer here", placeholder="…")
                with gr.Row():
                    b1 = gr.Button("Load pilot answer")
                    b2 = gr.Button("Load gpt-4o answer")
                    b3 = gr.Button("Load Llama answer")
                btn = gr.Button("Check citations", variant="primary")
            out = gr.Dataframe(
                headers=["citation", "AI's case name", "verdict", "real case name (DB / external)", "claimed principle"],
                row_count=(0, "dynamic"),
                wrap=True, label="Results",
            )
        b1.click(lambda: EX_PILOT, outputs=txt)
        b2.click(lambda: EX_GPT, outputs=txt)
        b3.click(lambda: EX_LLAMA, outputs=txt)
        btn.click(check_answer, inputs=txt, outputs=out)

    with gr.Tab("Ask LankaCite"):
        gr.Markdown("### Ask a Sri Lankan legal question\n"
                    "Llama-3.2-3B generates an answer token by token. Each completed citation is "
                    "scored by an experimental internal-signal probe (early warning). The external "
                    "verifier runs on every citation when generation finishes (final check).")
        q_in = gr.Textbox(lines=3, label="Question",
                          placeholder="e.g. What is the time limit for a fundamental rights application?")
        ask_btn = gr.Button("Ask", variant="primary")
        answer_box = gr.Textbox(label="Streaming answer", lines=14)
        live_md = gr.Markdown("_citations with live risk will appear here_")
        final_tbl = gr.Dataframe(
            headers=["citation", "AI's case name", "internal-signal risk",
                     "external verdict", "real case name"],
            row_count=(0, "dynamic"), wrap=True, label="Final check")
        footer = gr.Markdown("")
        ask_btn.click(ask_lankacite, inputs=q_in,
                      outputs=[answer_box, live_md, final_tbl, footer])

    with gr.Tab("Most cited cases"):
        gr.Markdown("### Top 20 by in-degree in the citation graph")
        gr.Dataframe(value=top_rows,
                     headers=["#", "parties", "year", "kind", "in-degree"],
                     row_count=(len(top_rows), "fixed"), wrap=True)
        gr.Markdown("### Network figure (top 50 most-cited + their citers)")
        gr.Image(value=NETWORK_PNG, label="network_sample.png")

    gr.Markdown("---\n"
                "Icons: ✅ verified · ⚠️ number/name exists but not fully confirmed · "
                "❌ wrong case / not found · 🔴 later doubted or overruled by a Sri Lankan court.")


if __name__ == "__main__":
    app.launch(server_name="127.0.0.1", inbrowser=True)  # auto-port, avoid clashes
