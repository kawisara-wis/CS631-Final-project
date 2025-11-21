# core/db.py
import os, time, json
from typing import List, Dict, Optional, Any

BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()

# -----------------------------
# Common helpers (shared API)
# -----------------------------
def capacity_available(wh_row: dict) -> float:
    try:
        cap = float(wh_row.get("capacity_cbm", 0.0))
        used = float(wh_row.get("used_cbm", 0.0))
        return max(0.0, cap - used)
    except Exception:
        return 0.0


# =========================
# SQLite backend
# =========================
if BACKEND == "sqlite":
    import sqlite3

    DB_PATH = os.getenv("DB_PATH", "wms.sqlite3")

    def get_conn():
        return sqlite3.connect(DB_PATH)

    def init_db():
        con = get_conn(); cur = con.cursor()
        # warehouses
        cur.execute("""
        CREATE TABLE IF NOT EXISTS warehouses(
            warehouse_id TEXT PRIMARY KEY,
            name TEXT,
            lat REAL,
            lng REAL,
            capacity_cbm REAL,
            used_cbm REAL,
            service_limit REAL,
            status TEXT
        )""")
        # distance cache
        cur.execute("""
        CREATE TABLE IF NOT EXISTS distance_cache(
            key TEXT PRIMARY KEY,
            a_lat REAL, a_lng REAL, b_lat REAL, b_lng REAL,
            km REAL, minutes REAL, expires_at INTEGER
        )""")
        # decision runs (app.py)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS decision_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER,
            offer_json TEXT,
            decision_json TEXT,
            meta_json TEXT
        )""")
        # case runs (inspect_cases.py)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS case_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER,
            rows_json TEXT,
            meta_json TEXT
        )""")
        con.commit(); con.close()

    def seed_warehouses():
        force = os.getenv("FORCE_RESEED") == "1"
        con = get_conn(); cur = con.cursor()
        rows = cur.execute("SELECT COUNT(*) FROM warehouses").fetchone()[0]
        if force:
            cur.execute("DELETE FROM warehouses")
        elif rows and rows >= 5:
            con.close(); return

        data = [
            ("W1","Bangkok DC1",13.649,100.647,10000.0,2000.0,200.0,"ACTIVE"),
            ("W2","Bangkok DC2",13.651,100.637,15000.0,2200.0,180.0,"ACTIVE"),
            ("W3","Bangkok DC3",13.655,100.634,10000.0,1500.0,200.0,"ACTIVE"),
            ("W4","Bangkok DC4",13.627,100.734,15000.0,2100.0,200.0,"ACTIVE"),
            ("W5","Bangkok DC5",13.618,100.736,10000.0,1800.0,180.0,"ACTIVE"),
        ]
        cur.executemany(
            """INSERT OR REPLACE INTO warehouses
               (warehouse_id,name,lat,lng,capacity_cbm,used_cbm,service_limit,status)
               VALUES (?,?,?,?,?,?,?,?)""",
            data
        )
        con.commit(); con.close()

    def list_active_warehouses() -> List[Dict]:
        con = get_conn(); cur = con.cursor()
        res = cur.execute("""SELECT warehouse_id,name,lat,lng,capacity_cbm,used_cbm,service_limit,status
                             FROM warehouses WHERE UPPER(status)='ACTIVE'""").fetchall()
        con.close()
        out=[]
        for (wid,name,lat,lng,cap,used,limit,status) in res:
            out.append({"warehouse_id":wid,"name":name,"lat":lat,"lng":lng,
                        "capacity_cbm":cap,"used_cbm":used,"service_limit":limit,"status":status})
        return out

    def try_hold_capacity(warehouse_id: str, offer_id: str, volume_cbm: float) -> Optional[str]:
        con = get_conn(); cur = con.cursor()
        row = cur.execute("""SELECT capacity_cbm, used_cbm FROM warehouses WHERE warehouse_id=?""",
                          (warehouse_id,)).fetchone()
        if not row:
            con.close(); return None
        cap, used = float(row[0]), float(row[1])
        if used + volume_cbm > cap:
            con.close(); return None
        new_used = used + volume_cbm
        cur.execute("""UPDATE warehouses SET used_cbm=? WHERE warehouse_id=?""",
                    (new_used, warehouse_id))
        con.commit(); con.close()
        return f"RESV-{offer_id[:8]}-{warehouse_id}"

    # ---- distance cache (sqlite) ----
    def _sqlite_distance_get(key: str):
        con = get_conn(); cur = con.cursor()
        row = cur.execute("""SELECT km, minutes, expires_at FROM distance_cache WHERE key=?""",
                          (key,)).fetchone()
        con.close()
        if not row:
            return None
        km, minutes, exp = float(row[0]), float(row[1]), int(row[2] or 0)
        if exp and exp < int(time.time()):
            return None
        return (km, minutes)

    def _sqlite_distance_put(key: str, a_lat, a_lng, b_lat, b_lng,
                             km: float, minutes: float, ttl_sec: int = 86400):
        con = get_conn(); cur = con.cursor()
        cur.execute("""INSERT OR REPLACE INTO distance_cache
                       (key,a_lat,a_lng,b_lat,b_lng,km,minutes,expires_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (key, float(a_lat), float(a_lng), float(b_lat), float(b_lng),
                     float(km), float(minutes), int(time.time()) + int(ttl_sec)))
        con.commit(); con.close()

    # ---- persist results (sqlite) ----
    def save_decision_result(offer: Dict[str, Any], decision: Dict[str, Any], meta: Dict[str, Any] | None = None):
        con = get_conn(); cur = con.cursor()
        cur.execute("""INSERT INTO decision_runs(ts, offer_json, decision_json, meta_json)
                       VALUES (?,?,?,?)""",
                    (int(time.time()),
                     json.dumps(offer, ensure_ascii=False),
                     json.dumps(decision, ensure_ascii=False),
                     json.dumps(meta or {}, ensure_ascii=False)))
        con.commit(); con.close()

    def save_case_runs(rows: List[Dict[str, Any]], meta: Dict[str, Any] | None = None):
        con = get_conn(); cur = con.cursor()
        cur.execute("""INSERT INTO case_runs(ts, rows_json, meta_json)
                       VALUES (?,?,?)""",
                    (int(time.time()),
                     json.dumps(rows, ensure_ascii=False),
                     json.dumps(meta or {}, ensure_ascii=False)))
        con.commit(); con.close()


# =========================
# MongoDB backend (Atlas)
# =========================
else:
    from pymongo import MongoClient, ASCENDING
    from pymongo.errors import PyMongoError, OperationFailure
    import datetime as dt
    try:
        import certifi
        _TLS_CA = certifi.where()
    except Exception:
        _TLS_CA = None

    MONGO_URI = os.getenv("MONGO_URI")
    MONGO_DB  = os.getenv("MONGO_DB", "wms")
    COLL_W    = os.getenv("MONGO_WAREHOUSE_COLL", "warehouses")
    COLL_D    = os.getenv("MONGO_DISTANCE_COLL", "distance_cache")
    COLL_DEC  = os.getenv("MONGO_DECISION_COLL", "decision_runs")
    COLL_CASE = os.getenv("MONGO_CASE_COLL", "case_runs")

    _client: Optional[MongoClient] = None
    _db = None
    _cw = None
    _cd = None
    _cdec = None
    _ccase = None

    def _ensure_client():
        global _client, _db, _cw, _cd, _cdec, _ccase
        if _client is None:
            if not MONGO_URI:
                raise RuntimeError("MONGO_URI is not set")
            kwargs = {}
            if _TLS_CA:
                kwargs["tlsCAFile"] = _TLS_CA
            kwargs.setdefault("serverSelectionTimeoutMS", 30000)
            _client = MongoClient(MONGO_URI, **kwargs)
            _db = _client[MONGO_DB]
            _cw = _db[COLL_W]
            _cd = _db[COLL_D]
            _cdec = _db[COLL_DEC]
            _ccase = _db[COLL_CASE]
        return _client, _db, _cw, _cd, _cdec, _ccase

    def init_db():
        _, db, cw, cd, cdec, ccase = _ensure_client()
        cw.create_index([("warehouse_id", ASCENDING)], unique=True)
        cw.create_index([("status", ASCENDING)])
        cd.create_index([("key", ASCENDING)], unique=True)
        # --- TTL index on expires_at (พร้อมกันชน IndexOptionsConflict) ---
        try:
            cd.create_index("expires_at", expireAfterSeconds=0)
        except OperationFailure as e:
            if getattr(e, "code", None) == 85 or "IndexOptionsConflict" in str(e):
                try:
                    cd.drop_index("expires_at_1")
                except Exception:
                    pass
                cd.create_index("expires_at", expireAfterSeconds=0)
            else:
                raise
        # history collections
        cdec.create_index([("ts", ASCENDING)])
        ccase.create_index([("ts", ASCENDING)])

    def seed_warehouses():
        """
        Seed ข้อมูลคลังลง Mongo

        - ถ้า FORCE_RESEED=1 จะลบคลังทั้งหมดก่อน แล้วใส่ใหม่
        - ใช้ $set + upsert=True เพื่อให้ถ้ามีอยู่แล้วก็อัปเดต field (รวม lat/lng) ให้ตรงกับในโค้ด
        """
        _, db, cw, *_ = _ensure_client()
        if os.getenv("FORCE_RESEED") == "1":
            cw.delete_many({})

        data = [
            {"warehouse_id":"W1","name":"Bangkok DC1","lat":13.649,"lng":100.647,
             "capacity_cbm":10000.0,"used_cbm":2000.0,"service_limit":200.0,"status":"ACTIVE"},
            {"warehouse_id":"W2","name":"Bangkok DC2","lat":13.651,"lng":100.637,
             "capacity_cbm":15000.0,"used_cbm":2200.0,"service_limit":180.0,"status":"ACTIVE"},
            {"warehouse_id":"W3","name":"Bangkok DC3","lat":13.655,"lng":100.634,
             "capacity_cbm":10000.0,"used_cbm":1500.0,"service_limit":200.0,"status":"ACTIVE"},
            {"warehouse_id":"W4","name":"Bangkok DC4","lat":13.627,"lng":100.734,
             "capacity_cbm":15000.0,"used_cbm":2100.0,"service_limit":200.0,"status":"ACTIVE"},
            {"warehouse_id":"W5","name":"Bangkok DC5","lat":13.618,"lng":100.736,
             "capacity_cbm":10000.0,"used_cbm":1800.0,"service_limit":180.0,"status":"ACTIVE"},
        ]
        for d in data:
            cw.update_one(
                {"warehouse_id": d["warehouse_id"]},
                {"$set": d},   # อัปเดตเสมอ รวม lat/lng ใหม่
                upsert=True
            )

    def list_active_warehouses() -> List[Dict]:
        _, _, cw, *_ = _ensure_client()
        return list(cw.find(
            {"status": "ACTIVE"},
            {"_id":0, "warehouse_id":1,"name":1,"lat":1,"lng":1,
             "capacity_cbm":1,"used_cbm":1,"service_limit":1,"status":1}
        ))

    def try_hold_capacity(warehouse_id: str, offer_id: str, volume_cbm: float) -> Optional[str]:
        _, _, cw, *_ = _ensure_client()
        try:
            res = cw.update_one(
                {
                    "warehouse_id": warehouse_id,
                    "$expr": {
                        "$lte": [
                            {"$add": ["$used_cbm", float(volume_cbm)]},
                            "$capacity_cbm",
                        ]
                    }
                },
                {"$inc": {"used_cbm": float(volume_cbm)}}
            )
            if res.modified_count == 1:
                return f"RESV-{offer_id[:8]}-{warehouse_id}"
            return None
        except PyMongoError:
            return None

    # ---- distance cache (mongo) ----
    def _mongo_distance_get(key: str):
        _, _, _, cd, *_ = _ensure_client()
        doc = cd.find_one({"key": key}, {"_id": 0, "km":1, "minutes":1, "expires_at":1})
        if not doc:
            return None
        exp = doc.get("expires_at")
        if isinstance(exp, dt.datetime) and exp < dt.datetime.utcnow():
            return None
        return float(doc.get("km", 0.0)), float(doc.get("minutes", 0.0))

    def _mongo_distance_put(key: str, a_lat, a_lng, b_lat, b_lng,
                            km: float, minutes: float, ttl_sec: int = 86400):
        _, _, _, cd, *_ = _ensure_client()
        cd.update_one(
            {"key": key},
            {"$set": {
                "a_lat": float(a_lat), "a_lng": float(a_lng),
                "b_lat": float(b_lat), "b_lng": float(b_lng),
                "km": float(km), "minutes": float(minutes),
                "expires_at": dt.datetime.utcnow() + dt.timedelta(seconds=int(ttl_sec)),
            }},
            upsert=True
        )

    # ---- persist results (mongo) ----
    def save_decision_result(offer: Dict[str, Any], decision: Dict[str, Any], meta: Dict[str, Any] | None = None):
        _, _, _, _, cdec, _ = _ensure_client()
        doc = {
            "ts": int(time.time()),
            "offer": offer,
            "decision": decision,
            "meta": meta or {},
        }
        cdec.insert_one(doc)

    def save_case_runs(rows: List[Dict[str, Any]], meta: Dict[str, Any] | None = None):
        _, _, _, _, _, ccase = _ensure_client()
        doc = {
            "ts": int(time.time()),
            "rows": rows,
            "meta": meta or {},
        }
        ccase.insert_one(doc)

    # ป้องกันไม่ให้โค้ดเก่าไปเรียก get_conn ตอน BACKEND=mongo
    def get_conn():
        raise RuntimeError("get_conn() is only available for sqlite backend")

# =========================
# Unified Distance Cache API
# =========================
def load_distance_cache(key: str):
    """ให้ core/location.py เรียกใช้ตัวเดียวได้ทั้ง sqlite/mongo"""
    if BACKEND == "sqlite":
        return _sqlite_distance_get(key)
    return _mongo_distance_get(key)

def save_distance_cache(key: str, a_lat: float, a_lng: float, b_lat: float, b_lng: float,
                        km: float, minutes: float, ttl_sec: int = 7*24*3600):
    if BACKEND == "sqlite":
        return _sqlite_distance_put(key, a_lat, a_lng, b_lat, b_lng, km, minutes, ttl_sec)
    return _mongo_distance_put(key, a_lat, a_lng, b_lat, b_lng, km, minutes, ttl_sec)

# (วาง "History features" ต่อจากนี้ก็ได้ หรือจะวางก่อน block นี้ก็ได้ ขอแค่อยู่หลัง backend blocks)

# ===== History features (รองรับ sqlite/mongo) =====
from collections import defaultdict
import json as _json
import time as _t

def _sqlite_get_recent_decisions(days: int = 14) -> list[dict]:
    con = get_conn(); cur = con.cursor()
    since = int(_t.time()) - days * 24 * 3600
    rows = cur.execute(
        "SELECT ts, offer_json, decision_json FROM decision_runs WHERE ts >= ? ORDER BY ts ASC",
        (since,)
    ).fetchall()
    con.close()
    out = []
    for ts, offer_j, dec_j in rows:
        try: offer = _json.loads(offer_j or "{}")
        except Exception: offer = {}
        try: decision = _json.loads(dec_j or "{}")
        except Exception: decision = {}
        out.append({"ts": int(ts or 0), "offer": offer, "decision": decision})
    return out

def _mongo_get_recent_decisions(days: int = 14) -> list[dict]:
    _, db, *_ = _ensure_client()
    since = int(_t.time()) - days * 24 * 3600
    return list(db[COLL_DEC].find({"ts": {"$gte": since}}, {"_id": 0}))

def get_recent_decisions(days: int = 14) -> list[dict]:
    if BACKEND == "sqlite":
        return _sqlite_get_recent_decisions(days)
    return _mongo_get_recent_decisions(days)

def compute_warehouse_stats(days: int = 14) -> dict[str, dict]:
    rows = get_recent_decisions(days)
    agg = defaultdict(lambda: {"wins":0,"bids":0,"profit_sum":0.0,"margin_sum":0.0,"price_sum":0.0})
    alpha = 0.3
    ewma_util = defaultdict(float)
    has_ewma = defaultdict(bool)

    for r in rows:
        dec = r.get("decision") or {}
        chosen = dec.get("chosen_warehouse")
        cands = dec.get("candidates") or []
        for c in cands:
            wid = c.get("warehouse_id")
            if not wid:
                continue
            agg[wid]["bids"] += 1
            agg[wid]["profit_sum"] += float(c.get("profit") or 0.0)
            agg[wid]["margin_sum"] += float(c.get("margin") or 0.0)
            agg[wid]["price_sum"]  += float(c.get("price_amount") or 0.0)
            if wid == chosen:
                util = float(c.get("utilization") or 0.0)
                if not has_ewma[wid]:
                    ewma_util[wid] = util; has_ewma[wid] = True
                else:
                    ewma_util[wid] = alpha * util + (1 - alpha) * ewma_util[wid]
        if chosen:
            agg[chosen]["wins"] += 1

    out = {}
    for wid, a in agg.items():
        bids = max(1, a["bids"])
        wins = a["wins"]
        out[wid] = {
            "wins": wins,
            "bids": a["bids"],
            "accept_rate": wins / float(bids),
            "avg_profit": a["profit_sum"] / bids,
            "avg_margin": a["margin_sum"] / bids,
            "avg_price":  a["price_sum"]  / bids,
            "ewma_util":  ewma_util.get(wid, 0.0),
        }
    return out

# ===== Backward-compat aliases (ต้องวางสุดท้าย หลังประกาศฟังก์ชันแล้ว) =====
distance_cache_get = load_distance_cache
distance_cache_put = save_distance_cache
