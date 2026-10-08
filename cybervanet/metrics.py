"""Single source of truth for every per-run metric (PDR, latency, goodput, stability ...).

Used by aggregate.py (paper tables/figures), core.py (both web sites) and the tests, so that
the paper and the sites cannot disagree.
"""
import glob, json, os, re
import numpy as np
from scipy import stats

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
PROTOS = ["DSRC", "C-V2X", "5G-V2X"]; WEATHERS = ["clear", "rain", "fog"]
SCEN = ["urban", "mixed", "vile_parle"]; DENS = {"2.0": "low", "1.0": "medium", "0.5": "high"}
STRATS = ["random", "greedy", "stability_default", "stability_equal", "stability_delivery_heavy", "oracle"]
PKT_BITS = 300 * 8

def ci(x):
    x = np.asarray(x, float)
    if len(x) < 2: return float(x.mean()), 0.0
    return float(x.mean()), float(stats.t.ppf(0.975, len(x) - 1) * x.std(ddof=1) / np.sqrt(len(x)))

runs = {}
for f in sorted(glob.glob(os.path.join(R, "runs", "*.json"))):
    j = json.load(open(f))
    m = re.match(r"(\w+?)_p([\d.]+)_s(\d+)", j["trace"])
    runs.setdefault((m.group(1), m.group(2)), []).append(j)

def per_run(j, p, w="clear"):
    a = j["acc"]; k = f"{p}|{w}|"; T = a["snapshots"]
    d = {}
    d["pdr300"] = 100 * a[k + "rx300"] / a[k + "tx300"]
    d["pdr_own"] = 100 * a[k + "rxown"] / a[k + "txown"]
    d["loss300"] = 100 - d["pdr300"]
    d["lat300"] = a[k + "lat300"] / a[k + "rx300"]
    d["lat_sd"] = np.sqrt(max(a[k + "lat300sq"] / a[k + "rx300"] - d["lat300"] ** 2, 0))
    d["goodput_mbps"] = a[k + "rxown"] * PKT_BITS / (T * 1e6)
    ser = j["series"][p][w]
    d["goodput_peak_mbps"] = max(x[3] for x in ser) * PKT_BITS / 1e6
    d["goodput_per_veh_kbps"] = d["goodput_mbps"] * 1000 / (a["n_active"] / T)
    d["score"] = a[k + "score300"] / a[k + "score300_n"]
    d["coverage"] = 100 * a[k + "txown"] / a["ordered_pairs"]
    d["legacy_pdr"] = 100 * a[k + "rxown"] / a["ordered_pairs"]
    d["tx300"] = a[k + "tx300"] / T; d["rx300"] = a[k + "rx300"] / T
    return d

