"""Export road geometry of each SUMO network to site/static/geom/<scenario>.json (for the live map)."""
import os, json, sumolib
H = os.path.dirname(os.path.abspath(__file__)); S = os.path.join(H, "..", "scenarios"); O = os.path.join(H, "..", "site", "static", "geom")
os.makedirs(O, exist_ok=True)
for scn in ("urban", "mixed", "vile_parle"):
    net = sumolib.net.readNet(os.path.join(S, f"{scn}.net.xml"), withInternal=False)
    x0, y0, x1, y1 = net.getBoundary(); edges = []
    for e in net.getEdges():
        if e.getFunction() != "": continue
        pts = [(round(x), round(y)) for x, y in e.getShape()]
        edges.append([c for p in pts for c in p])
    json.dump({"bbox": [round(x0), round(y0), round(x1), round(y1)], "edges": edges}, open(os.path.join(O, f"{scn}.json"), "w"), separators=(",", ":"))
    print(scn, len(edges), os.path.getsize(os.path.join(O, f"{scn}.json")) // 1024, "KB")
