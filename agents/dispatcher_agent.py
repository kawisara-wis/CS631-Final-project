# agents/dispatcher_agent.py
import os, random
from math import isfinite
from typing import Dict, Any, List

from core.llm import call_llm
from core.db import compute_warehouse_stats
from agents.location_agent_llm import LocationAgent
from agents.pricing_agent_llm import PricingAgent
from agents.warehouse_agent_llm import WarehouseAgent

# ===== Scoring Weights =====
W_PROFIT   = float(os.getenv("W_PROFIT", "0.6"))
W_UTILBAL  = float(os.getenv("W_UTILBAL", "0.2"))
W_DISTANCE = float(os.getenv("W_DISTANCE", "0.1"))
W_SLA      = float(os.getenv("W_SLA", "0.05"))
W_PRICE    = float(os.getenv("W_PRICE", "0.05"))
W_SPEC     = float(os.getenv("W_SPEC", "0.05"))

TARGET_UTIL = float(os.getenv("TARGET_UTIL", "0.7"))

# ===== Exploration =====
EPSILON       = float(os.getenv("EPSILON", "0.08"))  # โอกาสสุ่มเลือก
EXPL_TOPK     = int(os.getenv("EXPL_TOPK", "3"))
EXPL_WEIGHT   = os.getenv("EXPL_WEIGHT", "distance*avail")

USE_LLM_EXPLAIN = os.getenv("USE_LLM_EXPLAIN", "0") == "1"
HISTORY_DAYS    = int(os.getenv("HISTORY_DAYS", "14"))

_loc  = LocationAgent()
_price= PricingAgent()
_wh   = WarehouseAgent()

_HIST = None
def _hist():
    global _HIST
    if _HIST is None:
        try:
            _HIST = compute_warehouse_stats(HISTORY_DAYS)
        except Exception:
            _HIST = {}
    return _HIST

def _util_penalty(util: float) -> float:
    if util <= TARGET_UTIL:
        return 1.0
    overflow = util - TARGET_UTIL
    return max(0.0, 1.0 - 0.8 * overflow)  # ลงโทษแรงขึ้นเมื่อเกินเป้า

def _price_rank_score(prices: List[float], val: float) -> float:
    if not prices:
        return 0.5
    pmin, pmax = min(prices), max(prices)
    if pmax == pmin:
        return 0.5
    # ถูกสุด = 1.0
    return (pmax - val) / (pmax - pmin)

def _llm_explain(decision_payload: Dict[str, Any]) -> str:
    if not USE_LLM_EXPLAIN:
        return ""
    prompt = f"""You are a senior WMS planner. Summarize why the winner was chosen.
Focus on price ranking, profit, distance, utilization target, diversity cooldown, and specialization match.
Keep under 120 words as bullet points.
Payload: {decision_payload}"""
    return call_llm(prompt).strip()

def _candidate_reason(c: Dict[str, Any], hist_row: Dict[str, Any] | None, extra: Dict[str, Any] | None = None):
    r = c.get("route", {}) or {}
    why = {
        "warehouse_id": c["warehouse_id"],
        "distance_km": r.get("km"),
        "utilization": c.get("utilization"),
        "availability_cbm": c.get("available_cbm"),
        "price": c.get("price_amount"),
        "cost": c.get("cost"),
        "profit": c.get("profit"),
        "margin": c.get("margin"),
        "score_components": {
            "profit": c.get("profit_score"),
            "price":  c.get("price_score"),
            "distance": c.get("distance_score"),
            "sla": c.get("sla_score"),
            "util_bal": c.get("util_score"),
            "util_penalty": c.get("util_penalty"),
            "spec": c.get("spec_score"),
            "diversity_penalty": c.get("diversity_penalty"),
        },
        "history": {
            "accept_rate": (hist_row or {}).get("accept_rate"),
            "ewma_util":   (hist_row or {}).get("ewma_util"),
            "avg_profit":  (hist_row or {}).get("avg_profit"),
            "avg_margin":  (hist_row or {}).get("avg_margin"),
            "avg_price":   (hist_row or {}).get("avg_price"),
            "wins":        (hist_row or {}).get("wins"),
            "bids":        (hist_row or {}).get("bids"),
        }
    }
    if extra:
        why.update(extra)
    return why

def run(offer: Dict[str, Any]) -> Dict[str, Any]:
    # 1) Geocode ถ้าจำเป็น
    if not (offer.get("origin_lat") and offer.get("origin_lng")):
        lat, lng = _loc.geocode(offer.get("origin_address"))
    else:
        lat, lng = float(offer["origin_lat"]), float(offer["origin_lng"])

    # 2) ดึงคลัง + สถิติย้อนหลัง
    whs = _wh.get_active()
    hist = _hist()
    streaks = _wh.streaks()

    # 3) สร้าง candidates (pricing + spec)
    cands = []
    for w in whs:
        rt = _loc.route(lat, lng, w["lat"], w["lng"])      # dict {"km","minutes"}
        wid = w["warehouse_id"]
        cand = _price.quote_candidate(
            offer=offer,
            wh=w,
            route_info=rt,
            hist_row=hist.get(wid)
        )
        # spec score (LLM-able)
        spec = _wh.spec_score(offer, w)
        cand["spec_score"] = round(float(spec), 4)

        cands.append(cand)

    # 4) จัดอันดับ + คำนวณคะแนนรวม
    prices = [c["_raw_price"] for c in cands] if cands else []
    scored = []
    for c in cands:
        km  = float(c["_raw_km"])
        price_score   = _price_rank_score(prices, c["_raw_price"])
        profit_score  = min(1.0, (c["profit"] / 200.0) if isfinite(c["profit"]) else 0.0)
        distance_score= 1.0 / (1.0 + km)
        sla_score     = 1.0 if c["sla_fit"] else 0.0
        util_score    = max(0.0, 1.0 - abs(c["utilization"] - TARGET_UTIL))
        util_pen      = _util_penalty(c["utilization"])

        div_pen, st  = _wh.diversity_penalty(c["warehouse_id"], streaks)

        base_score = (
            W_PROFIT   * profit_score +
            W_PRICE    * price_score  +
            W_DISTANCE * distance_score +
            W_SLA      * sla_score +
            W_UTILBAL  * util_score +
            W_SPEC     * c["spec_score"]
        )
        score = base_score * util_pen * div_pen

        c["profit_score"]      = round(profit_score, 4)
        c["price_score"]       = round(price_score, 4)
        c["distance_score"]    = round(distance_score, 4)
        c["sla_score"]         = sla_score
        c["util_score"]        = round(util_score, 4)
        c["util_penalty"]      = round(util_pen, 4)
        c["diversity_penalty"] = round(div_pen, 4)
        c["win_streak"]        = st
        c["score"]             = round(float(score), 6)
        scored.append(c)

    # 5) เลือกผู้ชนะ (epsilon-greedy exploration)
    scored.sort(key=lambda x: x["score"], reverse=True)
    winner = scored[0] if scored else None
    exploration = False
    if scored and random.random() < EPSILON:
        exploration = True
        k = min(EXPL_TOPK, len(scored))
        pool = scored[:k]
        weights = []
        for c in pool:
            if EXPL_WEIGHT == "distance*avail":
                w = max(1e-9, c["distance_score"] * (c["available_cbm"] + 1.0))
            elif EXPL_WEIGHT == "score":
                w = max(1e-9, c["score"])
            else:
                w = 1.0
            weights.append(w)
        s = sum(weights)
        r = random.random() * s
        cur = 0.0
        for c, w in zip(pool, weights):
            cur += w
            if r <= cur:
                winner = c
                break

    # 6) อธิบายเหตุผล (มี LLM summary ถ้าเปิด)
    reasons_per_candidate = []
    for c in scored:
        reasons_per_candidate.append(
            _candidate_reason(c, hist.get(c["warehouse_id"]), extra={"streak_used": c.get("win_streak")})
        )

    if winner:
        reason = {
            "type": "history_aware_selection",
            "chosen_warehouse": winner["warehouse_id"],
            "exploration": exploration,
            "why": [
                f"คะแนนรวมหลังปรับ: base_score × util_penalty({winner['util_penalty']}) × diversity_penalty({winner['diversity_penalty']}) = {winner['score']:.3f}",
                f"price_score(ภายในแบทช์)={winner['price_score']} profit={winner['profit']} margin={winner['margin']}",
                f"ระยะทาง {winner['route']['km']} km → distance_score={winner['distance_score']}",
                f"spec_score={winner['spec_score']} และประวัติ/สตรีคส่งผลต่อ fairness",
            ],
            "candidates_explained": reasons_per_candidate,
        }
        # LLM summary (ถ้าเปิด)
        if USE_LLM_EXPLAIN:
            reason["llm_summary"] = _llm_explain({
                "winner": winner, "top3": scored[:3],
                "weights": {
                    "W_PROFIT": W_PROFIT, "W_PRICE": W_PRICE, "W_DISTANCE": W_DISTANCE,
                    "W_UTILBAL": W_UTILBAL, "W_SPEC": W_SPEC
                }
            })
        decision = {
            "accept": True,
            "chosen_warehouse": winner["warehouse_id"],
            "reason": reason,
            "priced_amount": winner["price_amount"],
            "candidates": scored,
        }
    else:
        decision = {
            "accept": False,
            "chosen_warehouse": None,
            "reason": {"type": "no_candidates", "why": ["ไม่พบผู้สมัครที่ผ่านเกณฑ์"]},
            "priced_amount": None,
            "candidates": [],
        }
    return decision
