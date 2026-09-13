"""
Temporal-graph observability model of a port water area.

Reference implementation for the paper "Temporal graph model of port water area
observability in the context of the green port concept".

Discrete time with step DT minutes. Within one snapshot G_t data propagate across
a connected component instantly (link delay << DT); between snapshots the
store-carry-forward principle applies.

Requires Python 3.9+ and the standard library only.
Usage:  python model.py        (prints all numbers reported in the paper)
"""
import math, itertools, json
from collections import defaultdict

DT = 5
T_END = 180
TIMES = list(range(0, T_END + 1, DT))

# ---------- Акваторія: зони 4x3 по 0.5 км ----------
ZONES = {}
for r in range(3):
    for c in range(4):
        k = r * 4 + c + 1
        ZONES[k] = ((c * 0.5, c * 0.5 + 0.5), (r * 0.5, r * 0.5 + 0.5))
def zone_center(k):
    (x0, x1), (y0, y1) = ZONES[k]
    return ((x0 + x1) / 2, (y0 + y1) / 2)
def zone_of(p):
    x, y = p
    for k, ((x0, x1), (y0, y1)) in ZONES.items():
        if x0 <= x < x1 and y0 <= y < y1:
            return k
    return None

W = {k: 1 for k in ZONES}                      # вагові коефіцієнти ризику
for k in (1, 2): W[k] = 3                      # причали нафтоолійного терміналу
for k in (5, 6, 10, 11): W[k] = 2              # прилеглі зони та фарватер
DMAX = {k: {3: 10, 2: 20, 1: 30}[W[k]] for k in ZONES}  # допустимий вік даних, хв

# ---------- Типи вузлів ----------
# channels: множина радіоінтерфейсів; r: дальність, км; q: якість (достовірність) спостереження
TYPES = {
    "CC":     dict(ch={"radio"},          r=1.5, q=None),
    "relay":  dict(ch={"lora", "radio"},  r=1.6, q=None),
    "sensor": dict(ch={"lora"},           r=1.6, q=1.0),
    "tanker": dict(ch={"radio"},          r=3.0, q=None),
    "service":dict(ch={"lora", "radio"},  r=2.0, q=0.9),
    "uav":    dict(ch={"lora", "radio"},  r=2.0, q=0.8),
    "worker": dict(ch={"radio"},          r=1.0, q=0.5),
}
WIRED = {("CC", "R1"), ("CC", "R2")}

def lin(waypoints, t):
    """Кусково-лінійна траєкторія: [(t, x, y), ...]."""
    if t <= waypoints[0][0]:
        return waypoints[0][1:]
    for (t0, x0, y0), (t1, x1, y1) in zip(waypoints, waypoints[1:]):
        if t0 <= t <= t1:
            a = (t - t0) / (t1 - t0) if t1 > t0 else 1
            return (x0 + a * (x1 - x0), y0 + a * (y1 - y0))
    return waypoints[-1][1:]

NODES = {
    "CC": dict(type="CC",     pos=lambda t: (1.6, -0.25), life=(0, 999)),
    "R1": dict(type="relay",  pos=lambda t: (0.4, -0.10), life=(0, 60)),   # знеструмлено о t=60
    "R2": dict(type="relay",  pos=lambda t: (1.6, -0.10), life=(0, 999)),
    "S1": dict(type="sensor", pos=lambda t: (0.25, 0.30), life=(0, 60), zone=1),  # зірваний штормом о t=60
    "S2": dict(type="sensor", pos=lambda t: (1.25, 0.30), life=(0, 999), zone=3),
    "S3": dict(type="sensor", pos=lambda t: (0.75, 0.75), life=(0, 999), zone=6),
    "S4": dict(type="sensor", pos=lambda t: (1.75, 0.75), life=(0, 999), zone=8),
    "S5": dict(type="sensor", pos=lambda t: (0.75, 1.25), life=(0, 999), zone=10),
    "S6": dict(type="sensor", pos=lambda t: (1.75, 1.25), life=(0, 999), zone=12),
    # Танкер біля причалу, відходить о t=120 і залишає акваторію о t=150
    "V1": dict(type="tanker", pos=lambda t: lin([(0, .80, .12), (120, .80, .12), (135, .90, 1.0), (150, 1.1, 1.9)], t),
               life=(0, 150)),
    # Судно портового флоту: о t=70 вирушає до зони терміналу, з t=100 ставить бони
    "V2": dict(type="service", pos=lambda t: lin([(0, 1.65, .15), (70, 1.65, .15), (90, .70, .65), (100, .30, .35)], t),
               life=(0, 999)),
    # БПЛА: зліт о t=90, облітає зони Z1, Z2, Z5, Z6, посадка о t=170
    "D1": dict(type="uav", pos=lambda t: (lin([(90, 1.6, -.25), (100, .5, .5)], t) if t <= 100 else
                                        (.5 + .3 * math.cos((t - 100) / 10), .5 + .3 * math.sin((t - 100) / 10))),
               life=(90, 170)),
    # Працівники з рацією та UWB-бейджем; під час аварії W1 і W2 евакуйовано до пункту збору
    "W1": dict(type="worker", pos=lambda t: lin([(0, .50, -.05), (60, .50, -.05), (65, .90, -.45), (100, .90, -.45), (105, .50, -.05)], t),
               life=(0, 999)),
    "W2": dict(type="worker", pos=lambda t: lin([(0, 1.0, -.05), (60, 1.0, -.05), (65, .95, -.45), (95, .95, -.45), (100, 1.0, -.05)], t),
               life=(0, 999)),
    "W3": dict(type="worker", pos=lambda t: (1.75, -.05), life=(0, 999)),
}

FLAGS = {"jam": True, "destroy": True}
def jam(t):
    """Коефіцієнт погіршення дальності каналів (шторм, перевантаження ефіру), kappa(t)."""
    return 0.5 if (FLAGS["jam"] and 60 <= t < 120) else 1.0

CONFIGS = {
    "A": [n for n in NODES if NODES[n]["type"] in ("CC", "relay", "sensor")],
    "B": [n for n in NODES if NODES[n]["type"] in ("CC", "relay", "sensor", "tanker", "service")],
    "C": list(NODES),
}

def active(n, t, removed=()):
    a, b = NODES[n]["life"]
    if not FLAGS["destroy"] and n in ("R1", "S1"):
        b = 999
    return n not in removed and a <= t < b

def edges_at(t, nodes):
    E = set()
    for u, v in itertools.combinations(nodes, 2):
        if (u, v) in WIRED or (v, u) in WIRED:
            E.add((u, v)); continue
        tu, tv = TYPES[NODES[u]["type"]], TYPES[NODES[v]["type"]]
        # датчики LoRaWAN працюють за схемою «зірка»: лише з вузлами-шлюзами
        if NODES[u]["type"] == "sensor" and NODES[v]["type"] == "sensor":
            continue
        if not (tu["ch"] & tv["ch"]):
            continue
        (x1, y1), (x2, y2) = NODES[u]["pos"](t), NODES[v]["pos"](t)
        if math.hypot(x1 - x2, y1 - y2) <= min(tu["r"], tv["r"]) * jam(t):
            E.add((u, v))
    return E

def sensing_at(t, n):
    """Відношення спостереження: які зони вузол n спостерігає в момент t."""
    ty = NODES[n]["type"]
    if ty == "sensor":
        return {NODES[n]["zone"]}
    p = NODES[n]["pos"](t)
    if ty == "service":
        z = zone_of(p); return {z} if z else set()
    if ty == "uav":
        return {k for k in ZONES if math.dist(p, zone_center(k)) <= 0.45}
    if ty == "worker":
        if p[1] < -0.2:          # у пункті збору спостереження неможливе
            return set()
        return {k for k in ZONES if math.dist(p, zone_center(k)) <= 0.40}
    return set()

def components(nodes, E):
    adj = defaultdict(set)
    for u, v in E:
        adj[u].add(v); adj[v].add(u)
    seen, comps = set(), []
    for s in nodes:
        if s in seen: continue
        stack, comp = [s], []
        seen.add(s)
        while stack:
            u = stack.pop(); comp.append(u)
            for w in adj[u]:
                if w not in seen:
                    seen.add(w); stack.append(w)
        comps.append(comp)
    return comps

def run(config, removed=(), spill=None):
    """Повертає: O(t), вік даних у ЦК, моменти виявлення забруднення."""
    nodes_all = [n for n in CONFIGS[config] if n not in removed]
    store = {n: {} for n in nodes_all}   # store[n][(zone, src_type)] = найсвіжіший момент вимірювання
    O, AGE, first_seen = {}, {}, {}
    for t in TIMES:
        act = [n for n in nodes_all if active(n, t, removed)]
        for n in nodes_all:
            if n not in act:
                store[n] = {}            # вузол вийшов з ладу або вибув, локальні дані втрачено
        for n in act:                    # 1) локальні вимірювання
            ty = NODES[n]["type"]
            for k in sensing_at(t, n):
                store[n][(k, ty)] = t
        E = edges_at(t, act)             # 2) обмін у межах компонент знімка G_t
        # кінцеві датчики LoRaWAN не ретранслюють: компоненти будуються на вузлах-не-датчиках,
        # а кожен датчик передає свої дані всім сусіднім компонентам
        core = [n for n in act if NODES[n]["type"] != "sensor"]
        coreE = {(u, v) for u, v in E if u in core and v in core}
        comps = components(core, coreE)
        cid = {n: i for i, c in enumerate(comps) for n in c}
        merged = [dict() for _ in comps]
        def push(i, src):
            for key, tau in src.items():
                if tau > merged[i].get(key, -1):
                    merged[i][key] = tau
        for i, c in enumerate(comps):
            for n in c:
                push(i, store[n])
        for u, v in E:
            for a, b in ((u, v), (v, u)):
                if NODES[a]["type"] == "sensor" and b in cid:
                    push(cid[b], store[a])
        for i, c in enumerate(comps):
            for n in c:
                store[n] = dict(merged[i])
        cc = store["CC"]                 # 3) стан знань центру керування
        num, age = 0.0, {}
        for k in ZONES:
            best_q, freshest = 0.0, None
            for (kk, ty), tau in cc.items():
                if kk != k: continue
                freshest = tau if freshest is None else max(freshest, tau)
                if t - tau <= DMAX[k]:
                    best_q = max(best_q, TYPES[ty]["q"])
            num += W[k] * best_q
            age[k] = None if freshest is None else t - freshest
            if spill and k in spill and freshest is not None and freshest >= spill[k] and k not in first_seen:
                first_seen[k] = t
        O[t] = num / sum(W.values())
        AGE[t] = age
    return O, AGE, first_seen

def run_static(config, window_of=DMAX):
    """Порівняльна оцінка на статичному агрегованому графі: зона вважається покритою,
    якщо в межах вікна [t-Dmax_k, t] існує вузол, що її спостерігав і належить до однієї
    компоненти з ЦК в об'єднаному (агрегованому) графі за це вікно."""
    nodes_all = CONFIGS[config]
    O = {}
    for t in TIMES:
        num = 0.0
        for k in ZONES:
            win = [s for s in TIMES if t - DMAX[k] <= s <= t]
            aggE, aggN, obs = set(), set(), {}
            for s in win:
                act = [n for n in nodes_all if active(n, s)]
                aggN |= set(act)
                aggE |= edges_at(s, act)
                for n in act:
                    if k in sensing_at(s, n):
                        obs[n] = max(obs.get(n, 0), TYPES[NODES[n]["type"]]["q"])
            core = [n for n in aggN if NODES[n]["type"] != "sensor"]
            coreE = {(u, v) for u, v in aggE if u in core and v in core}
            comp = set(next((c for c in components(core, coreE) if "CC" in c), []))
            for u, v in aggE:           # датчики є листовими вузлами
                for a, b in ((u, v), (v, u)):
                    if NODES[a]["type"] == "sensor" and b in comp:
                        comp.add(a)
            num += W[k] * max([q for n, q in obs.items() if n in comp], default=0.0)
        O[t] = num / sum(W.values())
    return O

# Забруднення: витік із терміналу о t=60 у Z1, поширення на схід/північ кожні 15 хв, стримане бонами (d<=2)
def spill_times():
    sp = {}
    for k in ZONES:
        r, c = (k - 1) // 4, (k - 1) % 4
        d = r + c
        if d <= 2:
            sp[k] = 60 + 15 * d
    return sp

def mean(d, a=0, b=T_END):
    v = [x for t, x in d.items() if a <= t <= b]
    return sum(v) / len(v)

if __name__ == "__main__":
    SP = spill_times()
    res = {}
    for cfg in "ABC":
        O, AGE, fs = run(cfg, spill=SP)
        res[cfg] = dict(O=O, fs=fs)
        det = {k: (fs[k] - SP[k]) if k in fs else None for k in SP}
        print(cfg, "mean O all=%.3f  normal(0-55)=%.3f  crisis(60-115)=%.3f  after(120-180)=%.3f" %
              (mean(O), mean(O, 0, 55), mean(O, 60, 115), mean(O, 120, 180)), "min=%.3f" % min(O.values()))
        print("   detection delay:", det)
    # Критичність вузлів (конфігурація C): зменшення середнього O при вилученні вузла з t=0
    base = mean(run("C")[0])
    crit = []
    for n in CONFIGS["C"]:
        if n == "CC": continue
        crit.append((n, base - mean(run("C", removed=(n,))[0])))
    crit.sort(key=lambda x: -x[1])
    print("criticality:", [(n, round(v, 3)) for n, v in crit])
    # Статичний агрегований граф vs темпоральний
    for cfg in "ABC":
        Os = run_static(cfg)
        Ot = res[cfg]["O"]
        over = [Os[t] - Ot[t] for t in TIMES]
        print(cfg, "static mean=%.3f temporal mean=%.3f  max overestimate=%.3f at t=%d" %
              (mean(Os), mean(Ot), max(over), TIMES[over.index(max(over))]))
        res[cfg]["Os"] = Os
    json.dump({c: {"O": res[c]["O"], "Os": res[c]["Os"], "fs": res[c]["fs"]} for c in res},
              open("results.json", "w"), ensure_ascii=False, indent=1)
    json.dump({"spill": SP, "crit": crit, "base": base}, open("extra.json", "w"), ensure_ascii=False, indent=1)
