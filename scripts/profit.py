# quick & simple (รันใน notebook/สคริปต์)
from pymongo import MongoClient
import numpy as np
cli = MongoClient("<MONGO_URI>")
c = cli["wms"]["decision_runs"]

def kpi(filter_):
    docs = list(c.find(filter_, {"_id":0, "decision":1}))
    profits, km_list, regrets, winners = [], [], [], []
    for d in docs:
        dec = d["decision"]; cands = dec.get("candidates", [])
        if not cands: continue
        chosen = dec.get("chosen_warehouse")
        best = max(cands, key=lambda x: x.get("profit", 0))
        chosen_c = next((x for x in cands if x["warehouse_id"]==chosen), best)
        profits.append(chosen_c.get("profit", 0))
        km_list.append((chosen_c.get("route") or {}).get("km", 0))
        regrets.append(best.get("profit",0) - chosen_c.get("profit",0))
        winners.append(chosen)
    import collections, math
    h = collections.Counter(winners)
    total = sum(h.values()) or 1
    # Herfindahl-Hirschman Index (ยิ่งต่ำยิ่งกระจาย)
    hhi = sum((cnt/total)**2 for cnt in h.values())
    return {
        "n": len(profits),
        "profit_mean": np.mean(profits) if profits else 0,
        "profit_p50": float(np.median(profits)) if profits else 0,
        "profit_p95": float(np.percentile(profits,95)) if profits else 0,
        "km_median": float(np.median(km_list)) if km_list else 0,
        "regret_mean": np.mean(regrets) if regrets else 0,
        "winner_hhi": hhi,
        "winner_share": {k: round(v/total,3) for k,v in h.items()}
    }

old = kpi({"decision.meta.version":"v_old"})
new = kpi({"decision.meta.version":"v_new"})
print("OLD:", old)
print("NEW:", new)
