# agents/warehouse_agent_llm.py
import os
from typing import Dict, Any, List, Tuple

from core.llm import call_llm
from core.db import (
    list_active_warehouses,
    capacity_available,
    get_recent_decisions,
)
USE_LLM_WAREHOUSE = os.getenv("USE_LLM_WAREHOUSE", "0") == "1"

# diversity/cooldown
COOLDOWN_LOOKBACK = int(os.getenv("COOLDOWN_LOOKBACK", "30"))
COOLDOWN_GAMMA    = float(os.getenv("COOLDOWN_GAMMA", "0.05"))
COOLDOWN_CAP      = int(os.getenv("COOLDOWN_CAP", "5"))

# specialization
SPEC_MATCH_FULL = float(os.getenv("SPEC_MATCH_FULL", "1.0"))
SPEC_MATCH_PART = float(os.getenv("SPEC_MATCH_PART", "0.9"))
SPEC_MATCH_NONE = float(os.getenv("SPEC_MATCH_NONE", "0.8"))

def _llm_spec_score(offer_tags: List[str], wh_tags: List[str]) -> float:
    """
    ให้ LLM ประเมินความเข้ากันได้ของความต้องการ vs ความสามารถ ของคลัง
    ควรคืนค่า [0.0, 1.0]
    """
    if not USE_LLM_WAREHOUSE:
        # rule-based ง่าย ๆ
        if not offer_tags:
            return 1.0
        if not wh_tags:
            return SPEC_MATCH_PART
        inter = set(offer_tags) & set(wh_tags)
        if len(inter) == len(set(offer_tags)):
            return SPEC_MATCH_FULL
        if inter:
            return SPEC_MATCH_PART
        return SPEC_MATCH_NONE

    prompt = f"""You are a logistics capability matcher.
Offer requires tags: {offer_tags}
Warehouse provides tags: {wh_tags}
Rate compatibility in [0.0, 1.0]. Return ONLY the number."""
    out = call_llm(prompt).strip()
    try:
        val = float(out)
        return max(0.0, min(1.0, val))
    except Exception:
        # fallback เป็น rule-based
        if not offer_tags:
            return 1.0
        if not wh_tags:
            return SPEC_MATCH_PART
        inter = set(offer_tags) & set(wh_tags)
        if len(inter) == len(set(offer_tags)):
            return SPEC_MATCH_FULL
        if inter:
            return SPEC_MATCH_PART
        return SPEC_MATCH_NONE

def _winner_streaks() -> Dict[str, int]:
    """
    นับสตรีคของผู้ชนะล่าสุด (ล่าสุดเรียงจากใหม่ไปเก่า)
    ใช้กับ cooldown penalty
    """
    try:
        rows = get_recent_decisions(COOLDOWN_LOOKBACK) or []
    except Exception:
        rows = []
    streak = {}
    last = None
    for r in sorted(rows, key=lambda x: x.get("ts", 0), reverse=True):
        wid = (r.get("decision") or {}).get("chosen_warehouse")
        if not wid:
            break
        if last is None or wid == last:
            streak[wid] = streak.get(wid, 0) + 1
            last = wid
        else:
            break
    return streak

def _diversity_penalty(wid: str, streaks: Dict[str, int]) -> Tuple[float, int]:
    st = min(COOLDOWN_CAP, streaks.get(wid, 0))
    return (max(0.7, 1.0 - COOLDOWN_GAMMA * st), st)

class WarehouseAgent:
    """
    รวมฟังก์ชันเกี่ยวกับคลัง: ดึงคลัง, spec matching (LLM point), และ diversity penalty
    """
    def get_active(self) -> List[Dict[str, Any]]:
        return list_active_warehouses()

    def spec_score(self, offer: Dict[str, Any], wh: Dict[str, Any]) -> float:
        req_tags = list(((offer.get("requirements", {}) or {}).get("tags", []) or []))
        wh_tags  = list((wh.get("tags", []) or []))
        return _llm_spec_score(req_tags, wh_tags)

    def diversity_penalty(self, wid: str, streaks: Dict[str, int]) -> Tuple[float, int]:
        return _diversity_penalty(wid, streaks)

    def streaks(self) -> Dict[str, int]:
        return _winner_streaks()
