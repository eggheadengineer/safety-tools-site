#!/usr/bin/env python3
"""Regenerate index.html from the tools' own output.

Inputs (defaults assume sibling checkouts of reqthread, faultbench and edgegate):
  --bundle   reqthread evidence bundle JSON of examples/wb55-ref  (reqthread build -o bundle.json)
  --fb       faultbench timelines JSON (python build.py --make-fb writes it from the ReferenceDut scenarios)
  --base/--cand  two edgegate results files (edgegate run -o ...)
"""
import argparse, json, pathlib, re

HERE = pathlib.Path(__file__).parent

def make_fb(out):
    from faultbench import Harness, HeartbeatSource, FaultPlan, ReferenceDut, Stop, Drop, Delay, CorruptTag, Replay
    scen = [("stop", "link loss (transmitter stops)", [Stop(at_ms=1000)]),
            ("drop2", "two lost heartbeats (availability)", [Drop(at_ms=1000, count=2)]),
            ("drop3", "three lost heartbeats", [Drop(at_ms=1000, count=3)]),
            ("delay400", "heartbeats delayed 400 ms", [Delay(at_ms=1000, ms=400)]),
            ("forged", "forged authentication tag", [CorruptTag(at_ms=1000)]),
            ("replay", "replayed valid heartbeat", [Replay(at_ms=1000)])]
    res = []
    for key, title, faults in scen:
        with Harness(ReferenceDut(timeout_ms=300), HeartbeatSource(period_ms=100), FaultPlan(*faults)) as h:
            h.run_until(2000)
            res.append({"key": key, "title": title, "enable": [[s.t_ms, int(s.enable)] for s in h.timeline],
                        "rejected": h.dut.rejected[:3]})
    json.dump(res, open(out, "w"))

def fb_rows(fb):
    rows = []
    for s in fb:
        drops = [t for t, e in s["enable"] if not e and t >= 1000]
        first = drops[0] if drops else None
        if s["key"] == "drop2":
            ok = first is None
            result = "stays enabled, no nuisance trip" if ok else f"nuisance trip at {first} ms"
        else:
            ok = first is not None and first - 1000 <= 300
            result = f"safe state {first - 1000} ms after fault" if first is not None else "never tripped"
            if first is not None and not ok:
                result += " (FTTI violated)"
        rows.append({"title": s["title"], "enable": s["enable"], "ok": ok, "result": result})
    return rows

def graph(bundle):
    ents = {e["id"]: e for e in bundle["entities"]}
    links = bundle["links"]
    outcome = {}
    for e in bundle["entities"]:
        if e["kind"] == "test_result":
            outcome[e["test"]] = e["outcome"]
    verified = {l["from"] for l in links if l["type"] == "verifies"}
    mitigated = {l["to"] for l in links if l["type"] == "mitigates"}
    tested = {}
    for l in links:
        if l["type"] == "verifies":
            tested.setdefault(l["to"], []).append(ents[l["from"]].get("level"))
    nodes, out_links = [], []
    for e in bundle["entities"]:
        k = e["kind"]
        if k == "hazard":
            nodes.append({"id": e["id"], "col": "hazard", "kind": "hazard", "label": e["key"] if "key" in e else e["id"].split(":")[1], "text": e.get("title", "")})
        elif k == "cause":
            gap = e["id"] not in mitigated
            nodes.append({"id": e["id"], "col": "cause", "kind": e.get("type", "cause"), "label": e["id"].split(":")[1], "text": e.get("title", ""),
                          "gap": gap, "note": "rule 12: no mitigating requirement and no accepted-risk record" if gap else ""})
        elif k == "requirement":
            levels = tested.get(e["id"], [])
            gap = e["id"].startswith("req:SSR") and "module" not in levels
            nodes.append({"id": e["id"], "col": "requirement", "kind": f"{e.get('level','')} requirement, {e.get('integrity_level','')}".strip(", "), "label": e["id"].split(":")[1], "text": e.get("text", e.get("title", "")),
                          "gap": gap, "note": "rule 1: no verifying test at level module" if gap else (f"{len(levels)} verifying test(s)" if levels else "")})
        elif k == "code_unit":
            if not e.get("symbol"):      # file-level @file units; the graph shows functions
                continue
            nodes.append({"id": e["id"], "col": "code", "kind": e["path"], "label": e["symbol"] + "()", "text": f"{e['path']}:{e['source']['line']}"})
        elif k == "test_case":
            o = outcome.get(e["id"], "skip")
            untraced = e["id"] not in verified
            nodes.append({"id": e["id"], "col": "test", "kind": f"{e['level']} test", "label": e["name"].split("::")[-1], "text": e["name"],
                          "status": "fail" if o == "fail" else ("skip" if o not in ("pass",) else "pass"), "untraced": untraced,
                          "warn": o not in ("pass", "fail"), "note": "runs and passes, but is traced to no requirement" if untraced else ("rule 4: only skipped at baseline" if o not in ("pass", "fail") else "")})
    ids = {n["id"] for n in nodes}
    for l in links:
        if l["type"] in ("leads_to", "mitigates", "satisfies", "verifies") and l["from"] in ids and l["to"] in ids:
            out_links.append({"type": l["type"], "from": l["from"], "to": l["to"]})
    order = {"hazard": 0, "cause": 1, "requirement": 2, "code": 3, "test": 4}
    nodes.sort(key=lambda n: (order[n["col"]], n["label"]))
    return {"nodes": nodes, "links": out_links, "node": {n["id"]: n for n in nodes}}

def cov(bundle):
    for e in bundle["entities"]:
        if e["kind"] == "coverage_record" and e["code_unit"].endswith("#seq_check"):
            m = e["metrics"]
            return f"{m['statement']['covered']} of {m['statement']['total']} statements, {m['branch']['covered']} of {m['branch']['total']} branches"
    return ""

def edgegate(base, cand, cfg_thr):
    from edgegate.compare import FLOORS
    verdict, rows = {}, []
    def pct(b, c): return (c - b) / b * 100 if b else 0.0
    p99b, p99c = base["latency_ms"]["p99"], cand["latency_ms"]["p99"]
    floor = FLOORS["latency_p99_regression_pct"][1]
    reg = pct(p99b, p99c)
    if p99c > cfg_thr["latency_p99_ms_max"]:
        verdict["latency_ms.p99"] = "FAIL: over limit"
    elif reg > cfg_thr["latency_p99_regression_pct"] and (p99c - p99b) >= floor:
        verdict["latency_ms.p99"] = f"FAIL: +{reg:.0f}%"
    elif reg > cfg_thr["latency_p99_regression_pct"]:
        verdict["latency_ms.p99"] = f"+{reg:.0f}%, under {floor} ms floor: pass"
    else:
        verdict["latency_ms.p99"] = "pass"
    verdict["accuracy.value"] = "pass" if cand["accuracy"]["value"] >= cfg_thr["accuracy_min"] and cand["accuracy"]["value"] >= base["accuracy"]["value"] - cfg_thr["accuracy_drop_max"] else "FAIL"
    mb, mc = base["memory"]["peak_rss_mb"], cand["memory"]["peak_rss_mb"]
    verdict["memory.peak_rss_mb"] = f"{pct(mb, mc):+.1f}%"
    for lab, path in [("latency p50 (ms)", ("latency_ms", "p50")), ("latency p90 (ms)", ("latency_ms", "p90")), ("latency p99 (ms)", ("latency_ms", "p99")),
                      ("throughput (inf/s)", ("throughput_ips",)), ("peak RSS (MB)", ("memory", "peak_rss_mb")), ("top-1 accuracy", ("accuracy", "value"))]:
        b = base; c = cand
        for k in path: b = b[k]; c = c[k]
        rows.append(f"<tr><td>{lab}</td><td class=n>{b}</td><td class=n>{c}</td><td class=n>{pct(b, c):+.1f}%</td></tr>")
    table = "<table><tr><th>metric</th><th>baseline</th><th>candidate</th><th>change</th></tr>" + "".join(rows) + "</table>"
    dev = cand["device"]
    note = (f"Device {dev['name']} ({dev['machine']}), {cand['model']['backend']} {cand['model']['version']} {cand['model']['provider']}, "
            f"{cand['benchmark']['iterations']} iterations after {cand['benchmark']['warmup']} warmup. "
            f"The p99 moved {reg:+.0f}% between two runs of the identical model, which is scheduler jitter on a {p99b} ms model. "
            f"Without the {floor} ms absolute floor that would block the merge. Power is null on the host; on Jetson the tegrastats rails are sampled during the run.")
    return {"base": base, "cand": cand, "thr": cfg_thr, "verdict": verdict, "table": table, "note": note}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True); ap.add_argument("--fb", required=True)
    ap.add_argument("--base", required=True); ap.add_argument("--cand", required=True)
    ap.add_argument("--edgegate-config", default=str(HERE.parent / "edgegate/examples/host/edgegate.yaml"))
    ap.add_argument("--make-fb", action="store_true", help="regenerate --fb from faultbench's ReferenceDut first")
    a = ap.parse_args()
    if a.make_fb:
        make_fb(a.fb)
    import yaml
    thr = yaml.safe_load(open(a.edgegate_config))["thresholds"]
    bundle = json.load(open(a.bundle))
    data = {"graph": graph(bundle), "cov": cov(bundle), "fb": fb_rows(json.load(open(a.fb))),
            "eg": edgegate(json.load(open(a.base)), json.load(open(a.cand)), thr),
            "generated": {"reqthread": bundle["generator"]["version"], "bundle_created": bundle["created_at"]}}
    tpl = (HERE / "template.html").read_text()
    (HERE / "index.html").write_text(tpl.replace("/*__DATA__*/", json.dumps(data, separators=(",", ":"))))
    g = data["graph"]
    print(f"index.html: {len(g['nodes'])} nodes, {len(g['links'])} links; gaps:", [n["label"] for n in g["nodes"] if n.get("gap")],
          "untraced:", [n["label"] for n in g["nodes"] if n.get("untraced")], "warn:", [n["label"] for n in g["nodes"] if n.get("warn")])
    for r in data["fb"]: print(" ", r["title"], "->", r["result"])
    print(" ", data["eg"]["verdict"])

if __name__ == "__main__":
    main()
