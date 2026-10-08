"""Check every quantitative / ordinal claim made in the paper against results/summary.json.

Exit status 0 only if all checks pass.  Each check prints the evidence it used.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "..", "results")
S = json.load(open(os.path.join(R, "summary.json")))["scenarios"]
PROTOS = ["DSRC", "C-V2X", "5G-V2X"]; SCN = ["urban", "mixed", "vile_parle"]; DENS = ["low", "medium", "high"]
fails = []; n = 0

def check(name, ok, evidence=""):
    global n; n += 1
    print(("PASS " if ok else "FAIL ") + name + (f"   [{evidence}]" if evidence else ""))
    if not ok: fails.append(name)

def m(s, d, p, k): return S[s][d]["proto"][p][k][0]
def c(s, d, p, k): return S[s][d]["proto"][p][k][1]

cells = [(s, d) for s in SCN for d in DENS]
check("all 9 scenario/density cells present with >=6 seeds", all(d in S.get(s, {}) and S[s][d]["n_seeds"] >= 6 for s, d in cells))

# C1  PDR300 ordering 5G > C-V2X > DSRC in every cell, beyond the 95% CIs
ok = all(m(s, d, "5G-V2X", "pdr300") - c(s, d, "5G-V2X", "pdr300") > m(s, d, "C-V2X", "pdr300") + c(s, d, "C-V2X", "pdr300") and
         m(s, d, "C-V2X", "pdr300") - c(s, d, "C-V2X", "pdr300") > m(s, d, "DSRC", "pdr300") + c(s, d, "DSRC", "pdr300") for s, d in cells)
check("C1 PDR300 ordering 5G-V2X > C-V2X > DSRC in all 9 cells, CIs disjoint", ok)

# C2  latency ordering and near-determinism
ok = all(m(s, d, "5G-V2X", "lat300") < m(s, d, "DSRC", "lat300") < m(s, d, "C-V2X", "lat300") for s, d in cells)
check("C2 latency 5G-V2X < DSRC < C-V2X in all cells", ok)
mx = max(c(s, d, p, "lat300") for s, d in cells for p in PROTOS)
check("C2b latency CI half-width < 0.05 ms", mx < 0.05, f"max CI={mx:.4f}")

# C3  density effects
drop = {s: {p: m(s, "low", p, "pdr300") - m(s, "high", p, "pdr300") for p in PROTOS} for s in SCN}
check("C3a DSRC PDR300 falls from low to high density in every scenario", all(drop[s]["DSRC"] > 0 for s in SCN),
      str({s: round(drop[s]["DSRC"], 2) for s in SCN}))
check("C3b 5G-V2X PDR300 falls from low to high density in every scenario", all(drop[s]["5G-V2X"] > 0 for s in SCN),
      str({s: round(drop[s]["5G-V2X"], 2) for s in SCN}))
check("C3c C-V2X changes by < 0.6 pp between low and high density", all(abs(drop[s]["C-V2X"]) < 0.6 for s in SCN),
      str({s: round(drop[s]["C-V2X"], 2) for s in SCN}))
check("C3d mixed scenario degrades most for DSRC", drop["mixed"]["DSRC"] == max(drop[s]["DSRC"] for s in SCN))
check("C3e mean local neighbors and obstructions higher at high than medium density (mixed)",
      S["mixed"]["high"]["mean_nloc"][0] > S["mixed"]["medium"]["mean_nloc"][0] and
      S["mixed"]["high"]["mean_nobs300"][0] > S["mixed"]["medium"]["mean_nobs300"][0])
check("C3f goodput increases with density for all protocols/scenarios",
      all(m(s, "low", p, "goodput_mbps") < m(s, "medium", p, "goodput_mbps") < m(s, "high", p, "goodput_mbps") for s in SCN for p in PROTOS))
check("C3g goodput ordering 5G-V2X > C-V2X > DSRC (own range)",
      all(m(s, d, "5G-V2X", "goodput_mbps") > m(s, d, "C-V2X", "goodput_mbps") > m(s, d, "DSRC", "goodput_mbps") for s, d in cells))

# C4  weather
def wchg(s, d, p, key="pdr300_rel_change_pct", w="rain"): return S[s][d]["proto"][p]["weather"][w][key]
vals = [(abs(S[s][d]["proto"][p]["weather"][w][k][0]), abs(S[s][d]["proto"][p]["weather"][w][k][1]))
        for s, d in cells for p in ("DSRC", "C-V2X") for w in ("rain", "fog") for k in ("pdr300_rel_change_pct", "pdr_own_rel_change_pct")]
check("C4a DSRC and C-V2X mean |relative PDR change| < 0.5% in rain and fog", max(v[0] for v in vals) < 0.5, f"max={max(v[0] for v in vals):.3f}")
check("C4a2 ...and the 95% CI includes zero in most (>= 80%) of those comparisons", sum(v[0] <= v[1] for v in vals) >= 0.8 * len(vals),
      f"{sum(v[0] <= v[1] for v in vals)}/{len(vals)}")
ok = all(abs(wchg(s, d, "5G-V2X", "pdr_own_rel_change_pct", "rain")[0]) > abs(wchg(s, d, "5G-V2X", "pdr_own_rel_change_pct", "fog")[0]) for s, d in cells)
check("C4b 5G-V2X own-range effect of rain exceeds that of fog", ok)
ok = all(abs(wchg(s, d, "5G-V2X", "pdr_own_rel_change_pct", "rain")[0]) > abs(wchg(s, d, "5G-V2X", "pdr300_rel_change_pct", "rain")[0]) for s, d in cells)
check("C4c 5G-V2X rain effect is larger over own range than within 300 m", ok)
dl = max(abs(S[s][d]["proto"][p]["weather"][w]["lat300"][0] - m(s, d, p, "lat300")) for s, d in cells for p in PROTOS for w in ("rain", "fog"))
check("C4d weather changes latency by < 0.05 ms", dl < 0.05, f"max={dl:.4f}")
wc = json.load(open(os.path.join(R, "weather_coeffs.json")))["gamma_db_per_km"]
check("C4e ITU coefficients: 5.9 GHz rain/fog < 1 dB/km, 28 GHz rain > 4 dB/km, fog(28)>fog(5.9)",
      wc["5.9"]["rain"] < 1 and wc["5.9"]["fog"] < 1 and wc["28.0"]["rain"] > 4 and wc["28.0"]["fog"] > wc["5.9"]["fog"],
      f"{wc['5.9']['rain']}/{wc['5.9']['fog']}/{wc['28.0']['rain']}/{wc['28.0']['fog']}")

# C5  PDR definition: pair-based PDR << neighbor-link PDR
check("C5a pair-based (legacy) PDR is below neighbor-link PDR300 for every protocol and cell",
      all(m(s, d, p, "legacy_pdr") < m(s, d, p, "pdr300") for s, d in cells for p in PROTOS))
check("C5b pair coverage is a small fraction (<60%) of pairs in Vile Parle",
      all(m("vile_parle", d, p, "coverage") < 60 for d in DENS for p in PROTOS),
      str({p: round(m("vile_parle", "medium", p, "coverage"), 1) for p in PROTOS}))
check("C5c absolute PDR300 stays moderate (< 80%) everywhere (paper: relative index, not 'reliable')",
      all(m(s, d, p, "pdr300") < 80 for s, d in cells for p in PROTOS),
      f"max={max(m(s, d, p, 'pdr300') for s, d in cells for p in PROTOS):.1f}")

# C6  stability score ranking: 5G first, DSRC above C-V2X
ok = all(m(s, d, "5G-V2X", "score") > m(s, d, "DSRC", "score") > m(s, d, "C-V2X", "score") for s, d in cells)
check("C6 stability score ranks 5G-V2X > DSRC > C-V2X", ok)

# C7  relay selection
def rel(s, d, p, k): return S[s][d]["proto"][p]["relay"][k]
for p in PROTOS:
    check(f"C7a {p}: stability-aware gain over random > 0 in every cell (CI excludes 0)",
          all(rel(s, d, p, "gain_vs_random_pct")[0] - rel(s, d, p, "gain_vs_random_pct")[1] > 0 for s, d in cells))
    check(f"C7b {p}: stability-aware >= random, oracle >= stability-aware in every cell",
          all(rel(s, d, p, "oracle")[0] >= rel(s, d, p, "stability_default")[0] >= rel(s, d, p, "random")[0] for s, d in cells))
check("C7c gain over random is largest for 5G-V2X (medium density, Vile Parle)",
      rel("vile_parle", "medium", "5G-V2X", "gain_vs_random_pct")[0] == max(rel("vile_parle", "medium", p, "gain_vs_random_pct")[0] for p in PROTOS))
check("C7d relay gain over random grows from low to high density (5G-V2X, each scenario)",
      all(rel(s, "high", "5G-V2X", "gain_vs_random_pct")[0] > rel(s, "low", "5G-V2X", "gain_vs_random_pct")[0] for s in SCN))
check("C7e weight sensitivity: equal and delivery-heavy weights still beat random (5G-V2X, VP medium)",
      all(rel("vile_parle", "medium", "5G-V2X", k)[0] > rel("vile_parle", "medium", "5G-V2X", "random")[0]
          for k in ("stability_equal", "stability_delivery_heavy")))
check("C7f absolute end-to-end delivery stays low (< 40%) as the paper states",
      all(rel(s, d, p, "stability_default")[0] < 40 for s, d in cells for p in PROTOS),
      f"max={max(rel(s, d, p, 'stability_default')[0] for s, d in cells for p in PROTOS):.1f}")

print(f"\n{n - len(fails)}/{n} checks passed")
if fails:
    print("FAILED:", *fails, sep="\n  ")
sys.exit(1 if fails else 0)
