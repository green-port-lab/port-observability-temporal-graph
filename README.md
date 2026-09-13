# Temporal-graph observability model of a port water area

Reference implementation and reproduction scripts for the paper

> **Temporal graph model of port water area observability in the context of the green port concept**
> *(author, journal, year — to be filled in on publication)*

The paper treats a port water area as a distributed cyber-physical system whose
participants and communication links change over time. The observing system is
modelled as a temporal graph whose vertices are fixed sensors, shore gateways,
vessels, unmanned aerial vehicles, workers with portable radios and UWB badges,
and the control centre. This repository contains the model, the illustrative
scenario, and everything needed to regenerate every number and figure in the paper.

## What the model computes

For each zone of the water area and each time step the model determines whether a
measurement has reached the control centre along a **time-respecting path**, how old
that measurement is, and how reliable its source was. From this it derives:

* **Δ-observability** of a zone — the age of the freshest delivered measurement does
  not exceed the limit set for that zone;
* **the observability index O(t)** — the risk-weighted share of zones observed in time
  and with sufficient reliability;
* **node criticality χ(v)** — the drop in the mean index when a participant is removed.

A comparison against a **static aggregated graph** shows how much a time-agnostic
model overstates observability.

## Requirements

* Python 3.9 or newer — the model itself uses the **standard library only**
* Matplotlib (figures only): `pip install matplotlib`

No other dependencies, no configuration, no data files.

## Usage

```bash
# all numbers reported in the paper, printed to stdout
python src/model.py

# the same numbers written to results/*.csv, plus run-time measurements
python src/reproduce.py

# figures 1-3 written to figures/*.png
python src/fig1.py
python src/figs.py
```

## Repository layout

```
src/model.py       the model: scenario, temporal graph, index and criticality
src/reproduce.py   regenerates every table and quoted number as CSV
src/fig1.py        Fig. 1, the two-contour conceptual scheme
src/figs.py        Fig. 2 (graph snapshots) and Fig. 3 (index dynamics)
results/           generated CSV output
figures/           generated PNG figures, 300 dpi
```

## The scenario

An accident during a storm at an oil terminal. All parameters are **set
conventionally for illustration**: they are plausible in order of magnitude but are
not derived from measurements at any real port. The numbers below demonstrate the
behaviour of the method, not the performance of an existing system.

**Water area.** 2 × 1.5 km, split into 12 zones of 0.5 × 0.5 km. Zones Z1 and Z2 next
to the terminal carry risk weight *w* = 3 and a maximum data age of 10 min; Z5, Z6 and
the fairway zones Z10, Z11 carry *w* = 2 and 20 min; the rest carry *w* = 1 and 30 min.

**Participants (15).** Control centre CC and shore gateways R1, R2 (wired to CC);
buoys S1–S6 with LoRaWAN, range 1.6 km, in zones Z1, Z3, Z6, Z8, Z10, Z12; tanker V1
at the berth (radio, 3 km), leaving at 120 min and clearing the area at 150 min;
port service vessel V2 with an onboard sensor and a LoRaWAN gateway (2 km), heading
for the terminal at 70 min and deploying booms from 100 min; unmanned aerial vehicle
D1 (2 km), airborne from 90 to 170 min; workers W1–W3 with portable radios (1 km) and
visual observation within 0.4 km.

**Events.** At 60 min a pipeline ruptures at the berth and oil enters zone Z1. The
terminal section is de-energised, so gateway R1 goes down; buoy S1 is torn from its
mooring by the storm. The slick advances one zone every 15 min and is contained by
booms two zones out. From 60 to 120 min link conditions are degraded (κ = 0.5).
Workers W1 and W2 are evacuated to the assembly point until roughly 95–100 min.

**Configurations compared.** A — fixed infrastructure only; B — A plus vessels;
C — all participants.

Time step δ = 5 min, horizon 180 min.

## Selected results

Mean index over the accident interval (60–115 min): **0.19** for configuration A,
**0.29** for B, **0.42** for C. The static aggregated graph overstates the index by
0.058 on average and by up to **0.215** at 100 min, because of an "island of
observers" — a group of participants holding fresh measurements but with no
time-respecting path to the control centre.

A single run takes 1.1–4.9 ms depending on configuration; evaluating the criticality
of all participants (15 runs) takes about 61 ms (Python 3.12, x86-64).

## Reproducibility

The model is fully deterministic: no random number generation, no external data, no
wall-clock dependence. Any run on any machine yields identical values. Only the
`timings.csv` output is hardware-dependent.

## Citing

Please cite the paper. Once it is published, its DOI and bibliographic details will
be added here.

## License

MIT — see [LICENSE](LICENSE).
