"""Backend shared by BOTH web sites (live replay + analytics).  Every number comes from results/runs/*.json
through metrics.per_run, the same function that produces the paper's tables, so the sites, the paper and
the tests cannot disagree.  Nothing is simulated or randomized here.
"""
import json, os
import numpy as np
import metrics as M
import comm_model as CM

HERE = os.path.dirname(os.path.abspath(__file__))
PROTOS, WEATHERS, SCEN = M.PROTOS, M.WEATHERS, M.SCEN
DENS_NAME = M.DENS                                 # {"2.0": "low", ...}
DENS_PERIOD = {v: k for k, v in DENS_NAME.items()}
SCN_LABEL = {"urban": "Urban grid", "mixed": "Mixed urban-highway", "vile_parle": "Vile Parle (OSM)"}
WARMUP = 60

def _runs(scn, density):
    per = DENS_PERIOD[density]
    js = sorted(M.runs.get((scn, per), []), key=lambda j: j["seed"])
    if not js: raise KeyError(f"no results for {scn}/{density}")
    return js

def meta():
    seeds = sorted({j["seed"] for js in M.runs.values() for j in js})
    sp = {p: {"range_m": s.R, "processing_delay_ms": s.t_proc, "carrier_ghz": s.f, "reliability": s.rel} for p, s in CM.SPECS.items()}
    wc = json.load(open(os.path.join(M.R, "weather_coeffs.json")))
    return {"scenarios": [{"id": s, "label": SCN_LABEL[s]} for s in SCEN], "densities": ["low", "medium", "high"],
            "seeds": seeds, "weathers": WEATHERS, "protocols": PROTOS, "protocol_params": sp, "weather_coeffs": wc,
            "eval_range_m": CM.EVAL_RANGE, "warmup_s": WARMUP, "packet_bytes": CM.PKT_BYTES,
            "model": "Paper Eqs. (1)-(11): FSPL + obstruction + ITU-R weather -> S -> P_rx -> Bernoulli; see cybervanet/comm_model.py",
            "stability_weights": {"v_r": 0.2, "d_s": 0.2, "l_d": 0.3, "d_f": 0.3}}

KEYS = ["pdr300", "pdr_own", "loss300", "lat300", "goodput_mbps", "score", "coverage", "legacy_pdr"]

def metrics(scn, density, weather="clear", seed=None):
    """Per-protocol metrics.  seed=None -> mean +/- 95% CI over seeds (paper tables); seed=k -> that run only."""
    js = _runs(scn, density)
    if seed is not None:
        js = [j for j in js if j["seed"] == int(seed)]
        if not js: raise KeyError(f"seed {seed} not available")
    out = {"scenario": scn, "density": density, "weather": weather, "seed": seed, "n_runs": len(js), "protocols": {}}
    out["mean_active_vehicles"] = float(np.mean([j["acc"]["n_active"] / j["acc"]["snapshots"] for j in js]))
    for p in PROTOS:
        rows = [M.per_run(j, p, weather) for j in js]
        out["protocols"][p] = {k: {"mean": M.ci([r[k] for r in rows])[0], "ci95": M.ci([r[k] for r in rows])[1]} for k in KEYS}
        out["protocols"][p]["range_m"] = CM.SPECS[p].R
        if weather != "clear":
            base = [M.per_run(j, p, "clear") for j in js]
            out["protocols"][p]["pdr300_rel_change_pct"] = {"mean": M.ci([100 * (b["pdr300"] / a["pdr300"] - 1) for a, b in zip(base, rows)])[0],
                                                           "ci95": M.ci([100 * (b["pdr300"] / a["pdr300"] - 1) for a, b in zip(base, rows)])[1]}
        # distance curve (clear weather only is stored)
        if weather == "clear":
            tx = np.sum([j["acc"][f"{p}|clear|bin_tx"] for j in js], axis=0); rx = np.sum([j["acc"][f"{p}|clear|bin_rx"] for j in js], axis=0)
            out["protocols"][p]["pdr_vs_dist"] = [{"d": 25 + 50 * i, "pdr": 100 * rx[i] / tx[i]} for i in range(len(tx)) if tx[i] > 0]
        rel = {"connectable_pct": M.ci([100 * j["acc"][f"relay|{p}|connectable"] / j["acc"][f"relay|{p}|pairs"] for j in js])[0]}
        for s in M.STRATS:
            rel[s] = M.ci([100 * j["acc"][f"relay|{p}|{s}|e2e"] / j["acc"][f"relay|{p}|connectable"] for j in js])[0]
        rel["gain_vs_random_pct"] = M.ci([100 * (j["acc"][f"relay|{p}|stability_default|e2e"] / j["acc"][f"relay|{p}|random|e2e"] - 1) for j in js])[0]
        rel["gain_vs_greedy_pct"] = M.ci([100 * (j["acc"][f"relay|{p}|stability_default|e2e"] / j["acc"][f"relay|{p}|greedy|e2e"] - 1) for j in js])[0]
        out["protocols"][p]["relay"] = rel
    return out

TRACES = os.path.join(HERE, "..", "traces")

def trace_path(scn, density, seed):
    """Locate the SUMO trace of a configuration; generate it with SUMO/TraCI if it is missing and SUMO is installed."""
    f = os.path.join(TRACES, f"{scn}_p{DENS_PERIOD[density]}_s{int(seed)}.npz")
    if not os.path.exists(f):
        import gen_traces
        gen_traces.run(scn, float(DENS_PERIOD[density]), int(seed), TRACES)
    return f

def _num(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else float(x)

def live_events(scn, density, seed, weather="clear"):
    """Generator behind the 'Live Run': executes cybervanet/evaluate.py one SUMO snapshot at a time
    (same code and same random stream as the batch evaluation of the paper) and yields one event per second."""
    import evaluate as EV
    path = trace_path(scn, density, seed)
    total = len(EV.load(path))
    yield {"type": "start", "scenario": scn, "density": density, "seed": int(seed), "weather": weather,
           "duration_s": total, "warmup_s": WARMUP}
    last = None
    for t, S_, acc, series, info in EV.evaluate_iter(path):
        run = {"acc": acc, "series": series}
        ev = {"type": "snap", "t": int(t), "vehicles": [[round(float(r[1])), round(float(r[2])), round(float(r[3]), 1)] for r in S_],
              "info": info, "protocols": {}, "weather_table": {}, "relay": {}}
        with np.errstate(all="ignore"):
            for p in PROTOS:
                m = M.per_run(run, p, weather)
                ser = series[p][weather][-1]
                ev["protocols"][p] = {
                    "pdr": _num(m["pdr300"]), "latency": _num(m["lat300"]), "stability": _num(m["score"]), "goodput_mbps": _num(m["goodput_mbps"]),
                    "pdr_own": _num(m["pdr_own"]), "loss": _num(m["loss300"]),
                    "inst_pdr": _num(100 * ser[1] / max(ser[2], 1)), "inst_latency": _num(ser[4] / max(ser[1], 1)), "inst_stability": _num(ser[5] / max(ser[2], 1)),
                    "tx": int(ser[2]), "rx": int(ser[1])}
                ev["weather_table"][p] = {w: _num(M.per_run(run, p, w)["pdr300"]) for w in WEATHERS}
                k = f"relay|{p}|"
                if acc.get(k + "connectable", 0) > 0:
                    c = acc[k + "connectable"]
                    ev["relay"][p] = {s: _num(100 * acc[f"{k}{s}|e2e"] / c) for s in ("random", "greedy", "stability_default", "oracle")}
        last = run
        yield ev
    # final comparison with the stored run behind the paper (identical by construction; reported, not assumed)
    ref = metrics(scn, density, weather, seed); worst = 0.0
    with np.errstate(all="ignore"):
        for p in PROTOS:
            m = M.per_run(last, p, weather)
            for key in ("pdr300", "lat300", "score", "goodput_mbps", "pdr_own"):
                worst = max(worst, abs(m[key] - ref["protocols"][p][key]["mean"]))
    yield {"type": "done", "max_abs_difference_vs_paper_run": float(worst), "identical": bool(worst < 1e-9),
           "final": {p: {k: _num(M.per_run(last, p, weather)[k]) for k in ("pdr300", "lat300", "score", "goodput_mbps", "pdr_own")} for p in PROTOS}}

def explain(d, n_obs, n_loc, v, weather="clear"):
    return {p: CM.explain_link(CM.SPECS[p], d, n_obs, n_loc, v, weather) for p in PROTOS}
