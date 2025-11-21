# core/scoring.py
from __future__ import annotations
import os
from typing import List, Dict, Optional

def _f(v: float) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0

def _w(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default

def _norm_min_better(x: float, lo: float, hi: float) -> float:
    """ยิ่งต่ำยิ่งดี -> สเกลเป็น [0,1]"""
    if hi <= lo:
        return 1.0
    return max(0.0, min(1.0, (hi - x) / (hi - lo)))

def _norm_max_better(x: float, lo: float, hi: float) -> float:
    """ยิ่งสูงยิ่งดี -> สเกลเป็น [0,1]"""
    if hi <= lo:
        return 1.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))

def _util_balance_score(util: float, target: float) -> float:
    """ใกล้ TARGET_UTIL ยิ่งดี: 1 - |u - t|/t  (clamp 0..1)"""
    t = max(1e-6, target)
    return max(0.0, min(1.0, 1.0 - abs(util - target) / t))

def compute_scores(
    candidates: List[Dict],
    *,
    offer: Optional[Dict] = None,
    weights: Optional[Dict[str, float]] = None,
) -> List[Dict]:
    """
    เติม sub-scores และ score รวมให้แต่ละ candidate แล้วคืนรายการเรียงจากคะแนนสูง -> ต่ำ

    ใช้ค่าน้ำหนักจาก ENV (หรืออาร์กิวเมนต์ weights):
      W_PROFIT, W_UTILBAL, W_DISTANCE, W_SLA, W_PRICE
      TARGET_UTIL

    Fields ที่คาดหวังใน candidate:
      - route.km
      - price_amount, cost (ถ้าไม่มี cost จะประมาณจาก margin ถ้ามี)
      - utilization
      - available_cbm
      - sla_fit (0..1)

    ถ้ามี offer จะใช้ offer["volume_cbm"] เพื่อคำนวณ availability_score
    """

    if not candidates:
        return []

    # น้ำหนัก
    W_PROFIT   = _w("W_PROFIT",   0.6)
    W_UTILBAL  = _w("W_UTILBAL",  0.2)
    W_DISTANCE = _w("W_DISTANCE", 0.1)
    W_SLA      = _w("W_SLA",      0.05)
    W_PRICE    = _w("W_PRICE",    0.05)
    TARGET_UTIL = _w("TARGET_UTIL", 0.7)

    if weights:
        W_PROFIT   = weights.get("profit",   W_PROFIT)
        W_UTILBAL  = weights.get("utilbal",  W_UTILBAL)
        W_DISTANCE = weights.get("distance", W_DISTANCE)
        W_SLA      = weights.get("sla",      W_SLA)
        W_PRICE    = weights.get("price",    W_PRICE)

    # ดึงค่าที่ต้องใช้สำหรับ normalization
    kms      = [_f(c.get("route", {}).get("km", 0.0)) for c in candidates]
    prices   = [_f(c.get("price_amount", 0.0)) for c in candidates]

    # profit = price - cost  (ถ้าไม่มี cost พยายามอนุมานจาก margin)
    profits  = []
    for c in candidates:
        price = _f(c.get("price_amount", 0.0))
        cost  = c.get("cost", None)
        if cost is None:
            margin = c.get("margin", None)
            if margin is not None:
                # price = cost / (1 - margin)  -> cost = price * (1 - margin)
                try:
                    cost = float(price) * (1.0 - float(margin))
                except Exception:
                    cost = None
        if cost is None:
            cost = max(0.0, price * 0.95)  # กันพัง: สมมุติต้นทุนสูงเกือบราคา
        c["cost"] = _f(cost)
        profits.append(max(0.0, price - c["cost"]))

    util_list = [_f(c.get("utilization", 0.0)) for c in candidates]
    sla_list  = [_f(c.get("sla_fit", 1.0)) for c in candidates]

    km_lo, km_hi       = min(kms), max(kms)
    price_lo, price_hi = min(prices), max(prices)
    prof_lo, prof_hi   = min(profits), max(profits)

    # volume สำหรับ availability
    vol_need = None
    if offer:
        try:
            vol_need = float(offer.get("volume_cbm"))
        except Exception:
            vol_need = None

    ranked: List[Dict] = []
    for idx, c in enumerate(candidates):
        km   = kms[idx]
        price = prices[idx]
        profit = profits[idx]
        util  = util_list[idx]
        sla   = sla_list[idx]

        # sub-scores
        distance_score = _norm_min_better(km, km_lo, km_hi)         # ใกล้ดีกว่า
        price_score    = _norm_min_better(price, price_lo, price_hi) # ถูกดีกว่า
        profit_score   = _norm_max_better(profit, prof_lo, prof_hi)  # กำไรสูงดีกว่า
        util_score     = _util_balance_score(util, TARGET_UTIL)      # ใกล้ target ดีกว่า
        sla_score      = max(0.0, min(1.0, sla))                     # เชื่อจากข้อมูล (0..1)

        # availability_score: ถ้ามี vol_need ใช้ ratio, ไม่มีก็ 1.0
        if vol_need and vol_need > 0:
            avail_cbm = _f(c.get("available_cbm", 0.0))
            availability_score = max(0.0, min(1.0, avail_cbm / vol_need))
        else:
            availability_score = 1.0

        # รวมคะแนน (availability เป็นตัวคูณ safety gate)
        base_score = (
            W_PROFIT   * profit_score +
            W_UTILBAL  * util_score   +
            W_DISTANCE * distance_score +
            W_SLA      * sla_score    +
            W_PRICE    * price_score
        )
        final_score = base_score * availability_score

        out = dict(c)
        out.update({
            "distance_score": round(distance_score, 4),
            "price_score":    round(price_score, 4),
            "profit_score":   round(profit_score, 4),
            "util_score":     round(util_score, 4),
            "sla_score":      round(sla_score, 4),
            "availability_score": round(availability_score, 4),
            "score": round(float(final_score), 6),
        })
        ranked.append(out)

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked
