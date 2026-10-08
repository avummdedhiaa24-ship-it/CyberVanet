"""Pipeline tests: determinism of the evaluator and the paper-claim verifier on the shipped results."""
import os, sys, json, subprocess, numpy as np, pytest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "cybervanet"))

def _tiny_trace(path, seed=1, n=25, T=80):
    rng = np.random.default_rng(seed); snaps = []
    xy = rng.uniform(0, 600, (n, 2)); v = rng.uniform(5, 14, n)
    for t in range(T):
        xy = xy + np.c_[v, np.zeros(n)] ; xy[:, 0] %= 600
        snaps.append(np.c_[np.arange(n), xy, v])
    np.savez_compressed(path, flat=np.concatenate(snaps), lens=np.array([len(s) for s in snaps]))

def test_evaluate_is_deterministic(tmp_path):
    from evaluate import evaluate
    p = tmp_path / "toy_p1.0_s1.npz"; _tiny_trace(p)
    a1, s1, _ = evaluate(str(p)); a2, s2, _ = evaluate(str(p))
    assert all(np.allclose(a1[k], a2[k]) for k in a1) and s1 == s2

def test_pdr_ordering_on_toy_trace(tmp_path):
    from evaluate import evaluate
    p = tmp_path / "toy_p1.0_s2.npz"; _tiny_trace(p, 2)
    a, _, _ = evaluate(str(p))
    pdr = {q: a[f"{q}|clear|rx300"] / a[f"{q}|clear|tx300"] for q in ("DSRC", "C-V2X", "5G-V2X")}
    assert pdr["5G-V2X"] > pdr["C-V2X"] > pdr["DSRC"]

@pytest.mark.skipif(not os.path.exists(os.path.join(ROOT, "results", "summary.json")), reason="no results")
def test_paper_claims_hold_on_shipped_results():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "cybervanet", "verify_claims.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]

HAVE = os.path.exists(os.path.join(ROOT, "results", "summary.json"))

@pytest.mark.skipif(not HAVE, reason="no results")
def test_sites_serve_the_paper_numbers():
    """Both sites use core.py; its numbers must equal results/summary.json (source of the paper tables) in every cell."""
    sys.path.insert(0, os.path.join(ROOT, "site"))
    import app as A
    c = A.app.test_client()
    r = c.get("/api/consistency").get_json()
    assert r["consistent"], r
    for path in ("/", "/analytics", "/formulas"):
        assert c.get(path).status_code == 200

TR = os.path.join(ROOT, "traces")

@pytest.mark.skipif(not HAVE or not os.path.exists(os.path.join(TR, "vile_parle_p2.0_s1.npz")), reason="no traces/results")
@pytest.mark.parametrize("scn", ["urban", "mixed", "vile_parle"])
@pytest.mark.parametrize("weather", ["clear", "rain", "fog"])
def test_live_run_ends_at_the_paper_numbers(scn, weather):
    """The live run executes evaluate.py snapshot by snapshot; its final values must equal the stored run behind the paper."""
    import core
    done = [e for e in core.live_events(scn, "low", 1, weather) if e["type"] == "done"][0]
    assert done["identical"], done

def test_live_stream_over_http():
    sys.path.insert(0, os.path.join(ROOT, "site"))
    import app as A
    r = A.app.test_client().get("/api/live?scenario=urban&density=low&seed=1&weather=rain&speed=100000")
    evs = [json.loads(l[6:]) for l in r.get_data(as_text=True).split("\n\n") if l.startswith("data: ")]
    assert evs[0]["type"] == "start" and evs[-1]["type"] == "done" and evs[-1]["identical"]
    assert sum(e["type"] == "snap" for e in evs) == 240

def test_explain_link_equals_vectorized_model():
    import comm_model as C
    rng = np.random.default_rng(0)
    for _ in range(300):
        for sp in C.SPECS.values():
            d, no, nl, v, w = rng.uniform(1, 1100), int(rng.integers(0, 6)), rng.uniform(0, 250), rng.uniform(0, 130), str(rng.choice(["clear", "rain", "fog"]))
            e = C.explain_link(sp, d, no, nl, v, w)
            p, S, L = C.link_model(sp, np.array([d]), np.array([no]), np.array([nl]), np.array([v]), w)
            sc = C.stability_score(C.stability_terms(sp, np.array([d]), np.array([nl]), L, p))[0]
            assert abs(e["p_rx"] - p[0]) < 1e-9 and abs(e["latency_ms"] - L[0]) < 1e-9 and abs(e["score"] - sc) < 1e-9

def test_evaluate_iter_equals_stored_run():
    import evaluate as EV
    f = os.path.join(TR, "urban_p2.0_s1.npz")
    if not os.path.exists(f): pytest.skip("no traces")
    acc, series, _ = EV.evaluate(f); ref = json.load(open(os.path.join(ROOT, "results", "runs", "urban_p2.0_s1.json")))
    assert all(np.allclose(np.asarray(ref["acc"][k]), np.asarray(acc[k]), rtol=0, atol=1e-9) for k in ref["acc"])

@pytest.mark.skipif(not HAVE, reason="no results")
def test_all_scenarios_seeds_weathers_available():
    import core
    mt = core.meta()
    assert [s["id"] for s in mt["scenarios"]] == ["urban", "mixed", "vile_parle"]
    assert mt["seeds"] == [1, 2, 3, 4, 5, 6] and mt["weathers"] == ["clear", "rain", "fog"]
