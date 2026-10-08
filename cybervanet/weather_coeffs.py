"""Compute ITU-R specific attenuation values used by the weather model.
Rain: ITU-R P.838-3 (via the `itur` package), horizontal polarisation, zero elevation.
Fog : ITU-R P.840 double-Debye liquid-water model, gamma = K_l * M, T = 15 C.
"""
import json, os
import numpy as np
from itur.models import itu838

def kl(f_ghz, T=288.15):
    th = 300.0 / T
    e0 = 77.66 + 103.3 * (th - 1); e1 = 0.0671 * e0; e2 = 3.52
    fp = 20.20 - 146 * (th - 1) + 316 * (th - 1) ** 2; fs = 39.8 * fp
    epp = f_ghz * (e0 - e1) / (fp * (1 + (f_ghz / fp) ** 2)) + f_ghz * (e1 - e2) / (fs * (1 + (f_ghz / fs) ** 2))
    ep = (e0 - e1) / (1 + (f_ghz / fp) ** 2) + (e1 - e2) / (1 + (f_ghz / fs) ** 2) + e2
    eta = (2 + ep) / epp
    return 0.819 * f_ghz / (epp * (1 + eta ** 2))

RAIN_RATE = 25.0   # mm/h  (heavy rain)
FOG_M = 0.5        # g/m^3 (dense fog, visibility ~50 m)
out = {"rain_rate_mm_h": RAIN_RATE, "fog_liquid_water_g_m3": FOG_M, "temperature_K": 288.15, "gamma_db_per_km": {}}
for f in (5.9, 28.0):
    g_rain = float(getattr(itu838.rain_specific_attenuation(RAIN_RATE, f, 0.0, 0.0), "value", 0))
    g_fog = float(kl(f) * FOG_M)
    out["gamma_db_per_km"][str(f)] = {"clear": 0.0, "rain": round(g_rain, 4), "fog": round(g_fog, 4), "Kl": round(float(kl(f)), 4)}
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "weather_coeffs.json")
json.dump(out, open(path, "w"), indent=2); print(json.dumps(out, indent=2))
