# core/pricing.py
import os
from typing import Dict, Tuple
import os


def load_rate() -> Dict:
    """Rate card กลาง (ยังใช้ได้ร่วมกับ per-warehouse ถ้ามีในอนาคต)"""
    return {
        "handling_per_cbm": float(os.getenv("HANDLING_PER_CBM", 5.0)),
        "storage_per_cbm_day": float(os.getenv("STORAGE_PER_CBM_DAY", 0.8)),
        "km_cost": float(os.getenv("KM_COST", 10.0)),
        "min_margin": float(os.getenv("MIN_MARGIN", 0.05)),
        "surcharge": float(os.getenv("SURCHARGE", 0.0)),
    }

def compute_cost(
    volume_cbm: float,
    duration_days: int,
    km: float,
    utilization: float,
    rate: Dict | None = None,
) -> float:
    """
    ต้นทุนจริง = handling + storage + km + opportunity_cost(utilization)
    opportunity_cost ~ coeff * utilization * volume_cbm
    """
    r = rate or load_rate()
    base = (
        r["handling_per_cbm"] * volume_cbm
        + r["storage_per_cbm_day"] * volume_cbm * duration_days
        + r["km_cost"] * km
    )
    # โอกาสเสียโอกาส (ยิ่ง utilization สูง ยิ่งแพง)
    opp_coeff = float(os.getenv("OPPORTUNITY_COEFF", 0.15))
    opp = opp_coeff * max(0.0, min(1.0, utilization)) * volume_cbm
    return base + opp

def price_from_cost(cost: float, rate: Dict | None = None) -> Tuple[float, float]:
    """
    แปลง cost -> price ด้วย min_margin + surcharge
    คืน (price, margin_ratio)
    """
    r = rate or load_rate()
    price = cost * (1.0 + r["min_margin"]) + r["surcharge"]
    margin = 0.0 if price <= 0 else (price - cost) / price
    return price, margin

def quote_price(
    volume_cbm: float,
    duration_days: int,
    km: float,
    utilization: float,
    rate: Dict | None = None,
) -> Dict:
    """คำนวณราคาพร้อมรายละเอียด ติดไปกับ candidate ใช้ใน scoring ได้"""
    r = rate or load_rate()
    cost = compute_cost(volume_cbm, duration_days, km, utilization, r)
    price, margin = price_from_cost(cost, r)

    # surge ราคาตาม utilization (ออปชัน)
    surge_k = float(os.getenv("SURGE_K", 0.0))   # 0.0 = ปิด
    if surge_k > 0:
        surge = 1.0 + surge_k * max(0.0, utilization - 0.7)  # เริ่ม surge หลัง 70%
        price *= surge
        margin = 0.0 if price <= 0 else (price - cost) / price

    return {
        "cost": round(cost, 2),
        "price_amount": round(price, 2),
        "margin": round(margin, 4),
        "profit": round(price - cost, 2),
    }

# --- Backward-compat wrapper for old callers ---
def price(volume_cbm: float, km: float, duration_days: int, rate: dict | None = None) -> float:
    """
    Legacy shim so older code that imports `price` keeps working.
    Returns only the quoted price amount (not the cost/margin breakdown).
    """
    if rate is None:
        rate = load_rate()
    q = quote_price(
        volume_cbm=float(volume_cbm),
        duration_days=int(duration_days),
        km=float(km),
        utilization=0.0,   # อย่าพิมพ์เป็น util=
        rate=rate,
    )
    return float(q["price_amount"])


