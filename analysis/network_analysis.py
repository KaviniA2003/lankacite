"""Network analysis of the LankaCite citation graph.
Outputs (all under evaluation/):
  top20_in_degree.csv / .md
  top20_pagerank.csv / .md
  citations_by_reporter_year.csv
  citations_by_reporter_year.png   (NLR / SLR / foreign over time)
  network_sample.png               (top-50 nodes by in-degree + their incoming edges)
"""
import json
import os
import re
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
GRAPH = os.path.join(ROOT, "data", "citation_graph.json")
OUT = os.path.join(ROOT, "evaluation")
os.makedirs(OUT, exist_ok=True)

g = json.load(open(GRAPH))
G = nx.DiGraph()
for n in g["nodes"]:
    G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
for e in g["edges"]:
    G.add_edge(e["source"], e["target"], **{k: v for k, v in e.items() if k not in ("source", "target")})
print(f"1) graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

indeg = sorted(G.in_degree(), key=lambda x: -x[1])
pr = nx.pagerank(G, alpha=0.85)
pr_sorted = sorted(pr.items(), key=lambda x: -x[1])


def row(nid, score):
    d = G.nodes[nid]
    return [nid, d.get("kind", ""), d.get("parties", "")[:120], d.get("year", ""), score]


def write_top(path_csv, path_md, header, items, score_fmt):
    import csv
    with open(path_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "kind", "parties", "year", header])
        for nid, score in items:
            w.writerow([nid, G.nodes[nid].get("kind", ""), G.nodes[nid].get("parties", ""),
                        G.nodes[nid].get("year", ""), score_fmt(score)])
    with open(path_md, "w") as f:
        f.write(f"# Top 20 by {header}\n\n")
        f.write(f"| rank | id | kind | parties | year | {header} |\n|---|---|---|---|---|---|\n")
        for i, (nid, score) in enumerate(items, 1):
            d = G.nodes[nid]
            f.write(f"| {i} | {nid} | {d.get('kind','')} | {d.get('parties','')[:80]} | {d.get('year','')} | {score_fmt(score)} |\n")


write_top(os.path.join(OUT, "top20_in_degree.csv"), os.path.join(OUT, "top20_in_degree.md"),
          "in_degree", indeg[:20], str)
write_top(os.path.join(OUT, "top20_pagerank.csv"), os.path.join(OUT, "top20_pagerank.md"),
          "pagerank", pr_sorted[:20], lambda x: f"{x:.5f}")
print("2) wrote top20 CSV/MD")

# citations to NLR/SLR/foreign over time
# determine year + reporter from edge target id (e.g. NLR_79_421, SLR_1997_2_98, AIR_1981_SC_852, Ch_1949_NA_333)
by_year = Counter()  # (year, bucket)
for s, t, d in G.edges(data=True):
    tgt_kind = G.nodes[t].get("kind", "")
    y = None
    raw = d.get("raw", "") or ""
    # try citing judgment's year
    src_year = G.nodes[s].get("year", "")
    if src_year and src_year.isdigit():
        y = int(src_year)
    if not y:
        continue
    key = d.get("link_method", "")
    # reporter bucket
    if tgt_kind == "foreign" or (key == "foreign_report"):
        bucket = "foreign"
    elif t.startswith("NLR_"):
        bucket = "NLR"
    elif t.startswith("SLR_") or "Sri" in raw or "SLR" in raw:
        bucket = "SLR"
    else:
        bucket = "other"
    by_year[(y, bucket)] += 1

import csv
with open(os.path.join(OUT, "citations_by_reporter_year.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["citing_year", "reporter_bucket", "count"])
    for (y, b), c in sorted(by_year.items()):
        w.writerow([y, b, c])

years = sorted({y for (y, _) in by_year})
buckets = ["NLR", "SLR", "foreign", "other"]
series = {b: [by_year[(y, b)] for y in years] for b in buckets}
fig, ax = plt.subplots(figsize=(9, 4.5))
for b in buckets:
    ax.plot(years, series[b], marker="o", label=b, linewidth=1.5, markersize=3)
ax.set_xlabel("citing judgment year")
ax.set_ylabel("citations")
ax.set_title("Citations by reporter over time")
ax.legend()
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "citations_by_reporter_year.png"), dpi=140)
print("3) wrote citations_by_reporter_year.csv/.png")

# graph figure: top-50 by in-degree + their incoming edges (one hop)
top50 = [nid for nid, _ in indeg[:50]]
sub = G.subgraph(list(set(top50) | set(src for src, tgt in G.in_edges(top50)))).copy()
if sub.number_of_nodes() > 500:
    # keep only incoming sources that cite >=2 of the top50
    keep = set(top50)
    for src, tgt in G.in_edges(top50):
        pass
    counts = Counter(src for src, tgt in G.in_edges(top50))
    keep |= {s for s, c in counts.items() if c >= 2}
    sub = G.subgraph(keep).copy()
pos = nx.spring_layout(sub, seed=42, k=0.5)
fig, ax = plt.subplots(figsize=(10, 10))
sizes = [max(30, G.in_degree(n) * 4) for n in sub.nodes()]
colors = ["#d62728" if n in top50 else "#1f77b4" for n in sub.nodes()]
nx.draw_networkx_edges(sub, pos, alpha=0.08, arrows=False, ax=ax)
nx.draw_networkx_nodes(sub, pos, node_size=sizes, node_color=colors, alpha=0.85, ax=ax)
labels = {n: (G.nodes[n].get("parties", "") or n)[:30] for n in top50[:15]}
nx.draw_networkx_labels(sub, pos, labels, font_size=7, ax=ax)
ax.set_title(f"Network: top-50 most-cited nodes (red) and their citers (blue). N={sub.number_of_nodes()}")
ax.axis("off")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "network_sample.png"), dpi=140)
print("4) wrote network_sample.png")
