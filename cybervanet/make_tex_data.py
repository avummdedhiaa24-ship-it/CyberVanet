"""Create numbers.tex (macros) and tables.tex from results so that no number in the paper is typed by hand."""
import json, os, glob, re
import numpy as np
import aggregate as AG   # re-runs aggregation, exposes per_run / ci / runs

HERE = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(HERE, "..", "results"); T = os.path.join(HERE, "..", "tex")
S = json.load(open(os.path.join(R, "summary.json")))["scenarios"]
WC = json.load(open(os.path.join(R, "weather_coeffs.json")))
ST = json.load(open(os.path.join(R, "scenario_stats.json")))
PROTOS = ["DSRC", "C-V2X", "5G-V2X"]; PN = {"DSRC": "Dsrc", "C-V2X": "Cvx", "5G-V2X": "Gv"}
SCN = {"urban": "Urban grid", "mixed": "Mixed urban-highway", "vile_parle": "Vile Parle (OSM)"}; SN = {"urban": "U", "mixed": "M", "vile_parle": "V"}
DN = {"low": "Low", "medium": "Med", "high": "High"}
M = {}
def put(name, val, nd=1):
    v = (f"{val:.{nd}f}" if not isinstance(val, str) else val)
    if v.startswith("-") and float(v) == 0: v = v[1:]
    M[name] = v

def f1(t, nd=1):
    a = f"{t[0]:.{nd}f}"
    a = "$-$" + a[1:] if a.startswith("-") else a
    return f"{a}$\\pm${t[1]:.{nd}f}"

# --- per scenario / density / protocol macros
for scn in SCN:
    for d in S[scn]:
        E = S[scn][d]
        put(f"act{SN[scn]}{DN[d]}", E["mean_active"][0], 0); put(f"nloc{SN[scn]}{DN[d]}", E["mean_nloc"][0], 0); put(f"nobs{SN[scn]}{DN[d]}", E["mean_nobs300"][0], 2)
        for p in PROTOS:
            P = E["proto"][p]; k = f"{SN[scn]}{DN[d]}{PN[p]}"
            put("pdrThree" + k, P["pdr300"][0]); put("pdrOwn" + k, P["pdr_own"][0]); put("lat" + k, P["lat300"][0]); put("gp" + k, P["goodput_mbps"][0], 2)
            put("cov" + k, P["coverage"][0]); put("pair" + k, P["legacy_pdr"][0], 2); put("score" + k, P["score"][0])
            R_ = P["relay"]
            for s in ("random", "greedy", "stability_default", "oracle"): put("rel" + s.replace("_", "") + k, R_[s][0], 2)
            put("gainRand" + k, R_["gain_vs_random_pct"][0]); put("gainGreedy" + k, R_["gain_vs_greedy_pct"][0]); put("share" + k, R_["share_of_oracle_gain_pct"][0], 0)
            put("conn" + k, R_["connectable_pct"][0], 0)
            for wn in ("equal", "delivery_heavy"):
                put(f"gain{wn.replace('_','')}Rand" + k, 100 * (R_["stability_" + wn][0] / R_["random"][0] - 1))
# --- ranges across all nine scenario/density cells
for p in PROTOS:
    v = [S[s][d]["proto"][p]["pdr300"][0] for s in S for d in S[s]]; put("pdrMin" + PN[p], min(v)); put("pdrMax" + PN[p], max(v))
    v = [S[s][d]["proto"][p]["lat300"][0] for s in S for d in S[s]]; put("latMin" + PN[p], min(v), 2); put("latMax" + PN[p], max(v), 2)
    g = [S[s][d]["proto"][p]["relay"]["gain_vs_random_pct"][0] for s in S for d in S[s]]; put("gainMin" + PN[p], min(g)); put("gainMax" + PN[p], max(g))
    gg = [S[s][d]["proto"][p]["relay"]["gain_vs_greedy_pct"][0] for s in S for d in S[s]]; put("gainGMin" + PN[p], min(gg)); put("gainGMax" + PN[p], max(gg))
    # density sensitivity (low -> high), pp change per scenario
    for s in S:
        put(f"drop{SN[s]}{PN[p]}", S[s]["low"]["proto"][p]["pdr300"][0] - S[s]["high"]["proto"][p]["pdr300"][0])
        put(f"gpHigh{SN[s]}{PN[p]}", S[s]["high"]["proto"][p]["goodput_mbps"][0], 1)
    allgp = [S[s]["high"]["proto"][p]["goodput_mbps"][0] for s in S]
# weather, pooled over the three scenarios at medium density (18 runs)
W = {}
for p in PROTOS:
    for w in ("rain", "fog"):
        vals = []; vals300 = []
        for scn in SCN:
            js = AG.runs[(scn, "1.0")]
            for j in js:
                a = AG.per_run(j, p); b = AG.per_run(j, p, w)
                vals.append(100 * (b["pdr_own"] / a["pdr_own"] - 1)); vals300.append(100 * (b["pdr300"] / a["pdr300"] - 1))
        W[(p, w)] = (AG.ci(vals), AG.ci(vals300))
        put(f"w{w}{PN[p]}", W[(p, w)][0][0], 2); put(f"w{w}{PN[p]}ci", W[(p, w)][0][1], 2)
        put(f"w{w}Three{PN[p]}", W[(p, w)][1][0], 2); put(f"w{w}Three{PN[p]}ci", W[(p, w)][1][1], 2)
for f_ in ("5.9", "28.0"):
    g = WC["gamma_db_per_km"][f_]; tag = "Low" if f_ == "5.9" else "High"
    put("gammaRain" + tag, g["rain"], 2); put("gammaFog" + tag, g["fog"], 3); put("Kl" + tag, g["Kl"], 3)
put("rainRate", WC["rain_rate_mm_h"], 0); put("fogM", WC["fog_liquid_water_g_m3"], 1)
# mean speed (stored by scenario_stats.py from the medium-density traces, t>=60)
for scn in SCN:
    put("speed" + SN[scn], float(ST[scn]["mean_speed_kmh"]), 0)
    for k, v in ST[scn].items():
        if isinstance(v, (int, float)): put(f"net{SN[scn]}{k.replace('_','').replace('m','M',1) if False else ''}" + k.replace("_", "").title().replace("Km", "Km"), v, 0 if k != "road_km" else 1)
import numpy as _np, comm_model as _cm
for p in PROTOS:
    pp, _, _ = _cm.link_model(_cm.SPECS[p], _np.array([10.0]), _np.array([0]), _np.array([0.0]), _np.array([0.0]))
    put("ceil" + PN[p], 100 * float(pp[0]), 0)
    SS = _cm.link_model(_cm.SPECS[p], _np.array([10.0]), _np.array([0]), _np.array([0.0]), _np.array([0.0]))[1]
    put("sigTen" + PN[p], float(SS[0]), 2)
n_seeds = S["urban"]["medium"]["n_seeds"]; put("nSeeds", n_seeds, 0)
cn = [S[s_][d]["proto"][p]["relay"]["connectable_pct"][0] for s_ in S for d in S[s_] for p in PROTOS]
put("connMin", min(cn), 0); put("connMax", max(cn), 0)
_wm = []; _wz = 0
for s_ in S:
    for d in S[s_]:
        for p in ("DSRC", "C-V2X"):
            for w in ("rain", "fog"):
                for k in ("pdr300_rel_change_pct", "pdr_own_rel_change_pct"):
                    m_, c_ = S[s_][d]["proto"][p]["weather"][w][k]; _wm.append(abs(m_)); _wz += abs(m_) <= c_
put("wxLowMax", max(_wm), 1); put("wxLowZero", _wz, 0); put("wxLowN", len(_wm), 0)
open(os.path.join(T, "numbers.tex"), "w").write("".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in M.items()))

# ---------------- table fragments
def w_(name, txt): open(os.path.join(T, name), "w").write(txt)
rows = []
for scn in SCN:
    st = ST[scn]
    rows.append(f"{SCN[scn]} & {st['width_m']}$\\times${st['height_m']} & {st['road_km']:.1f} & {st['junctions']} & "
                f"{S[scn]['low']['mean_active'][0]:.0f}/{S[scn]['medium']['mean_active'][0]:.0f}/{S[scn]['high']['mean_active'][0]:.0f} & {M['speed'+SN[scn]]} \\\\")
w_("tab_scenarios.tex", r"""\begin{table}[t]
\caption{Simulation Scenarios (L/M/H: Low/Medium/High Density, Time-Averaged Vehicle Counts After Warm-up; km/h: Mean Vehicle Speed)}
\label{tab:scenarios}
\centering\footnotesize
\setlength{\tabcolsep}{2pt}
\begin{tabular}{@{}lccccc@{}}
\toprule
Scenario & Area (m) & Roads (km) & Junct. & Veh. (L/M/H) & km/h \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table}
""")
E = S["vile_parle"]["medium"]["proto"]
w_("tab_pdrdef.tex", r"""\begin{table}[t]
\caption{Effect of the PDR Definition (Vile Parle, Medium Density, Clear Weather; Values in \%, Mean $\pm$ 95\% CI)}
\label{tab:pdrdef}
\centering\footnotesize
\setlength{\tabcolsep}{2pt}
\begin{tabular}{@{}lcccc@{}}
\toprule
Protocol & Pair cov. & Pair PDR & Neighbor PDR & PDR$_{300}$ \\
\midrule
""" + "\n".join(f"{p} & {f1(E[p]['coverage'])} & {f1(E[p]['legacy_pdr'],2)} & {f1(E[p]['pdr_own'])} & {f1(E[p]['pdr300'])} \\\\" for p in PROTOS) + r"""
\bottomrule
\end{tabular}
\end{table}
""")
L = [r"""\begin{table*}[t]
\caption{Performance Summary at Medium Traffic Density, Clear Weather (Mean $\pm$ 95\% CI over \nSeeds{} Seeds). PDR$_{300}$ and Latency Use the Common 300~m Link Set; Goodput Uses Each Protocol's Own Range}
\label{tab:main}
\centering\footnotesize
\begin{tabular}{@{}llccccc@{}}
\toprule
Scenario & Protocol & PDR$_{300}$ (\%) & Packet loss$_{300}$ (\%) & Latency (ms) & Goodput (Mbit/s) & Stability score \\
\midrule"""]
for i, scn in enumerate(SCN):
    for j, p in enumerate(PROTOS):
        P = S[scn]["medium"]["proto"][p]
        L.append(f"{SCN[scn] if j == 0 else ''} & {p} & {f1(P['pdr300'])} & {f1(P['loss300'])} & {f1(P['lat300'],2)} & {f1(P['goodput_mbps'],2)} & {f1(P['score'])} \\\\")
    if i < 2: L.append(r"\midrule")
L.append(r"""\bottomrule
\end{tabular}
\end{table*}
""")
w_("tab_main.tex", "\n".join(L))
L = [r"""\begin{table}[t]
\caption{Relative Change of PDR With Respect to Clear Weather at Medium Density, Pooled Over the Three Scenarios (Mean $\pm$ 95\% CI over 18 Runs)}
\label{tab:weather}
\centering\footnotesize
\begin{tabular}{@{}lcccc@{}}
\toprule
& \multicolumn{2}{c}{Own range (\%)} & \multicolumn{2}{c}{Within 300~m (\%)} \\
\cmidrule(lr){2-3}\cmidrule(lr){4-5}
Protocol & Rain & Fog & Rain & Fog \\
\midrule"""]
for p in PROTOS:
    L.append(f"{p} & {f1(W[(p,'rain')][0],2)} & {f1(W[(p,'fog')][0],2)} & {f1(W[(p,'rain')][1],2)} & {f1(W[(p,'fog')][1],2)} \\\\")
L.append(r"""\bottomrule
\end{tabular}
\end{table}
""")
w_("tab_weather.tex", "\n".join(L))
print(len(M), "macros; tables ok")
