"""CyberVANET web console: ONE Flask app, ONE backend (cybervanet/core.py), two sites:

    /            LIVE RUN: executes the paper's model second by second on a SUMO trace (map, telemetry, relay, formulas)
    /analytics   aggregated results (6 seeds, 95% CI), density / weather / relay / distance charts
    /formulas    step-by-step evaluation of Eqs. (2)-(8) and (11) for any link

Both sites read the same /api/* endpoints, which read results/runs/*.json through metrics.per_run,
the function that also generates the paper's tables.  python main.py site  ->  http://127.0.0.1:5000
"""
import os, sys, json, time
from flask import Flask, jsonify, request, render_template, Response, stream_with_context
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "cybervanet"))
import core

app = Flask(__name__, template_folder=os.path.join(HERE, "templates"), static_folder=os.path.join(HERE, "static"))

def _args():
    seed = request.args.get("seed", "mean")
    return (request.args.get("scenario", "vile_parle"), request.args.get("density", "medium"),
            request.args.get("weather", "clear"), None if seed in ("mean", "", None) else int(seed))

@app.errorhandler(KeyError)
def _nf(e): return jsonify(error=str(e)), 404

@app.errorhandler(RuntimeError)
def _rt(e): return jsonify(error=str(e)), 500

@app.after_request
def _cors(r):
    r.headers["Access-Control-Allow-Origin"] = "*"; r.headers["Cache-Control"] = "no-store"; return r

@app.route("/")
def live(): return render_template("live.html", page="live")
@app.route("/analytics")
def analytics(): return render_template("analytics.html", page="analytics")
@app.route("/formulas")
def formulas(): return render_template("formulas.html", page="formulas")

@app.route("/api/live")
def api_live():
    """Server-sent events: one JSON event per simulated second (see core.live_events)."""
    scn, den, w, seed = _args()
    seed = 1 if seed is None else seed
    speed = max(0.5, float(request.args.get("speed", 5)))
    if scn not in core.SCEN or den not in ("low", "medium", "high") or w not in core.WEATHERS:
        return jsonify(error="bad scenario/density/weather"), 400
    def gen():
        try:
            for ev in core.live_events(scn, den, seed, w):
                t0 = time.time()
                yield "data: " + json.dumps(ev, separators=(",", ":")) + "\n\n"
                if ev["type"] == "snap" and speed < 1000:
                    time.sleep(max(0.0, 1.0 / speed - 0.0))
        except Exception as e:
            yield "data: " + json.dumps({"type": "error", "message": str(e)}) + "\n\n"
    return Response(stream_with_context(gen()), mimetype="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})

@app.route("/api/explain")
def api_explain():
    a = request.args
    return jsonify(core.explain(float(a.get("d", 150)), int(float(a.get("n_obs", 0))), float(a.get("n_loc", 50)), float(a.get("v", 40)), a.get("weather", "clear")))

@app.route("/api/health")
def health(): return jsonify(status="ok", backend="cybervanet/core.py", data="results/runs/*.json")
@app.route("/api/meta")
def meta(): return jsonify(core.meta())
@app.route("/api/metrics")
def metrics():
    s, d, w, k = _args(); return jsonify(core.metrics(s, d, w, k))
@app.route("/api/series")
def series():
    s, d, w, k = _args(); return jsonify(core.run_series(s, d, w, k))
@app.route("/api/density")
def density():
    """PDR/latency/goodput of one scenario across the three densities (for the density chart)."""
    s, _, w, k = _args()
    return jsonify({dn: core.metrics(s, dn, w, k) for dn in ("low", "medium", "high")})
@app.route("/api/consistency")
def consistency():
    """Compare what the sites serve with results/summary.json (the file the paper tables are generated from)."""
    S = json.load(open(os.path.join(core.M.R, "summary.json")))["scenarios"]
    worst = 0.0; cells = 0
    for s in core.SCEN:
        for d in ("low", "medium", "high"):
            m = core.metrics(s, d)
            for p in core.PROTOS:
                for key, sk in (("pdr300", "pdr300"), ("lat300", "lat300"), ("goodput_mbps", "goodput_mbps"), ("score", "score")):
                    worst = max(worst, abs(m["protocols"][p][key]["mean"] - S[s][d]["proto"][p][sk][0])); cells += 1
    return jsonify(checked_values=cells, max_abs_difference=worst, consistent=worst < 1e-9)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5002)))
