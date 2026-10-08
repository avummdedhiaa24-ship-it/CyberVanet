"""CyberVANET communication model (revised).

Keeps the structure of the original model (FSPL + obstacle loss -> normalised signal strength S
-> protocol reliability x density/speed/size factors -> Bernoulli reception), but fixes how it is
*evaluated*:
  * density terms use the LOCAL vehicle count N_loc (vehicles within 300 m of the receiver),
    not the global number of vehicles on the map;
  * obstacle count N_obs is the number of vehicles physically between transmitter and receiver
    (2 m corridor around the Tx-Rx segment), capped at 3, instead of N_global/20;
  * PDR is computed over neighbour links, not over random sender/receiver pairs anywhere on the map;
  * weather enters as an explicit ITU-R specific attenuation (dB/km) added to the path loss;
  * the stability score terms are defined and normalised to [0,1] from measured quantities.
"""
import json, os
from dataclasses import dataclass
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WEATHER = json.load(open(os.path.join(HERE, "..", "results", "weather_coeffs.json")))["gamma_db_per_km"]

PKT_BYTES = 300          # BSM size (as in original code)
C_LIGHT = 3e8
EVAL_RANGE = 300.0       # common link set for PDR / latency comparison (m)
CTX_RANGE = 300.0        # contention domain for N_loc (m)
OBST_DB = 10.0           # dB per obstructing vehicle (original code)
OBST_CAP = 3             # max obstructions counted
CORRIDOR_W = 2.0         # half-width of obstruction corridor (m)
PL_NORM = 150.0          # dB used to normalise path loss to S in [0,1] (original eq. 4)
L_MAX = 50.0             # ms, latency normalisation in stability score (original code)
N_MAX = 200.0            # vehicles, congestion normalisation
W_DEFAULT = (0.2, 0.2, 0.3, 0.3)   # weights of (vr, ds, ld, df)

@dataclass(frozen=True)
class Spec:
    name: str
    R: float        # max range (m)
    t_proc: float   # protocol processing delay (ms)
    f: float        # carrier (GHz)
    rel: float      # protocol reliability constant

SPECS = {
    "DSRC":   Spec("DSRC",   300.0,  4.0,  5.9, 0.85),
    "C-V2X":  Spec("C-V2X",  500.0, 20.0,  5.9, 0.92),
    "5G-V2X": Spec("5G-V2X", 1000.0, 1.0, 28.0, 0.99),
}

def fspl(d, f):
    return 20 * np.log10(np.maximum(d, 1.0)) + 20 * np.log10(f) + 32.4

def link_model(spec, d, n_obs, n_loc, v_kmh, weather="clear"):
    """Return (p_success, S, latency_ms) for arrays of links. p=0 beyond spec.R."""
    obs = np.minimum(n_obs, OBST_CAP) * OBST_DB * (1.5 if spec.name == "5G-V2X" else 1.0)
    gam = WEATHER[str(spec.f)][weather]
    pl = fspl(d, spec.f) + obs + gam * d / 1000.0
    S = np.clip(1.0 - pl / PL_NORM, 0.0, 1.0)
    if spec.name == "5G-V2X":
        S = np.minimum(1.0, S + np.where(d < 500, 0.2, 0.1))
    inrange = d <= spec.R
    S = np.where(inrange, S, 0.0)
    base = S * spec.rel
    dens = np.maximum(0.5, 1 - n_loc / 200.0)
    spd = np.maximum(0.7, 1 - v_kmh / 150.0)
    size = max(0.8, 1 - PKT_BYTES / 2000.0)
    p = base * dens * spd * size
    if spec.name == "C-V2X":
        p = p + np.minimum(0.15, n_loc / 1000.0)
    elif spec.name == "5G-V2X":
        p = p + np.minimum(0.1, n_loc / 1500.0) + np.minimum(0.05, v_kmh / 200.0)
    p = np.where(inrange, np.clip(p, 0.0, 1.0), 0.0)
    lat = d / C_LIGHT * 1000.0 + spec.t_proc + (1.0 - S) * 5.0
    return p, S, lat

def stability_terms(spec, d, n_loc, lat, p):
    vr = np.clip(1 - n_loc / N_MAX, 0, 1)      # congestion term
    ds = np.clip(1 - d / spec.R, 0, 1)         # spatial (distance) margin term
    ld = np.clip(1 - lat / L_MAX, 0, 1)        # latency term
    df = p                                     # delivery term (modelled link success probability)
    return vr, ds, ld, df

def stability_score(terms, w=W_DEFAULT):
    vr, ds, ld, df = terms
    return 100.0 * (w[0] * vr + w[1] * ds + w[2] * ld + w[3] * df)

def count_obstructions(pos, I, J, chunk=6000):
    """Number of other vehicles within CORRIDOR_W of segment I->J (strictly between endpoints)."""
    n = len(pos)
    out = np.zeros(len(I), dtype=np.int16)
    pos = pos.astype(np.float32)
    for s in range(0, len(I), chunk):
        a = pos[I[s:s + chunk]]; b = pos[J[s:s + chunk]]
        ab = b - a
        L2 = (ab ** 2).sum(1)
        L = np.sqrt(L2)
        ak = pos[None, :, :] - a[:, None, :]
        t = (ak[:, :, 0] * ab[:, None, 0] + ak[:, :, 1] * ab[:, None, 1]) / np.maximum(L2[:, None], 1e-6)
        cr = np.abs(ak[:, :, 0] * ab[:, None, 1] - ak[:, :, 1] * ab[:, None, 0]) / np.maximum(L[:, None], 1e-6)
        cond = (t > 0.02) & (t < 0.98) & (cr < CORRIDOR_W)
        out[s:s + chunk] = cond.sum(1)
    return out


def explain_link(spec, d, n_obs, n_loc, v_kmh, weather="clear"):
    """Step-by-step evaluation of paper Eqs. (2)-(8) and (11) for ONE link, returning every intermediate value.
    Written independently of link_model() on purpose; tests assert that both agree for random inputs."""
    d = float(d); steps = []
    def add(eq, name, expr, val, unit=""):
        steps.append({"eq": eq, "name": name, "expr": expr, "value": float(val), "unit": unit})
    fs = 20 * np.log10(max(d, 1.0)) + 20 * np.log10(spec.f) + 32.4
    add("2", "Free-space path loss", "20log10(d) + 20log10(f) + 32.4", fs, "dB")
    mp = 1.5 if spec.name == "5G-V2X" else 1.0
    nob = min(n_obs, OBST_CAP)
    po = mp * OBST_DB * nob
    add("3", "Obstruction loss", f"m_p x 10 dB x min(N_obs,3) = {mp} x 10 x {nob}", po, "dB")
    g = WEATHER[str(spec.f)][weather]
    pw = g * d / 1000.0
    add("4", "Weather attenuation", f"gamma x d/1000 = {g} dB/km x {d/1000:.3f} km", pw, "dB")
    pt = fs + po + pw
    add("5", "Total path loss", "PL_fs + PL_obs + PL_wx", pt, "dB")
    S = min(max(1 - pt / PL_NORM, 0.0), 1.0)
    add("6", "Signal strength (before 5G gain)", "clip(1 - PL_tot/150, 0, 1)", S)
    if spec.name == "5G-V2X":
        dS = 0.2 if d < 500 else 0.1
        S = min(1.0, S + dS)
        add("6", "5G beamforming gain", f"+{dS} ({'d<500 m' if d < 500 else 'd>=500 m'})", S)
    if d > spec.R:
        S = 0.0
        add("6", "Out of range", f"d = {d:.0f} m > R = {spec.R:.0f} m, so S = 0", S)
    Fn = max(0.5, 1 - n_loc / 200.0); Fv = max(0.7, 1 - v_kmh / 150.0); Fs = max(0.8, 1 - PKT_BYTES / 2000.0)
    add("7", "Density factor F_n", f"max(0.5, 1 - N_loc/200), N_loc = {n_loc:.0f}", Fn)
    add("7", "Speed factor F_v", f"max(0.7, 1 - v/150), v = {v_kmh:.0f} km/h", Fv)
    add("7", "Packet-size factor F_s", f"max(0.8, 1 - {PKT_BYTES}/2000)", Fs)
    base = S * spec.rel * Fn * Fv * Fs
    add("7", "Base reception", f"S x rho x F_n x F_v x F_s, rho = {spec.rel}", base)
    if spec.name == "C-V2X": B = min(0.15, n_loc / 1000.0)
    elif spec.name == "5G-V2X": B = min(0.1, n_loc / 1500.0) + min(0.05, v_kmh / 200.0)
    else: B = 0.0
    add("7", "Protocol bonus B_p", {"DSRC": "0 (DSRC)", "C-V2X": "min(0.15, N_loc/1000)", "5G-V2X": "min(0.1, N_loc/1500) + min(0.05, v/200)"}[spec.name], B)
    p = 0.0 if d > spec.R else min(1.0, max(0.0, base + B))
    add("7", "Reception probability P_rx", "min(1, base + B_p)", p)
    lat = d / C_LIGHT * 1000.0 + spec.t_proc + (1.0 - S) * 5.0
    add("8", "End-to-end latency", f"d/c x 1e3 + t_p + 5(1-S), t_p = {spec.t_proc} ms", lat, "ms")
    vr = min(max(1 - n_loc / N_MAX, 0), 1); ds = min(max(1 - d / spec.R, 0), 1); ld = min(max(1 - lat / L_MAX, 0), 1)
    add("11", "Congestion term v_r", "1 - N_loc/200", vr); add("11", "Distance margin d_s", f"1 - d/R_p, R_p = {spec.R:.0f} m", ds)
    add("11", "Latency term l_d", "1 - L/50", ld); add("11", "Delivery term d_f", "P_rx", p)
    sc = 100 * (W_DEFAULT[0] * vr + W_DEFAULT[1] * ds + W_DEFAULT[2] * ld + W_DEFAULT[3] * p)
    add("11", "Stability score", "100(0.2 v_r + 0.2 d_s + 0.3 l_d + 0.3 d_f)", sc)
    return {"protocol": spec.name, "p_rx": p, "S": S, "latency_ms": lat, "score": sc, "steps": steps}
