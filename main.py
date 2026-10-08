#!/usr/bin/env python3
"""CyberVANET command line.   python main.py <command>

  scenarios   rebuild urban + mixed SUMO networks (needs SUMO on PATH; pip install eclipse-sumo)
  traces      generate the 54 mobility traces (3 scenarios x 3 densities x 6 seeds) with SUMO/TraCI
  evaluate    run the communication model on every trace  -> results/runs/*.json
  aggregate   mean +/- 95% CI over seeds                  -> results/summary.json
  figures     paper figures                               -> figs/ and tex/
  tables      LaTeX macros and tables                     -> tex/numbers.tex, tex/tab_*.tex
  verify      assert every claim made in the paper against results/summary.json
  paper       compile tex/main.pdf (needs pdflatex, bibtex, IEEEtran)
  site        serve BOTH web sites (live replay + analytics) from one backend at http://127.0.0.1:5002
  all         traces + evaluate + aggregate + figures + tables + verify (hours on 2 cores)
  quick       smoke test: 1 scenario, medium density, 2 seeds, into a temp dir (about 3 minutes)
Options: -j N  parallel workers (default: CPU count)
"""
import os, sys, subprocess, itertools, glob, tempfile, shutil, argparse, multiprocessing as mp

ROOT = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(ROOT, "cybervanet")
SCEN = ["urban", "mixed", "vile_parle"]
PERIODS = ["2.0", "1.0", "0.5"]       # low / medium / high density (seconds between inserted vehicles)
SEEDS = [1, 2, 3, 4, 5, 6]


def py(script, *args, cwd=PKG):
    subprocess.run([sys.executable, os.path.join(PKG, script), *map(str, args)], check=True, cwd=cwd)


def _trace(a):
    scn, per, seed, out = a
    py("gen_traces.py", scn, per, seed, out); return a


def _eval(a):
    tr, out = a
    py("evaluate.py", tr, out); return a


def jobs(scns=SCEN, pers=PERIODS, seeds=SEEDS):
    return [(s, p, k) for s in scns for p in pers for k in seeds]


def do_traces(n, scns=SCEN, pers=PERIODS, seeds=SEEDS, out=None):
    out = out or os.path.join(ROOT, "traces")
    todo = [(s, p, k, out) for s, p, k in jobs(scns, pers, seeds) if not os.path.exists(os.path.join(out, f"{s}_p{p}_s{k}.npz"))]
    with mp.Pool(n) as pool:
        for a in pool.imap_unordered(_trace, todo): print("trace", a[:3], flush=True)


def do_evaluate(n, scns=SCEN, pers=PERIODS, seeds=SEEDS, tdir=None, rdir=None):
    tdir = tdir or os.path.join(ROOT, "traces"); rdir = rdir or os.path.join(ROOT, "results", "runs")
    os.makedirs(rdir, exist_ok=True)
    todo = [(os.path.join(tdir, f"{s}_p{p}_s{k}.npz"), os.path.join(rdir, f"{s}_p{p}_s{k}.json")) for s, p, k in jobs(scns, pers, seeds)]
    todo = [t for t in todo if os.path.exists(t[0])]
    with mp.Pool(n) as pool:
        for a in pool.imap_unordered(_eval, todo): print("eval", os.path.basename(a[1]), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices="scenarios traces evaluate aggregate figures tables verify paper site all quick".split())
    ap.add_argument("-j", type=int, default=os.cpu_count() or 1)
    a = ap.parse_args()
    c = a.cmd
    if c == "scenarios": py("build_scenarios.py"); py("scenario_stats.py")
    elif c == "traces": do_traces(a.j)
    elif c == "evaluate": do_evaluate(a.j)
    elif c == "aggregate": py("aggregate.py")
    elif c == "figures": py("make_figures.py")
    elif c == "tables": py("make_tex_data.py")
    elif c == "verify": py("verify_claims.py")
    elif c == "paper":
        t = os.path.join(ROOT, "tex")
        for cmd in (["pdflatex", "-interaction=nonstopmode", "main.tex"], ["bibtex", "main"],
                    ["pdflatex", "-interaction=nonstopmode", "main.tex"], ["pdflatex", "-interaction=nonstopmode", "main.tex"]):
            subprocess.run(cmd, cwd=t, check=bool(cmd[0] == "bibtex"), stdout=subprocess.DEVNULL)
        print("wrote tex/main.pdf")
    elif c == "site": subprocess.run([sys.executable, os.path.join(ROOT, "site", "app.py")], check=True)
    elif c == "all":
        py("weather_coeffs.py"); py("scenario_stats.py")
        do_traces(a.j); do_evaluate(a.j); py("aggregate.py"); py("make_figures.py"); py("make_tex_data.py"); py("verify_claims.py")
    elif c == "quick":
        tmp = tempfile.mkdtemp(prefix="cybervanet_quick_")
        do_traces(a.j, ["urban"], ["1.0"], [1, 2], os.path.join(tmp, "traces"))
        do_evaluate(a.j, ["urban"], ["1.0"], [1, 2], os.path.join(tmp, "traces"), os.path.join(tmp, "runs"))
        import json
        for f in sorted(glob.glob(os.path.join(tmp, "runs", "*.json"))):
            acc = json.load(open(f))["acc"]
            print(os.path.basename(f), {p: round(100 * acc[f"{p}|clear|rx300"] / acc[f"{p}|clear|tx300"], 1) for p in ("DSRC", "C-V2X", "5G-V2X")})
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
