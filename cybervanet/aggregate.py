"""Aggregate per-run JSON into summary tables (mean +/- 95% CI over seeds)."""
import json, os
import numpy as np
from metrics import *
from metrics import R, runs, per_run, ci

out = {"scenarios": {}, "weather": WEATHERS}
for (scn, per), js in runs.items():
    E = out["scenarios"].setdefault(scn, {})[DENS[per]] = {"n_seeds": len(js), "period": per}
    E["mean_active"] = ci([j["acc"]["n_active"] / j["acc"]["snapshots"] for j in js])
    E["mean_nloc"] = ci([j["acc"]["mean_nloc"] / j["acc"]["snapshots"] for j in js])
    E["mean_nobs300"] = ci([j["acc"]["mean_nobs_300"] / j["acc"]["snapshots"] for j in js])
    E["proto"] = {}
    for p in PROTOS:
        rows = [per_run(j, p) for j in js]
        E["proto"][p] = {k: ci([r[k] for r in rows]) for k in rows[0]}
        # weather: relative change vs clear, per run
        wd = {}
        for w in ("rain", "fog"):
            rw = [per_run(j, p, w) for j in js]
            wd[w] = {"pdr300_rel_change_pct": ci([100 * (b["pdr300"] / a["pdr300"] - 1) for a, b in zip(rows, rw)]),
                     "pdr_own_rel_change_pct": ci([100 * (b["pdr_own"] / a["pdr_own"] - 1) for a, b in zip(rows, rw)]),
                     "pdr_own": ci([b["pdr_own"] for b in rw]), "lat300": ci([b["lat300"] for b in rw])}
        E["proto"][p]["weather"] = wd
        # distance curve
        tx = np.sum([j["acc"][f"{p}|clear|bin_tx"] for j in js], axis=0); rx = np.sum([j["acc"][f"{p}|clear|bin_rx"] for j in js], axis=0)
        E["proto"][p]["pdr_vs_dist"] = [(100 * rx[i] / tx[i] if tx[i] > 0 else None) for i in range(len(tx))]
        # relay
        rel = {"connectable_pct": ci([100 * j["acc"][f"relay|{p}|connectable"] / j["acc"][f"relay|{p}|pairs"] for j in js])}
        for s in STRATS:
            rel[s] = ci([100 * j["acc"][f"relay|{p}|{s}|e2e"] / j["acc"][f"relay|{p}|connectable"] for j in js])
            rel[s + "_lat"] = ci([j["acc"][f"relay|{p}|{s}|lat"] / j["acc"][f"relay|{p}|connectable"] for j in js])
        for base in ("random", "greedy"):
            rel[f"gain_vs_{base}_pct"] = ci([100 * (j["acc"][f"relay|{p}|stability_default|e2e"] / j["acc"][f"relay|{p}|{base}|e2e"] - 1) for j in js])
        rel["share_of_oracle_gain_pct"] = ci([100 * (j["acc"][f"relay|{p}|stability_default|e2e"] - j["acc"][f"relay|{p}|random|e2e"]) /
                                              max(j["acc"][f"relay|{p}|oracle|e2e"] - j["acc"][f"relay|{p}|random|e2e"], 1e-12) for j in js])
        E["proto"][p]["relay"] = rel
    # time series (PDR300 per 10 s window, mean over seeds)
    ts = {}
    for p in PROTOS:
        W = []
        for j in js:
            s = j["series"][p]["clear"]; t = np.array([x[0] for x in s]); rx = np.array([x[1] for x in s]); tx = np.array([x[2] for x in s])
            w = ((t - t.min()) // 10).astype(int)
            W.append([100 * rx[w == i].sum() / max(tx[w == i].sum(), 1) for i in range(w.max() + 1)])
        ts[p] = np.mean(W, axis=0).tolist()
    E["pdr_timeseries_10s"] = ts
json.dump(out, open(os.path.join(R, "summary.json"), "w"), indent=1, default=float)
print("scenarios:", {s: sorted(v) for s, v in out["scenarios"].items()})
