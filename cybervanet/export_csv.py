"""Export telemetry as CSV (paper Sec. III-E: per-run PDR, latency, goodput, packet loss and stability score).

Two files, both derived from results/runs/*.json through metrics.per_run, the same function behind the paper tables:
  results/telemetry_runs.csv     one row per (scenario, density, seed, protocol, weather)
  results/telemetry_summary.csv  mean and 95% CI over seeds for each (scenario, density, protocol, weather)

Usage: python export_csv.py        (the web console serves the same content at /api/export.csv?kind=runs|summary)
"""
import csv, io, os
import metrics as M

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "results")
DENS_ORDER = ["low", "medium", "high"]
DENS_PERIOD = {v: k for k, v in M.DENS.items()}
METRICS = [("pdr300", "pdr300_pct"), ("pdr_own", "pdr_own_pct"), ("loss300", "packet_loss300_pct"),
           ("lat300", "latency300_ms"), ("goodput_mbps", "goodput_mbps"), ("score", "stability_score")]


def _cells():
    for scn in M.SCEN:
        for dens in DENS_ORDER:
            js = sorted(M.runs.get((scn, DENS_PERIOD[dens]), []), key=lambda j: j["seed"])
            if js:
                yield scn, dens, js


def _fmt(x):
    return f"{float(x):.6f}"


def runs_rows():
    yield ["scenario", "density", "seed", "protocol", "weather"] + [c for _, c in METRICS]
    for scn, dens, js in _cells():
        for j in js:
            for p in M.PROTOS:
                for w in M.WEATHERS:
                    r = M.per_run(j, p, w)
                    yield [scn, dens, j["seed"], p, w] + [_fmt(r[k]) for k, _ in METRICS]


def summary_rows():
    yield ["scenario", "density", "protocol", "weather", "n_seeds"] + [f"{c}_{s}" for _, c in METRICS for s in ("mean", "ci95")]
    for scn, dens, js in _cells():
        for p in M.PROTOS:
            for w in M.WEATHERS:
                rows = [M.per_run(j, p, w) for j in js]
                vals = []
                for k, _ in METRICS:
                    m, c = M.ci([r[k] for r in rows]); vals += [_fmt(m), _fmt(c)]
                yield [scn, dens, p, w, len(js)] + vals


def _text(rows):
    buf = io.StringIO(); csv.writer(buf, lineterminator="\n").writerows(rows); return buf.getvalue()


def runs_csv(): return _text(runs_rows())
def summary_csv(): return _text(summary_rows())


def write(out_dir=OUT):
    os.makedirs(out_dir, exist_ok=True)
    for name, text in (("telemetry_runs.csv", runs_csv()), ("telemetry_summary.csv", summary_csv())):
        with open(os.path.join(out_dir, name), "w", newline="") as f: f.write(text)
        print("wrote", os.path.join("results", name), text.count("\n") - 1, "rows")


if __name__ == "__main__":
    write()
