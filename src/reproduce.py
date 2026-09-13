"""
Reproduce every number reported in the paper.

Writes:
  results/table2_results.csv     Table 2: index by phase, detection delays
  results/table3_criticality.csv Table 3: node criticality chi(v)
  results/factors.csv            factor analysis quoted in the text
  results/static_vs_temporal.csv static aggregated graph vs temporal graph
  results/timings.csv            run times quoted in the text
  results/index_series.csv       O(t) for all configurations (data behind Fig. 3)

Usage:  python src/reproduce.py
"""
import csv, os, platform, statistics, sys, time
from decimal import Decimal, ROUND_HALF_UP

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model
from model import (CONFIGS, DMAX, DT, T_END, TIMES, W, ZONES,
                   mean, run, run_static, spill_times)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
os.makedirs(OUT, exist_ok=True)
CFGS = ["A", "B", "C"]
SPILL = spill_times()


def w(name, header, rows):
    path = os.path.join(OUT, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    print("wrote", os.path.relpath(path))


def fmt(x, nd=3):
    """Round half up, as in the paper (Python's format uses banker's rounding)."""
    return str(Decimal(repr(x)).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP))


# ---------- Table 2 ----------
series, detection = {}, {}
for cfg in CFGS:
    O, _, first_seen = run(cfg, spill=SPILL)
    series[cfg] = O
    detection[cfg] = {k: (first_seen[k] - SPILL[k] if k in first_seen else None)
                      for k in sorted(SPILL)}

rows = [
    ["mean O, normal regime (0-55 min)"] + [fmt(mean(series[c], 0, 55), 2) for c in CFGS],
    ["mean O, accident interval (60-115 min)"] + [fmt(mean(series[c], 60, 115), 2) for c in CFGS],
    ["mean O, after recovery (120-180 min)"] + [fmt(mean(series[c], 120, 180), 2) for c in CFGS],
    ["minimum O(t)"] + [fmt(min(series[c].values()), 2) for c in CFGS],
]
for k in sorted(SPILL):
    cells = []
    for c in CFGS:
        d = detection[c][k]
        cells.append("n/d" if d is None else ("<=5" if d == 0 else str(d)))
    rows.append([f"detection delay Z{k} (spill at {SPILL[k]} min), min"] + cells)
w("table2_results.csv", ["metric"] + CFGS, rows)

# ---------- Table 3 ----------
base = mean(run("C")[0])
crit = sorted(((n, base - mean(run("C", removed=(n,))[0])) for n in CONFIGS["C"] if n != "CC"),
              key=lambda x: -x[1])
w("table3_criticality.csv", ["node", "chi(v)"], [[n, fmt(v)] for n, v in crit])
print(f"baseline mean O over 0-{T_END} min, configuration C = {fmt(base)}")

# ---------- factor analysis ----------
rows = []
for cfg in CFGS:
    row = [cfg]
    for jam, destroy in [(False, False), (False, True), (True, False), (True, True)]:
        model.FLAGS["jam"], model.FLAGS["destroy"] = jam, destroy
        row.append(fmt(mean(run(cfg)[0], 60, 115)))
    rows.append(row)
model.FLAGS["jam"] = model.FLAGS["destroy"] = True
w("factors.csv", ["configuration", "no failures", "node loss only",
                  "link degradation only", "both"], rows)

# ---------- static vs temporal ----------
rows, static = [], {}
for cfg in CFGS:
    static[cfg] = run_static(cfg)
    diff = [(t, static[cfg][t] - series[cfg][t]) for t in TIMES]
    t_max, d_max = max(diff, key=lambda x: x[1])
    rows.append([cfg,
                 fmt(mean(static[cfg], 60, 115)), fmt(mean(series[cfg], 60, 115)),
                 fmt(mean(static[cfg], 60, 115) - mean(series[cfg], 60, 115)),
                 fmt(d_max), t_max])
w("static_vs_temporal.csv",
  ["configuration", "static mean (60-115)", "temporal mean (60-115)",
   "mean overestimate", "max pointwise overestimate", "at t, min"], rows)

# ---------- O(t) series ----------
w("index_series.csv",
  ["t_min"] + [f"O_{c}" for c in CFGS] + [f"O_static_{c}" for c in CFGS],
  [[t] + [fmt(series[c][t]) for c in CFGS] + [fmt(static[c][t]) for c in CFGS] for t in TIMES])


# ---------- timings ----------
def best(fn, n=20):
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1000)
    return min(ts), statistics.median(ts)


rows = []
for cfg in CFGS:
    mn, md = best(lambda c=cfg: run(c, spill=SPILL))
    rows.append([f"single run, configuration {cfg}", fmt(mn, 1), fmt(md, 1)])
mn, md = best(lambda: [base - mean(run("C", removed=(n,))[0]) for n in CONFIGS["C"] if n != "CC"], 5)
rows.append(["criticality, 15 runs", fmt(mn, 1), fmt(md, 1)])
mn, md = best(lambda: run_static("C"), 5)
rows.append(["static aggregated graph, configuration C", fmt(mn, 1), fmt(md, 1)])
w("timings.csv", ["operation", "min, ms", "median, ms"], rows)
print(f"environment: Python {sys.version.split()[0]}, {platform.machine()}, {platform.system()}")

# ---------- scenario summary ----------
print(f"\nzones: {len(ZONES)}, nodes: {len(model.NODES)}, step: {DT} min, horizon: {T_END} min")
print("weights:", {k: W[k] for k in sorted(W)})
print("max data age, min:", {k: DMAX[k] for k in sorted(DMAX)})
print("spill onset per zone, min:", {k: SPILL[k] for k in sorted(SPILL)})
