# agents/tools_registry.py (สรุปโครง)
from core.location import geocode, route
from core.db import list_active_warehouses, try_hold_capacity
from core.pricing import load_rate, price

TOOLS = [
    {"type":"function","function":{
        "name":"tool_geocode","description":"...",
        "parameters":{"type":"object","properties":{"address":{"type":"string"}},"required":["address"]}
    }},
    # ... (tools อื่น ๆ)
]

def call_tool(name, args):
    if name == "tool_geocode":
        lat,lng = geocode(args["address"]); return {"lat":lat, "lng":lng}
    # ... (mapping ที่เหลือ)
    return {"error":"unknown tool"}
