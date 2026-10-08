"""Generate SUMO mobility traces (1 Hz TraCI snapshots) for CyberVANET scenarios.

Usage: python gen_traces.py <scenario> <period_s> <seed> [out_dir]
Scenarios: urban | mixed | vile_parle.  Demand is generated with SUMO's randomTrips
(one trip every <period_s> seconds in [0,200] s), so density is controlled identically
across scenarios.  Output: traces/<scenario>_p<period>_s<seed>.npz
"""
import os, sys, subprocess, shutil, tempfile
import numpy as np
import sumo, traci

HERE = os.path.dirname(os.path.abspath(__file__))
SCEN = os.path.join(HERE, "..", "scenarios")
RT = os.path.join(os.path.dirname(sumo.__file__), "tools", "randomTrips.py")
NETS = {"urban": "urban.net.xml", "mixed": "mixed.net.xml", "vile_parle": "vile_parle.net.xml"}
FRINGE = {"urban": 1, "mixed": 10, "vile_parle": 5}
SIM_END, STEP, SNAP = 300, 0.1, 1.0

def run(scn, period, seed, out_dir):
    net = os.path.abspath(os.path.join(SCEN, NETS[scn]))
    tmp = tempfile.mkdtemp(prefix=f"{scn}_{seed}_")
    trips, rou = os.path.join(tmp, "t.xml"), os.path.join(tmp, "r.xml")
    subprocess.run([sys.executable, RT, "-n", net, "-b", "0", "-e", "200", "-p", str(period),
                    "--fringe-factor", str(FRINGE[scn]), "--seed", str(seed),
                    "-o", trips, "-r", rou, "--validate", "--min-distance", "300",
                    "--vehicle-class", "passenger", "--prefix", "v"],
                   check=True, capture_output=True)
    cfg = ["sumo", "-n", net, "-r", rou, "--step-length", str(STEP), "--seed", str(seed),
           "--no-warnings", "true", "--no-step-log", "true", "--time-to-teleport", "-1",
           "--collision.action", "warn", "--end", str(SIM_END)]
    label = f"{scn}_{seed}_{os.getpid()}"
    traci.start(cfg, label=label)
    conn = traci.getConnection(label)
    snaps = []
    nsteps = int(SIM_END / STEP)
    every = int(SNAP / STEP)
    for k in range(1, nsteps + 1):
        conn.simulationStep()
        if k % every == 0:
            ids = conn.vehicle.getIDList()
            arr = np.zeros((len(ids), 4))
            for i, v in enumerate(ids):
                x, y = conn.vehicle.getPosition(v)
                arr[i] = (int(v[1:]) if v[1:].isdigit() else i, x, y, conn.vehicle.getSpeed(v))
            snaps.append(arr)
    conn.close()
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{scn}_p{period}_s{seed}.npz")
    lens = np.array([len(s) for s in snaps])
    flat = np.concatenate(snaps) if lens.sum() else np.zeros((0, 4))
    np.savez_compressed(out, flat=flat, lens=lens)
    return out, lens

if __name__ == "__main__":
    scn, period, seed = sys.argv[1], float(sys.argv[2]), int(sys.argv[3])
    out_dir = sys.argv[4] if len(sys.argv) > 4 else os.path.join(HERE, "..", "traces")
    out, lens = run(scn, period, seed, out_dir)
    print(out, "mean active (t>=60):", lens[60:].mean().round(1), "max:", lens.max())
