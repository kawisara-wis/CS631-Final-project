# agents/location_agent_llm.py
import os
from typing import Tuple, Dict, Any

from core.llm import call_llm
from core.location import geocode as _geo, route as _route

USE_LLM_LOCATION = os.getenv("USE_LLM_LOCATION", "0") == "0"

def _llm_normalize_address(addr: str) -> str:
    """
    ใช้ LLM ช่วย normalize/clean ที่อยู่ก่อน geocode
    ถ้าไม่เปิดใช้ LLM จะคืน addr เดิม
    """
    if not USE_LLM_LOCATION or not addr:
        return addr
    prompt = f"""You are an address normalizer for geocoding.
Given the address below, clean and standardize it for Google Maps geocoding.
Address: {addr}
Return ONLY the cleaned address, no extra words."""
    txt = call_llm(prompt).strip()
    return txt or addr

def _norm_route(rt) -> Dict[str, float]:
    """
    normalize ผลลัพธ์เส้นทางให้เป็น dict {"km":..,"minutes":..}
    รองรับทั้ง dict และ tuple/list
    """
    if isinstance(rt, dict):
        return {"km": float(rt.get("km") or 0.0),
                "minutes": float(rt.get("minutes") or 0.0)}
    if isinstance(rt, (tuple, list)) and len(rt) >= 2:
        return {"km": float(rt[0] or 0.0), "minutes": float(rt[1] or 0.0)}
    return {"km": 0.0, "minutes": 0.0}

class LocationAgent:
    """ตัวกลางเรื่อง location: geocode + route พร้อมจุดเสียบ LLM"""
    def geocode(self, origin_address: str) -> Tuple[float, float]:
        addr = _llm_normalize_address(origin_address) if origin_address else origin_address
        lat, lng = _geo(addr)
        return float(lat), float(lng)

    def route(self, a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> Dict[str, float]:
        rt = _route(a_lat, a_lng, b_lat, b_lng)
        return _norm_route(rt)
