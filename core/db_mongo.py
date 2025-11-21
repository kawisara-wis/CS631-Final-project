# core/db_mongo.py
import os
from typing import List, Dict, Optional
from pymongo import MongoClient, ASCENDING, ReturnDocument

_MONGO = None
_DB = None
_COLL = None

def _client():
    global _MONGO, _DB, _COLL
    if _MONGO is None:
        uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        _MONGO = MongoClient(uri, serverSelectionTimeoutMS=3000)
        dbname = os.getenv("MONGO_DB", "wms")
        _DB = _MONGO[dbname]
        cname = os.getenv("MONGO_WAREHOUSE_COLL", "warehouses")
        _COLL = _DB[cname]
    return _MONGO, _DB, _COLL

def init_db():
    """เตรียมคอลเลกชันและอินเด็กซ์พื้นฐาน"""
    _, _, coll = _client()
    # อินเด็กซ์ให้ค้นเร็วและกันซ้ำ
    coll.create_index([("warehouse_id", ASCENDING)], unique=True)
    coll.create_index([("status", ASCENDING)])

def seed_warehouses():
    """
    Seed W1..W5 ถ้ายังไม่มี (อิงรูปแบบเดิมจาก SQLite)
    """
    _, _, coll = _client()
    if coll.count_documents({}) >= 2:
        return

    docs = [
        {"warehouse_id":"W1","name":"Bangkok DC1","lat":13.649,"lng":100.647,
         "capacity_cbm":10000.0,"used_cbm":2000.0,"service_limit":200.0,"status":"ACTIVE"},
        {"warehouse_id":"W2","name":"Bangkok DC2","lat":13.651,"lng":100.637,
         "capacity_cbm":15000.0,"used_cbm":2200.0,"service_limit":180.0,"status":"ACTIVE"},
        {"warehouse_id":"W3","name":"Bangkok DC3","lat":13.655,"lng":100.634,
         "capacity_cbm":10000.0,"used_cbm":1500.0,"service_limit":200.0,"status":"ACTIVE"},
        {"warehouse_id":"W4","name":"Bangkok DC4","lat":13.627,"lng":100.734,
         "capacity_cbm":15000.0,"used_cbm":2100.0,"service_limit":200.0,"status":"ACTIVE"},
        {"warehouse_id":"W5","name":"Bangkok DC5","lat":13.618,"lng":100.734,
         "capacity_cbm":10000.0,"used_cbm":1800.0,"service_limit":180.0,"status":"ACTIVE"},
    ]
    for d in docs:
        coll.update_one({"warehouse_id": d["warehouse_id"]}, {"$setOnInsert": d}, upsert=True)

def list_active_warehouses() -> List[Dict]:
    _, _, coll = _client()
    cursor = coll.find({"status": "ACTIVE"})
    rows = []
    for doc in cursor:
        doc.pop("_id", None)
        rows.append(doc)
    return rows

def capacity_available(w: Dict) -> float:
    """คำนวณ available_cbm ตามเอกสารที่ดึงมา"""
    return float(w.get("capacity_cbm", 0.0) - w.get("used_cbm", 0.0))

def try_hold_capacity(warehouse_id: str, volume_cbm: float) -> bool:
    """
    จองความจุแบบอะตอมมิก:
    - อัปเดตเฉพาะเมื่อ available_cbm >= volume_cbm
    - ใช้ find_one_and_update พร้อมเงื่อนไข
    """
    _, _, coll = _client()
    # เงื่อนไข: capacity - used >= volume_cbm
    cond = {
        "warehouse_id": warehouse_id,
        "status": "ACTIVE",
        "$expr": {
            "$gte": [
                {"$subtract": ["$capacity_cbm", "$used_cbm"]},
                float(volume_cbm),
            ]
        }
    }
    update = {"$inc": {"used_cbm": float(volume_cbm)}}
    res = coll.find_one_and_update(cond, update, return_document=ReturnDocument.AFTER)
    return res is not None

def release_capacity(warehouse_id: str, volume_cbm: float) -> bool:
    """คืนความจุ (กรณียกเลิก)"""
    _, _, coll = _client()
    cond = {"warehouse_id": warehouse_id}
    update = {"$inc": {"used_cbm": -float(volume_cbm)}}
    res = coll.update_one(cond, update)
    return res.modified_count > 0
