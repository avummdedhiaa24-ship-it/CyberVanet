# CyberVANET

This repository regenerates **every number, table and figure** in the revised CyberVANET paper
(`tex/main.tex`) and checks the paper's claims automatically. Nothing in the paper's results is typed by hand:
`tex/numbers.tex` and `tex/tab_*.tex` are written by `cybervanet/make_tex_data.py` from `results/summary.json`.

## What is (and is not) modeled

* **Mobility** is real SUMO/TraCI microsimulation (traffic lights, car following, lane changes), sampled at 1 Hz.
* **Communication** is an *abstract probabilistic channel model* (paper Eqs. 1-11, `cybervanet/comm_model.py`): free-space
  path loss + obstruction loss + ITU-R weather attenuation -> signal strength S -> reception probability
  -> Bernoulli draw per directed link per second. It is **not** a packet-level PHY/MAC simulation
  (ns-3 / OMNeT++ / Veins). PDR is a relative link-quality index, not a field prediction.
* **Stability-aware forwarding** is a link-ranking component evaluated for one-hop relay selection
  (random / greedy-geographic / stability-aware / oracle), not a complete routing protocol.

## Quick start

```bash
pip install -r requirements.txt
python main.py verify        # asserts all paper claims against the shipped results (seconds)
python -m pytest tests -q    # unit + pipeline tests
python main.py site          # http://127.0.0.1:5000  both web sites, one backend, no mock data
python main.py quick         # under a minute: smoke test: SUMO -> traces -> model, 1 scenario x 2 seeds
python main.py all           # full re-run: 54 traces + 54 evaluations + figures + tables + verify (hours)
python main.py paper         # recompile tex/main.pdf (pdflatex, bibtex, IEEEtran)
```

The full re-run is deterministic (SUMO seeds 1-6, evaluator RNG seed 1000+seed): re-running reproduces `results/summary.json`
exactly (given the same SUMO version, 1.28.0 was used).

## The web site: CyberVANET | Research Command

`python main.py site` serves http://127.0.0.1:5000 (no internet needed; Chart.js is bundled). The old mock-data
"VANET Protocol Comparison Dashboard" and the stand-alone engines it used are removed.

| page | what it does |
|---|---|
| `/` **Live Run** | Press *Run simulation*. The server reads the SUMO trace of the chosen **scenario** (urban, mixed, Vile Parle), **density** (low, medium, high), **seed** (1-6) and **weather** (clear, rain, fog) and, second by second after the 60 s warm-up, evaluates the paper's model: neighbor links, obstruction count, path loss, weather attenuation, signal strength, reception probability, latency, stability score, PDR and goodput (Eqs. 1-11) for DSRC, C-V2X and 5G-V2X, plus the relay-selection experiment. Shown live: network map, per-protocol charts and cumulative telemetry, PDR for all three weather conditions, relay selection, and a formula inspector with every intermediate value. At the end it compares itself with the stored run behind the paper tables. |
| `/analytics` **Results** | The same configuration aggregated over the six seeds (mean +/- 95 % CI): PDR vs distance, density, weather, relay selection, full table. |
| `/formulas` | Step-by-step evaluation of Eqs. (2)-(8) and (11) for any distance, obstruction count, density and speed. |

There is exactly one implementation of the model. The live run executes `cybervanet/evaluate.py` (the code that produced `results/runs/*.json`) one snapshot at a time with the same random stream, so its final numbers are identical to the paper's; the Results page reads the stored runs through `cybervanet/metrics.py`, the function that also writes the paper tables. Tests check this for every scenario and weather, and that `explain_link` (formula inspector) equals the vectorized `link_model`. If a trace is missing, the live run generates it with SUMO (needs `eclipse-sumo`).

## Layout

| path | purpose |
|---|---|
| `cybervanet/comm_model.py` | channel, reception, latency, obstruction counting, stability score (Eqs. 1-11) |
| `cybervanet/gen_traces.py` | SUMO `randomTrips` + TraCI -> `traces/*.npz` |
| `cybervanet/evaluate.py` | per-trace evaluation: PDR, latency, goodput, weather, score, relay experiment |
| `cybervanet/aggregate.py` | mean +/- 95% CI (Student t, 6 seeds) -> `results/summary.json` |
| `cybervanet/weather_coeffs.py` | ITU-R P.838-3 (rain, `itur`) and P.840 (fog) -> `results/weather_coeffs.json` |
| `cybervanet/make_figures.py`, `make_tex_data.py` | figures, `numbers.tex`, tables |
| `cybervanet/verify_claims.py` | 31 assertions, one or more per claim in the paper |
| `cybervanet/build_scenarios.py` | rebuilds the urban / mixed networks (`netgenerate`, `netconvert`) |
| `cybervanet/metrics.py` | per-run metrics: the ONE function behind the paper tables and both web sites |
| `cybervanet/core.py`, `site/` | live-run backend + Flask app (Live Run, Results, Formulas) |
| `cybervanet/build_geometry.py` | exports road geometry for the live map |
| `traces/` | the 54 SUMO traces (1 Hz positions and speeds) used by the live run |
| `scenarios/` | SUMO networks (Vile Parle is OSM-derived) |
| `results/` | `runs/*.json` (54 raw runs), `summary.json`, weather and scenario constants |
| `tests/` | model-equation tests, determinism test, claims test |

## Claim -> check map (`verify_claims.py`)

| paper claim (Sec. VI) | check |
|---|---|
| 5G-V2X > C-V2X > DSRC in PDR300, exceeding the CIs, in all 9 settings | C1 |
| Latency 5G-V2X < DSRC < C-V2X, CI < 0.05 ms | C2, C2b |
| DSRC and 5G-V2X lose PDR with density; C-V2X changes < 0.6 pp; mixed degrades most; goodput rises | C3a-g |
| DSRC / C-V2X weather change < 0.5 %, CI includes 0 in most comparisons; 5G-V2X rain > fog; rain effect grows with range; latency change < 0.05 ms; ITU constants | C4a-e |
| Pair-based PDR << neighbor-link PDR; absolute PDR moderate (relative index) | C5a-c |
| Stability score ranks 5G-V2X > DSRC > C-V2X | C6 |
| Relay: stability-aware > random (CI excludes 0), oracle >= stability-aware >= random, largest for 5G-V2X, grows with density, robust to weights, absolute delivery low | C7a-f |

If you change a constant in `comm_model.py` and re-run, `verify` tells you which sentences of the paper no longer hold.

## Known limits

* Constants in the paper's Table of parameters (ranges, processing delays, reliability) are assumptions; the technology ordering partly follows from them.
* Building blockage and wet-surface multipath are not modeled; weather is ITU-R attenuation only.
* The relay experiment shares variables with the channel model, so it demonstrates component behavior, not independent evidence of real-network gains.
* `python main.py traces` regenerates the traces with SUMO (hours for all 54).
