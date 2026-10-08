"""Evaluate the revised communication model on one SUMO trace.
Usage: python evaluate.py <trace.npz> <out.json>
"""
import sys, os, json, re
import numpy as np
from comm_model import *

WEATHERS = ["clear", "rain", "fog"]
BINS = np.arange(0, 1050, 50)
WARMUP = 60            # s, discard initial fill-up transient
WSETS = {"default": (0.2, 0.2, 0.3, 0.3), "equal": (0.25, 0.25, 0.25, 0.25), "delivery_heavy": (0.1, 0.1, 0.2, 0.6)}
N_RELAY_PAIRS = 40

def load(path):
    z = np.load(path); flat, lens = z["flat"], z["lens"]
    off = np.concatenate([[0], np.cumsum(lens)])
    return [flat[off[i]:off[i + 1]] for i in range(len(lens))]

def evaluate_iter(path):
    """Generator: processes one SUMO snapshot per iteration and yields (t, snapshot_array, acc, series, info).
    evaluate() below simply runs it to the end, and the live web run consumes it step by step, so a live run
    executes exactly the same code (and the same random stream) as the batch evaluation behind the paper."""
    seed = int(re.search(r"_s(\d+)\.npz", path).group(1))
    rng = np.random.default_rng(1000 + seed)
    snaps = load(path)
    acc = {}
    def A(key, shape=()):
        return acc.setdefault(key, np.zeros(shape))
    series = {p: {w: [] for w in WEATHERS} for p in SPECS}
    for t, S_ in enumerate(snaps):
        n = len(S_)
        if t < WARMUP or n < 2:
            continue
        pos = S_[:, 1:3]; spd = S_[:, 3]
        D = np.sqrt(((pos[:, None, :] - pos[None, :, :]) ** 2).sum(-1))
        np.fill_diagonal(D, np.inf)
        nloc = (D <= CTX_RANGE).sum(0).astype(float)           # per receiver (column j)
        iu, ju = np.triu_indices(n, 1)
        sel = D[iu, ju] <= 1000.0
        I, J = iu[sel], ju[sel]
        nobs = count_obstructions(pos, I, J) if len(I) else np.zeros(0, dtype=int)
        # directed link arrays (sender -> receiver)
        Id = np.concatenate([I, J]); Jd = np.concatenate([J, I]); ob = np.concatenate([nobs, nobs])
        d = D[Id, Jd]; nl = nloc[Jd]; v = 0.5 * (spd[Id] + spd[Jd]) * 3.6
        _m3 = d <= 300
        info = {"n": int(n), "links300": int(_m3.sum()),
                "mean_d300": float(d[_m3].mean()) if _m3.any() else 0.0, "mean_obs300": float(ob[_m3].mean()) if _m3.any() else 0.0,
                "mean_nloc300": float(nl[_m3].mean()) if _m3.any() else 0.0, "mean_v300": float(v[_m3].mean()) if _m3.any() else 0.0}
        A("snapshots"); acc["snapshots"] += 1
        A("n_active"); acc["n_active"] += n
        A("ordered_pairs"); acc["ordered_pairs"] += n * (n - 1)
        A("mean_nloc"); acc["mean_nloc"] += nloc.mean()
        A("mean_nobs_300"); m3 = d <= 300
        acc["mean_nobs_300"] += ob[m3].mean() if m3.any() else 0
        for pname, spec in SPECS.items():
            for w in WEATHERS:
                p, Ssig, lat = link_model(spec, d, ob, nl, v, w)
                u = rng.random(len(p)) < p
                m300 = d <= EVAL_RANGE; mown = d <= spec.R
                k = f"{pname}|{w}|"
                A(k + "tx300"); acc[k + "tx300"] += m300.sum()
                A(k + "rx300"); acc[k + "rx300"] += (u & m300).sum()
                A(k + "txown"); acc[k + "txown"] += mown.sum()
                A(k + "rxown"); acc[k + "rxown"] += (u & mown).sum()
                A(k + "lat300"); acc[k + "lat300"] += lat[u & m300].sum()
                A(k + "lat300sq"); acc[k + "lat300sq"] += (lat[u & m300] ** 2).sum()
                A(k + "latown"); acc[k + "latown"] += lat[u & mown].sum()
                tm = build_terms = None
                terms = stability_terms(spec, d, nl, lat, p)
                sc = stability_score(terms)
                A(k + "score300"); acc[k + "score300"] += sc[m300].sum()
                A(k + "score300_n"); acc[k + "score300_n"] += m300.sum()
                # distance-binned counts (own range)
                bi = np.minimum((d // 50).astype(int), len(BINS) - 1)
                A(k + "bin_tx", len(BINS)); A(k + "bin_rx", len(BINS))
                acc[k + "bin_tx"] += np.bincount(bi[mown], minlength=len(BINS))
                acc[k + "bin_rx"] += np.bincount(bi[u & mown], minlength=len(BINS))
                series[pname][w].append((t, int((u & m300).sum()), int(m300.sum()), int((u & mown).sum()), float(lat[u & m300].sum()), float(sc[m300].sum()), n))
                if w == "clear":
                    # keep matrices for relay experiment
                    if pname == "DSRC" and "mats" not in locals():
                        pass
            # ---- relay experiment (clear weather) ----
            p, Ssig, lat = link_model(spec, d, ob, nl, v, "clear")
            terms = stability_terms(spec, d, nl, lat, p)
            Pm = np.zeros((n, n)); Lm = np.zeros((n, n)); Dm = D
            Pm[Id, Jd] = p; Lm[Id, Jd] = lat
            Sc = {}
            for wn, w_ in WSETS.items():
                M = np.zeros((n, n)); M[Id, Jd] = stability_score(terms, w_); Sc[wn] = M
            relay_snapshot(acc, pname, Pm, Lm, Sc, D, rng)
        yield t, S_, acc, series, info
    return

def evaluate(path):
    seed = int(re.search(r"_s(\d+)\.npz", path).group(1))
    acc = series = None
    for _t, _S, acc, series, _info in evaluate_iter(path):
        pass
    return acc, series, seed

def relay_snapshot(acc, pname, Pm, Lm, Sc, D, rng):
    n = len(D)
    cand_pairs = np.argwhere((D > EVAL_RANGE) & (D <= 550.0))
    if len(cand_pairs) == 0:
        return
    if len(cand_pairs) > N_RELAY_PAIRS:
        cand_pairs = cand_pairs[rng.choice(len(cand_pairs), N_RELAY_PAIRS, replace=False)]
    link = (D <= EVAL_RANGE)
    for s, t in cand_pairs:
        ks = np.where(link[s] & link[:, t])[0]
        ks = ks[(ks != s) & (ks != t)]
        key = f"relay|{pname}|"
        acc.setdefault(key + "pairs", 0.0); acc[key + "pairs"] += 1
        if len(ks) == 0:
            continue
        acc.setdefault(key + "connectable", 0.0); acc[key + "connectable"] += 1
        e2e = Pm[s, ks] * Pm[ks, t]; lat2 = Lm[s, ks] + Lm[ks, t]
        picks = {
            "random": (e2e.mean(), lat2.mean()),
            "greedy": (e2e[np.argmin(D[ks, t])], lat2[np.argmin(D[ks, t])]),
            "oracle": (e2e.max(), lat2[np.argmax(e2e)]),
        }
        for wn, M in Sc.items():
            b = np.minimum(M[s, ks], M[ks, t]); j = np.argmax(b)
            picks["stability_" + wn] = (e2e[j], lat2[j])
        for name, (e, l) in picks.items():
            for suffix, val in (("e2e", e), ("lat", l)):
                kk = key + name + "|" + suffix
                acc.setdefault(kk, 0.0); acc[kk] += val

if __name__ == "__main__":
    path, out = sys.argv[1], sys.argv[2]
    acc, series, seed = evaluate(path)
    json.dump({"trace": os.path.basename(path), "seed": seed,
               "acc": {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in acc.items()},
               "series": series}, open(out, "w"))
    print("ok", out, int(acc["snapshots"]), "snaps; mean active", round(acc["n_active"] / acc["snapshots"], 1))
