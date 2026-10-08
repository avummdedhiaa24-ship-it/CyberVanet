import os, json, glob
import numpy as np, sumolib
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scenarios")
out = {}
for k, f in (("urban", "urban.net.xml"), ("mixed", "mixed.net.xml"), ("vile_parle", "vile_parle.net.xml")):
    net = sumolib.net.readNet(os.path.join(S, f), withInternal=False)
    edges = [e for e in net.getEdges() if e.getFunction() == ""]
    (x0, y0, x1, y1) = net.getBoundary()
    L = sum(e.getLength() for e in edges) / 1000.0
    nodes = net.getNodes()
    out[k] = {"width_m": round(x1 - x0), "height_m": round(y1 - y0), "edges": len(edges),
              "road_km": round(L, 1), "junctions": len(nodes),
              "tls": len(net.getTrafficLights()),
              "speed_limits_kmh": sorted({round(e.getSpeed() * 3.6) for e in edges})[:1] + sorted({round(e.getSpeed() * 3.6) for e in edges})[-1:]}
# mean vehicle speed (km/h, t >= 60 s, medium density) from the traces; kept from the previous file if traces are absent
path = os.path.join(S, "..", "results", "scenario_stats.json")
old = json.load(open(path)) if os.path.exists(path) else {}
for k in out:
    sp = []
    for z in sorted(glob.glob(os.path.join(S, "..", "traces", f"{k}_p1.0_s*.npz"))):
        d = np.load(z); off = np.concatenate([[0], np.cumsum(d["lens"])]); sp.append(d["flat"][off[60]:, 3].mean() * 3.6)
    out[k]["mean_speed_kmh"] = round(float(np.mean(sp)), 1) if sp else old.get(k, {}).get("mean_speed_kmh")
json.dump(out, open(path, "w"), indent=1); print(json.dumps(out, indent=1))
