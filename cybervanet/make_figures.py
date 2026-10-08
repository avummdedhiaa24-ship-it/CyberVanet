import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
F = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "figs")
S = json.load(open(os.path.join(R, "summary.json")))["scenarios"]
PROTOS = ["DSRC", "C-V2X", "5G-V2X"]
COL = {"DSRC": "#0072B2", "C-V2X": "#D55E00", "5G-V2X": "#009E73"}
MRK = {"DSRC": "o", "C-V2X": "s", "5G-V2X": "^"}
SCN = {"urban": "Urban grid", "mixed": "Mixed urban-highway", "vile_parle": "Vile Parle (OSM)"}
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],
                     "font.size": 8, "axes.labelsize": 8, "legend.fontsize": 7, "xtick.labelsize": 7, "ytick.labelsize": 7,
                     "axes.linewidth": 0.6, "pdf.fonttype": 42, "axes.grid": True, "grid.alpha": 0.3, "grid.linewidth": 0.4})

# Fig. 2: PDR versus distance (Vile Parle, medium density, clear weather)
fig, ax = plt.subplots(figsize=(3.4, 2.35))
for p in PROTOS:
    y = S["vile_parle"]["medium"]["proto"][p]["pdr_vs_dist"]
    x = [25 + 50 * i for i, v in enumerate(y) if v is not None]; yy = [v for v in y if v is not None]
    ax.plot(x, yy, marker=MRK[p], ms=3, lw=1, color=COL[p], label=p)
ax.axvline(300, color="gray", ls=":", lw=0.8); ax.text(310, ax.get_ylim()[1] * 0.93, "300 m evaluation range", fontsize=6, color="gray")
ax.set_xlabel("Transmitter-receiver distance (m)"); ax.set_ylabel("PDR (%)"); ax.set_xlim(0, 1000); ax.set_ylim(bottom=0)
ax.legend(frameon=False, loc="upper right", bbox_to_anchor=(1.0, 0.85))
fig.tight_layout(pad=0.4); fig.savefig(os.path.join(F, "fig_pdr_distance.pdf")); plt.close(fig)

# Fig. 3: PDR within 300 m versus traffic density
fig, axs = plt.subplots(1, 3, figsize=(7.1, 2.2), sharey=True)
for ax, scn in zip(axs, SCN):
    for p in PROTOS:
        xs, ys, es = [], [], []
        for d in ("low", "medium", "high"):
            E = S[scn][d]; xs.append(E["mean_active"][0]); ys.append(E["proto"][p]["pdr300"][0]); es.append(E["proto"][p]["pdr300"][1])
        ax.errorbar(xs, ys, yerr=es, marker=MRK[p], ms=3.5, lw=1, capsize=2, color=COL[p], label=p)
    ax.set_title(f"({'abc'[list(SCN).index(scn)]}) {SCN[scn]}", fontsize=8); ax.set_xlabel("Mean active vehicles")
axs[0].set_ylabel("PDR within 300 m (%)"); axs[0].legend(frameon=False, loc="lower left")
axs[0].set_ylim(0, 40)
fig.tight_layout(pad=0.4); fig.savefig(os.path.join(F, "fig_density.pdf")); plt.close(fig)

# Fig. 4: relay selection, relative gain over random selection (Vile Parle + mixed shown for all densities)
fig, axs = plt.subplots(1, 2, figsize=(3.45, 2.3), sharey=True)
for ax, scn in zip(axs, ("urban", "vile_parle")):
    w = 0.26
    for i, p in enumerate(PROTOS):
        g = [S[scn][d]["proto"][p]["relay"]["gain_vs_random_pct"] for d in ("low", "medium", "high")]
        ax.bar(np.arange(3) + (i - 1) * w, [x[0] for x in g], w, yerr=[x[1] for x in g], capsize=1.5, color=COL[p], label=p, error_kw={"lw": 0.6})
    ax.set_xticks(range(3)); ax.set_xticklabels(["low", "med.", "high"]); ax.set_title(f"({'ab'[('urban','vile_parle').index(scn)]}) {SCN[scn]}", fontsize=7.5)
    ax.set_xlabel("Traffic density")
axs[0].set_ylabel("Delivery gain over random relay (%)"); axs[0].legend(frameon=False, loc="upper left")
fig.tight_layout(pad=0.4); fig.savefig(os.path.join(F, "fig_relay.pdf")); plt.close(fig)
print("figures ok")
