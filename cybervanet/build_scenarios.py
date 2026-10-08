"""Rebuild the urban-grid and mixed urban-highway SUMO networks (Vile Parle ships as an OSM-derived net).
Requires SUMO (netgenerate, netconvert) on PATH, e.g. `pip install eclipse-sumo`.
"""
import os, subprocess
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scenarios")

def run(*a):
    print(" ".join(a)); subprocess.run(a, check=True, cwd=S)

# Urban: 8x8 signalized grid, 150 m blocks (1050 x 1050 m), 50 km/h
run("netgenerate", "--grid", "--grid.number=8", "--grid.length=150", "--default.speed=13.89",
    "--tls.guess", "--no-warnings", "-o", "urban.net.xml")
# Mixed: 5x5 grid (600 x 600 m) + 3 km two-lane 108 km/h highway attached at the east edge
run("netgenerate", "--grid", "--grid.number=5", "--grid.length=150", "--default.speed=13.89",
    "--tls.guess", "--no-warnings", "-o", "grid5.net.xml")
run("netconvert", "-s", "grid5.net.xml", "-n", "hw.nod.xml", "-e", "hw.edg.xml", "--no-turnarounds",
    "--offset.disable-normalization", "--no-warnings", "-o", "mixed.net.xml")
