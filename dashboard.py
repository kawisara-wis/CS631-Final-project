# --- วางแทน compute_kpis(...) เดิมทั้งฟังก์ชัน ---

import json, statistics as stats
from collections import defaultdict, Counter

def _as_dict(x):
    """พยายามแปลง x ให้เป็น dict:
       - ถ้าเป็น str จะลอง json.loads
       - ถ้าไม่ใช่ dict หลังพยายามแปลง คืน {} """
    if isinstance(x, dict):
        return x
    if isinstance(x, str):
        try:
            y = json.loads(x)
            return y if isinstance(y, dict) else {}
        except Exception:
            return {}
    return {}

def _safe_float(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return float(d)

def _bin(x, step):
    return step * round(_safe_float(x)/step)

def _ewma(values, alpha=0.3):
    s = None
    for v in values:
        s = v if s is None else alpha*v + (1-alpha)*s
    return s if s is not None else 0.0

def compute_kpis(from_ts=None, to_ts=None, brief: bool=False):
    from core.db import get_recent_decisions, list_active_warehouses

    #decisions = get_recent_decisions(days=365*5) or []

    # ใหม่ ดูย้อนหลังแค่ 1 วัน
    decisions = get_recent_decisions(days=1) or []
    if from_ts or to_ts:
        decisions = [
            d for d in decisions
            if (from_ts is None or d.get("ts", 0) >= from_ts) and
               (to_ts   is None or d.get("ts", 0) <= to_ts)
        ]

    whs = {w["warehouse_id"]: w for w in (list_active_warehouses() or [])}

    chosen_seq = []
    util_history = defaultdict(list)
    profit_history = defaultdict(list)
    price_history = defaultdict(list)
    regret_list = []

    accept_cnt = decline_cnt = forward_cnt = 0
    exploration_cnt = 0

    clusters = defaultdict(list)

    for row in decisions:
        dec = _as_dict(row.get("decision"))
        offer = _as_dict(row.get("offer"))

        accept = dec.get("accept", row.get("accept"))
        chosen_wid = dec.get("chosen_warehouse", row.get("chosen_warehouse"))

        reason = dec.get("reason", row.get("reason"))
        reason_dict = _as_dict(reason)
        exploration = bool(reason_dict.get("exploration", False))
        if exploration:
            exploration_cnt += 1

        if bool(accept):
            accept_cnt += 1
        else:
            decline_cnt += 1

        cands = dec.get("candidates", row.get("candidates"))
        if isinstance(cands, str):
            try:
                cands = json.loads(cands)
            except Exception:
                cands = []
        if not isinstance(cands, list):
            cands = []

        chosen = None
        best = None
        for c in cands:
            if not isinstance(c, dict):
                continue
            if best is None or _safe_float(c.get("profit")) > _safe_float(best.get("profit")):
                best = c
            if chosen_wid and c.get("warehouse_id") == chosen_wid:
                chosen = c

        src = chosen or best or {}
        rt = src.get("route") or {}
        if isinstance(rt, (list, tuple)) and len(rt) >= 2:
            km = _safe_float(rt[0]); minutes = _safe_float(rt[1])
        else:
            km = _safe_float(rt.get("km")); minutes = _safe_float(rt.get("minutes"))

        util = _safe_float(src.get("utilization"))
        profit = _safe_float(src.get("profit"))
        price = _safe_float(src.get("price_amount"))
        cost = _safe_float(src.get("cost"))

        if chosen and best and _safe_float(best.get("profit")) > 0:
            regret = max(0.0, (_safe_float(best.get("profit")) - _safe_float(chosen.get("profit")))
                              / _safe_float(best.get("profit")))
            regret_list.append(regret)

        if chosen_wid and chosen:
            util_history[chosen_wid].append(util)
            profit_history[chosen_wid].append(profit)
            price_history[chosen_wid].append(price)
            chosen_seq.append((int(row.get("ts", 0)), chosen_wid, km, util, profit, price, cost, exploration))

        vol = _safe_float(offer.get("volume_cbm"))
        vol_key = _bin(vol, 5.0)
        dist_key = _bin(km, 5.0)
        if chosen_wid:
            clusters[(vol_key, dist_key)].append(chosen_wid)

    # Utilization KPI
    util_kpi = {}
    for wid, utils in util_history.items():
        utils_sorted = sorted(utils)
        p90 = utils_sorted[int(0.9*len(utils))-1] if len(utils) >= 10 else None
        util_kpi[wid] = {
            "mean_util": round(stats.mean(utils), 4) if utils else 0.0,
            "p90_util": round(p90, 4) if p90 is not None else None,
            "ewma_util": round(_ewma(utils, alpha=0.3), 4) if utils else 0.0,
            "samples": len(utils),
        }

    # Profitability KPI
    PROFIT_TO_TOKEN = _safe_float(os.getenv("PROFIT_TO_TOKEN", "1.0"))
    profit_kpi = {}
    total_profit = 0.0
    for wid, profits in profit_history.items():
        s = sum(profits); total_profit += s
        profit_kpi[wid] = {
            "total_profit": round(s, 2),
            "avg_profit": round(stats.mean(profits), 2) if profits else 0.0,
            "median_profit": round(stats.median(profits), 2) if profits else 0.0,
            "tokens_earned": round(s * PROFIT_TO_TOKEN, 2),
        }
    overall_tokens = round(total_profit * PROFIT_TO_TOKEN, 2)

    # Efficiency KPI
    total = accept_cnt + decline_cnt + forward_cnt
    eff_kpi = {
        "accept_rate": round(accept_cnt / total, 4) if total else 0.0,
        "decline_rate": round(decline_cnt / total, 4) if total else 0.0,
        "forward_rate": round(forward_cnt / total, 4) if total else 0.0,
        "avg_regret": round(stats.mean(regret_list), 4) if regret_list else None,
        "median_regret": round(stats.median(regret_list), 4) if regret_list else None,
        "n_with_regret": len(regret_list),
    }

    # Consistency KPI
    cluster_scores = []
    dominant_table = []
    for key, winners in clusters.items():
        if len(winners) < 3:
            continue
        cnt = Counter(winners)
        dominant, freq = cnt.most_common(1)[0]
        consistency = freq / len(winners)
        cluster_scores.append(consistency)
        if not brief:
            dominant_table.append({
                "cluster": {"vol_bin": key[0], "dist_bin": key[1]},
                "dominant_warehouse": dominant,
                "consistency": round(consistency, 4),
                "n": len(winners),
            })
    exploration_rate = round(exploration_cnt / max(1, len(decisions)), 4)

    consistency_kpi = {
        "avg_cluster_consistency": round(stats.mean(cluster_scores), 4) if cluster_scores else None,
        "median_cluster_consistency": round(stats.median(cluster_scores), 4) if cluster_scores else None,
        "exploration_rate": exploration_rate,
        "top_clusters": sorted(dominant_table, key=lambda x: (-x["n"], -x["consistency"]))[:10],
    }

    return {
        "utilization": util_kpi,
        "profitability": {
            "per_warehouse": profit_kpi,
            "overall_tokens": overall_tokens,
            "overall_profit": round(total_profit, 2),
        },
        "efficiency": eff_kpi,
        "consistency": consistency_kpi,
        "meta": {
            "n_decisions": len(decisions),
            "warehouses_seen": sorted(set(util_history.keys()) | set(profit_history.keys())),
        },
    }


# ===== add to bottom of metrics/dashboard.py =====
import os, json, time
from pathlib import Path

def _load_env(path):
    try:
        from dotenv import load_dotenv
        if path:
            ok = load_dotenv(path); print(f"[INFO] .env loaded from: {path}" if ok else f"[WARN] failed to load {path}")
        else:
            # auto ROOT/.env
            root_env = Path(__file__).resolve().parents[1] / ".env"
            if root_env.exists():
                ok = load_dotenv(root_env); print(f"[INFO] .env loaded from: {root_env}" if ok else f"[WARN] failed to load {root_env}")
    except Exception as e:
        print(f"[WARN] cannot load .env: {e}")

def _print_plain(k):
    # Overall / Efficiency
    eff = k["efficiency"]; prof = k["profitability"]; cons = k["consistency"]
    print("\n=== OVERALL ===")
    print(f"n_decisions={k['meta']['n_decisions']}, warehouses={','.join(k['meta']['warehouses_seen'])}")
    print(f"accept_rate={eff['accept_rate']:.3f}, decline_rate={eff['decline_rate']:.3f}, "
          f"avg_regret={eff.get('avg_regret')}, exploration_rate={cons.get('exploration_rate',0):.3f}")
    print(f"overall_profit={prof['overall_profit']:.2f}, overall_tokens={prof['overall_tokens']:.2f}")

    # Per-warehouse (Util + Profit)
    print("\n=== BY WAREHOUSE (utilization & profit) ===")
    for wid in sorted(set(k["utilization"].keys()) | set(prof["per_warehouse"].keys())):
        u = k["utilization"].get(wid, {})
        p = prof["per_warehouse"].get(wid, {})
        print(f"- {wid}: mean_util={u.get('mean_util',0):.3f}, ewma_util={u.get('ewma_util',0):.3f}, "
              f"avg_profit={p.get('avg_profit',0):.2f}, total_profit={p.get('total_profit',0):.2f}, tokens={p.get('tokens_earned',0):.2f}")

def _print_table(k):
    try:
        from rich.table import Table
        from rich.console import Console
        from rich.panel import Panel
    except Exception:
        # fallback plain
        return _print_plain(k)

    eff = k["efficiency"]; prof = k["profitability"]; cons = k["consistency"]

    c = Console()
    ov = Table(title="Overall KPIs")
    ov.add_column("n_decisions"); ov.add_column("accept_rate"); ov.add_column("decline_rate")
    ov.add_column("overall_profit"); ov.add_column("tokens"); ov.add_column("exploration_rate")
    ov.add_row(
        str(k["meta"]["n_decisions"]),
        f"{eff['accept_rate']:.3f}",
        f"{eff['decline_rate']:.3f}",
        f"{prof['overall_profit']:.2f}",
        f"{prof['overall_tokens']:.2f}",
        f"{cons.get('exploration_rate',0):.3f}",
    )
    c.print(Panel(ov, title="WMS Agent Metrics"))

    t = Table(title="By Warehouse (Utilization & Profit)", show_lines=False)
    for col in ["warehouse","mean_util","ewma_util","avg_profit","total_profit","tokens"]:
        t.add_column(col)

    all_wids = sorted(set(k["utilization"].keys()) | set(prof["per_warehouse"].keys()))
    for wid in all_wids:
        u = k["utilization"].get(wid, {})
        p = prof["per_warehouse"].get(wid, {})
        t.add_row(
            wid,
            f"{u.get('mean_util',0):.3f}",
            f"{u.get('ewma_util',0):.3f}",
            f"{p.get('avg_profit',0):.2f}",
            f"{p.get('total_profit',0):.2f}",
            f"{p.get('tokens_earned',0):.2f}",
        )
    c.print(t)

    if cons.get("top_clusters"):
        tc = Table(title="Top Clusters (volume, distance)")
        for col in ["vol_bin","dist_bin","dominant","consistency","n"]:
            tc.add_column(col)
        for row in cons["top_clusters"]:
            cl = row["cluster"]
            tc.add_row(str(cl["vol_bin"]), str(cl["dist_bin"]),
                       row["dominant_warehouse"], f"{row['consistency']:.3f}", str(row["n"]))
        c.print(tc)

def main():
    import argparse
    ap = argparse.ArgumentParser(description="WMS Metrics Dashboard (print to terminal)")
    ap.add_argument("--env-file", default=None, help="path to .env")
    ap.add_argument("--from-ts", type=int, default=None, help="start epoch (inclusive)")
    ap.add_argument("--to-ts", type=int, default=None, help="end epoch (inclusive)")
    ap.add_argument("--format", choices=["plain","table","json"], default="table", help="output format")
    ap.add_argument("--brief", action="store_true", help="hide long cluster table")
    args = ap.parse_args()

    _load_env(args.env_file)

    kpis = compute_kpis(from_ts=args.from_ts, to_ts=args.to_ts, brief=args.brief)

    if args.format == "json":
        print(json.dumps(kpis, ensure_ascii=False, indent=2))
    elif args.format == "plain":
        _print_plain(kpis)
    else:
        _print_table(kpis)

# ===== end add =====
