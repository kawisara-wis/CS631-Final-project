# agents/pricing_agent_llm.py
import os, random
from typing import Dict, Any

from core.llm import call_llm

# ===== Pricing / Cost Params (อ่านจาก env) =====
MIN_MARGIN            = float(os.getenv("MIN_MARGIN", "0.05"))
TARGET_UTIL           = float(os.getenv("TARGET_UTIL", "0.7"))
BID_UTIL_K            = float(os.getenv("BID_UTIL_K", "1.0"))
BID_KM_K              = float(os.getenv("BID_KM_K", "0.02"))
BID_JITTER            = float(os.getenv("BID_JITTER", "0.005"))
OPPORTUNITY_COEFF     = float(os.getenv("OPPORTUNITY_COEFF", "0.15"))
SURCHARGE             = float(os.getenv("SURCHARGE", "0"))
KM_COST               = float(os.getenv("KM_COST", "10"))
HANDLING_PER_CBM      = float(os.getenv("HANDLING_PER_CBM", "5"))
STORAGE_PER_CBM_DAY   = float(os.getenv("STORAGE_PER_CBM_DAY", "0.8"))

USE_LLM_PRICING = os.getenv("USE_LLM_PRICING", "0") == "1"
ALPHA_MARGIN    = float(os.getenv("ALPHA_MARGIN", "0.10"))  # margin push per util overflow
BETA_AR         = float(os.getenv("BETA_AR", "0.05"))       # bid factor sensitivity by accept_rate

def _adj_margin(base_margin: float, ewma_util: float) -> float:
    overflow = max(0.0, ewma_util - TARGET_UTIL)
    return base_margin + ALPHA_MARGIN * overflow + OPPORTUNITY_COEFF * overflow

def _adj_bid_factor(base_factor: float, accept_rate: float) -> float:
    return base_factor * (1.0 + BETA_AR * (accept_rate - 0.5))

def _llm_margin_hint(context: Dict[str, Any]) -> float:
    """
    ให้ LLM ช่วย suggest margin_delta (เพิ่ม/ลด) ในช่วง [-0.05, 0.08]
    """
    if not USE_LLM_PRICING:
        return 0.0
    prompt = f"""You are a pricing strategist.
Context: {context}
Suggest an extra `margin_delta` in [-0.05, 0.08] to maximize long-term profit while keeping win-rate healthy.
Return ONLY a number."""
    out = call_llm(prompt).strip()
    try:
        val = float(out)
        return max(-0.05, min(0.08, val))
    except Exception:
        return 0.0

class PricingAgent:
    """
    สร้าง “แคนดิเดต” รายคลัง: คำนวณ cost / price / profit / margin
    ใส่แนะนำนโยบายจาก LLM (margin_delta) ถ้าเปิด
    """
    def quote_candidate(
        self,
        offer: Dict[str, Any],
        wh: Dict[str, Any],
        route_info: Dict[str, float],
        hist_row: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        km = float(route_info.get("km") or 0.0)
        vol = float(offer["volume_cbm"])
        duration_days = float(offer.get("duration_days", 0) or 0)
        used = float(wh.get("used_cbm", 0.0))
        cap  = float(wh.get("capacity_cbm", 1.0))
        util_after = (used + vol) / max(1.0, cap)

        # base cost
        cost = (
            KM_COST * km
            + HANDLING_PER_CBM * vol
            + STORAGE_PER_CBM_DAY * vol * duration_days
            + SURCHARGE
        )

        # history
        accept_rate = float(hist_row.get("accept_rate", 0.0)) if hist_row else 0.0
        ewma_util   = float(hist_row.get("ewma_util", 0.0)) if hist_row else 0.0

        # margin & bid factor
        margin_eff = _adj_margin(MIN_MARGIN, ewma_util)
        margin_eff += _llm_margin_hint({
            "volume": vol, "km": km,
            "util_after": util_after, "accept_rate": accept_rate,
            "ewma_util": ewma_util,
        })

        base_price = cost / max(1e-6, (1.0 - margin_eff))
        base_factor = 1.0 + BID_UTIL_K * max(0.0, util_after - TARGET_UTIL) + BID_KM_K * km
        bid_factor  = _adj_bid_factor(base_factor, accept_rate)

        price = base_price * bid_factor * (1.0 + random.uniform(-BID_JITTER, BID_JITTER))
        profit = max(0.0, price - cost)
        margin = profit / max(1e-6, price)

        available = max(0.0, cap - used)

        return {
            "warehouse_id": wh["warehouse_id"],
            "route": route_info,
            "available_cbm": available,
            "utilization": util_after,
            "sla_fit": 1.0,
            "price_amount": round(price, 2),
            "cost": round(cost, 2),
            "profit": round(profit, 2),
            "margin": round(margin, 4),

            # สำหรับขั้นตอนจัดอันดับใน dispatcher
            "_raw_price": float(price),
            "_raw_km": float(km),
            "_wh": wh,
        }
