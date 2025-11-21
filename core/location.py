# core/location.py
import os, math, time, json
from typing import Tuple, Optional
from urllib.parse import urlencode
import requests

# ใช้ cache กลางจาก core.db (ทำงานได้ทั้ง sqlite/mongo)
from .db import load_distance_cache, save_distance_cache

# --- ENV ---
USE_REAL_ROUTE = os.getenv("USE_REAL_ROUTE", "0") == "1"

# Google Maps
GOOGLE_API_KEY   = os.getenv("GOOGLE_API_KEY")
GOOGLE_REGION    = os.getenv("GOOGLE_REGION", "th")
GOOGLE_LANGUAGE  = os.getenv("GOOGLE_LANGUAGE", "th")

# OpenRouteService (ตัวเลือกสำรอง ถ้ามีคีย์)
ORS_API_KEY      = os.getenv("ORS_API_KEY")

# ค่า default หากไม่ได้ใช้ API จริง
ASSUMED_KMH      = float(os.getenv("ASSUMED_KMH", "40"))   # ความเร็วเฉลี่ยถนนเมือง
ROUTE_CACHE_TTL  = int(os.getenv("ROUTE_CACHE_TTL_SEC", str(7*24*3600)))  # 7 วัน

# ---------------- Utils ----------------
def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    return R * (2*math.atan2(math.sqrt(a), math.sqrt(1-a)))

def _cache_key(lat1: float, lng1: float, lat2: float, lng2: float) -> str:
    return f"{round(lat1,6)},{round(lng1,6)}|{round(lat2,6)},{round(lng2,6)}"

# ---------------- Geocode ----------------
def geocode(address: str) -> Tuple[float, float]:
    """
    คืน (lat, lng) จากที่อยู่
    ลำดับความพยายาม: Google → ORS Nominatim → error
    """
    if not address or not address.strip():
        raise ValueError("geocode: address is empty")

    # 1) Google Geocoding API
    if GOOGLE_API_KEY:
        try:
            params = {
                "address": address,
                "key": GOOGLE_API_KEY,
                "region": GOOGLE_REGION,
                "language": GOOGLE_LANGUAGE,
            }
            url = f"https://maps.googleapis.com/maps/api/geocode/json?{urlencode(params)}"
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            data = r.json()
            if data.get("status") == "OK" and data.get("results"):
                loc = data["results"][0]["geometry"]["location"]
                return float(loc["lat"]), float(loc["lng"])
        except Exception as e:
            print(f"[WARN] geocode(Google) failed: {e}")

    # 2) ORS (Nominatim-like) — ต้องมี ORS_API_KEY ถึงจะขอ geocode ได้ผ่าน ORS geocoding endpoint
    if ORS_API_KEY:
        try:
            # OpenRouteService Geocoding (Pelias)
            url = "https://api.openrouteservice.org/geocode/search"
            headers = {"Authorization": ORS_API_KEY}
            params = {"text": address, "size": 1, "lang": GOOGLE_LANGUAGE}
            r = requests.get(url, headers=headers, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            feats = (data or {}).get("features") or []
            if feats:
                coords = feats[0]["geometry"]["coordinates"]  # [lng, lat]
                return float(coords[1]), float(coords[0])
        except Exception as e:
            print(f"[WARN] geocode(ORS) failed: {e}")

    # 3) หมดหนทาง
    raise RuntimeError("geocode failed: no provider returned a result")

# ---------------- Route (distance & time) ----------------
def route(lat1: float, lng1: float, lat2: float, lng2: float) -> Tuple[float, float]:
    """
    คืน (km, minutes) จากต้นทาง → ปลายทาง
    ลำดับความพยายาม: cache → ผู้ให้บริการจริง (Google/ORS) → haversine fallback
    """
    # 0) เช็ค cache ก่อน
    key = _cache_key(lat1, lng1, lat2, lng2)
    cached = load_distance_cache(key)
    if cached:
        return float(cached[0]), float(cached[1])

    km: Optional[float] = None
    minutes: Optional[float] = None

    # 1) ผู้ให้บริการจริง (ถ้าเปิด USE_REAL_ROUTE)
    if USE_REAL_ROUTE:
        # 1.1) Google Directions API
        if GOOGLE_API_KEY:
            try:
                params = {
                    "origin": f"{lat1},{lng1}",
                    "destination": f"{lat2},{lng2}",
                    "key": GOOGLE_API_KEY,
                    "region": GOOGLE_REGION,
                    "language": GOOGLE_LANGUAGE,
                    "mode": "driving",
                }
                url = f"https://maps.googleapis.com/maps/api/directions/json?{urlencode(params)}"
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                data = r.json()
                routes = data.get("routes") or []
                if routes and routes[0].get("legs"):
                    leg = routes[0]["legs"][0]
                    km = (leg["distance"]["value"] or 0) / 1000.0
                    minutes = (leg["duration"]["value"] or 0) / 60.0
            except Exception as e:
                print(f"[WARN] route(Google) failed: {e}")

        # 1.2) ORS Directions (ถ้ามีคีย์และ Google ไม่สำเร็จ)
        if (km is None or minutes is None) and ORS_API_KEY:
            try:
                url = "https://api.openrouteservice.org/v2/directions/driving-car"
                headers = {
                    "Authorization": ORS_API_KEY,
                    "Content-Type": "application/json",
                }
                body = {
                    "coordinates": [[float(lng1), float(lat1)], [float(lng2), float(lat2)]],
                    "units": "km",
                    "language": GOOGLE_LANGUAGE,
                }
                r = requests.post(url, headers=headers, data=json.dumps(body), timeout=30)
                r.raise_for_status()
                data = r.json()
                summary = (data.get("routes") or [{}])[0].get("summary") or {}
                km = float(summary.get("distance", 0.0))
                sec = float(summary.get("duration", 0.0))
                minutes = sec / 60.0
            except Exception as e:
                print(f"[WARN] route(ORS) failed: {e}")

    # 2) Fallback: haversine + สมมุติเวลา
    if km is None or minutes is None:
        km = _haversine_km(lat1, lng1, lat2, lng2)
        # สมมุติเวลาขับรถจากความเร็วเฉลี่ย
        minutes = (km / max(ASSUMED_KMH, 1e-6)) * 60.0

    # 3) บันทึก cache
    try:
        save_distance_cache(key, lat1, lng1, lat2, lng2, float(km), float(minutes), ttl_sec=ROUTE_CACHE_TTL)
    except Exception as e:
        print(f"[WARN] save_distance_cache failed: {e}")

    return float(km), float(minutes)
