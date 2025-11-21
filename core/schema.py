from pydantic import BaseModel, Field
from typing import Optional, List

class SLA(BaseModel):
    latest_dropoff_hour: int
    weekday_only: bool = True

class Offer(BaseModel):
    offer_id: str
    customer_id: str
    origin_address: Optional[str] = None
    origin_lat: Optional[float] = None
    origin_lng: Optional[float] = None
    volume_cbm: float
    start_date: str
    duration_days: int
    sla: SLA

class RouteInfo(BaseModel):
    km: float
    minutes: float

class Candidate(BaseModel):
    warehouse_id: str
    route: RouteInfo
    available_cbm: float
    price_amount: float
    margin: float
    utilization: float
    sla_fit: float
    score: float

class Decision(BaseModel):
    offer_id: str
    accept: bool
    chosen_warehouse: Optional[str] = None
    reason: str
    candidates: List[Candidate] = Field(default_factory=list)
    priced_amount: Optional[float] = None
    reservation_id: Optional[str] = None
