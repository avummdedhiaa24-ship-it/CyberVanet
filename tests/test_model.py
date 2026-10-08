"""Unit tests for the channel model against the equations in the paper (Sec. IV)."""
import os, sys, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cybervanet"))
from comm_model import SPECS, link_model, fspl, stability_terms, stability_score, count_obstructions

def one(p, d, nobs=0, nloc=0.0, v=0.0, w="clear"):
    pr, S, L = link_model(SPECS[p], np.array([float(d)]), np.array([nobs]), np.array([float(nloc)]), np.array([float(v)]), w)
    return float(pr[0]), float(S[0]), float(L[0])

def test_fspl_matches_formula():
    assert abs(float(fspl(100.0, 5.9)) - (20 * np.log10(100) + 20 * np.log10(5.9) + 32.4)) < 1e-9

def test_protocol_parameters():
    s = SPECS
    assert (s["DSRC"].R, s["C-V2X"].R, s["5G-V2X"].R) == (300, 500, 1000)
    assert (s["DSRC"].t_proc, s["C-V2X"].t_proc, s["5G-V2X"].t_proc) == (4, 20, 1)
    assert (s["DSRC"].rel, s["C-V2X"].rel, s["5G-V2X"].rel) == (0.85, 0.92, 0.99)

def test_out_of_range_is_zero():
    for p, R in (("DSRC", 300), ("C-V2X", 500), ("5G-V2X", 1000)):
        assert one(p, R + 1)[0] == 0.0

def test_pdr_monotone_in_distance_and_obstruction():
    for p in SPECS:
        a, b, c = one(p, 50)[0], one(p, 150)[0], one(p, 250)[0]
        assert a >= b >= c
        assert one(p, 100, nobs=0)[0] >= one(p, 100, nobs=2)[0]

def test_probability_bounds():
    rng = np.random.default_rng(0)
    for p in SPECS:
        d = rng.uniform(1, SPECS[p].R, 500); n = rng.integers(0, 5, 500)
        pr, S, L = link_model(SPECS[p], d, n, rng.uniform(0, 300, 500), rng.uniform(0, 120, 500), "clear")
        assert (pr >= 0).all() and (pr <= 1).all() and (S >= 0).all() and (S <= 1).all()

def test_latency_floor_is_processing_delay():
    for p in SPECS:
        assert one(p, 5)[2] >= SPECS[p].t_proc

def test_rain_hurts_5g_more_than_dsrc():
    r5 = one("5G-V2X", 900, w="rain")[0] / one("5G-V2X", 900)[0]
    rd = one("DSRC", 290, w="rain")[0] / one("DSRC", 290)[0]
    assert r5 < rd <= 1.0

def test_stability_weights_sum_to_one_and_score_range():
    from evaluate import WSETS
    for w in WSETS.values(): assert abs(sum(w) - 1) < 1e-12
    d = np.array([10.0, 150.0, 290.0]); p, S, L = link_model(SPECS["DSRC"], d, np.zeros(3, int), np.full(3, 20.0), np.full(3, 30.0))
    sc = stability_score(stability_terms(SPECS["DSRC"], d, np.full(3, 20.0), L, p))
    assert (sc >= 0).all() and (sc <= 100).all() and sc[0] > sc[2]

def test_obstruction_corridor():
    pos = np.array([[0, 0], [100, 0], [50, 1.0], [50, 30.0]])
    assert int(count_obstructions(pos, np.array([0]), np.array([1]))[0]) == 1   # only the vehicle in the 2 m corridor
