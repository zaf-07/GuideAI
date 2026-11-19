"""Pydantic request and response contracts for the GuideAI API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DetectedObject(BaseModel):
    label: str = Field(max_length=40)
    confidence: float = Field(ge=0, le=1)
    position: str = Field(max_length=30)
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    width: float | None = Field(default=None, ge=0, le=1)
    height: float | None = Field(default=None, ge=0, le=1)


class VisionResult(BaseModel):
    summary: str = Field(max_length=100)
    speech: str = Field(max_length=240)
    scene_key: str = Field(max_length=80)
    urgency: Literal["low", "medium", "high"]
    changed: bool
    objects: list[DetectedObject] = Field(max_length=8)
    task: Literal["scene", "sign"]
    should_speak: bool = False
    warnings: list[str] = Field(default_factory=list, max_length=3)


class TrackingResult(BaseModel):
    objects: list[DetectedObject] = Field(max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=3)
    tracking_latency_ms: int = Field(ge=0)
    detector: Literal["yolo11", "disabled"]
    metric_depth: bool = False
    camera_coach: None = None
    collision_warnings_enabled: bool = False


class SignSequenceRequest(BaseModel):
    frames: list[str] = Field(min_length=3, max_length=3)
    previous_transcript: str = Field(default="", max_length=600)


class SignTranslation(BaseModel):
    transcript: str = Field(max_length=600)
    segment: str = Field(max_length=180)
    confidence: float = Field(ge=0, le=1)
    is_final: bool
    should_speak: bool


class CampusAlert(BaseModel):
    id: int
    location: str
    category: str
    label: str
    description: str
    severity: Literal["low", "medium", "high"]
    reported_by: str
    created_at: str
    relative_time: str
    is_active: bool


class CampusAlertCreateRequest(BaseModel):
    location: str = Field(min_length=1, max_length=80)
    category: Literal["hazard", "obstacle", "sign", "room_status"] = "hazard"
    label: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=200)
    severity: Literal["low", "medium", "high"] = "medium"


class BaselineObject(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    x: float = Field(default=0.5, ge=0.0, le=1.0)
    y: float = Field(default=0.5, ge=0.0, le=1.0)
    width: float | None = Field(default=None, ge=0.0, le=1.0)
    height: float | None = Field(default=None, ge=0.0, le=1.0)


class WhatChangedRequest(BaseModel):
    location: str = Field(default="Room 204", min_length=1, max_length=80)
    current_objects: list[BaselineObject] = Field(default_factory=list, max_length=64)
    update_baseline: bool = False


class WhatChangedResponse(BaseModel):
    has_changed: bool
    delta_summary: str
    speech: str
    added_objects: list[str]
    removed_objects: list[str]
    moved_objects: list[str]


class BridgeMessageRequest(BaseModel):
    # The conversation code; the field keeps its original name for older clients.
    session_id: str = Field(pattern=r"^\d{6}$")
    sender_role: Literal["deaf", "blind"]
    text: str = Field(min_length=1, max_length=500)
    # Set by the client so a retried send is stored once.
    client_id: str | None = Field(default=None, max_length=64)


class BridgeMessage(BaseModel):
    id: int
    session_id: str
    sender_role: Literal["deaf", "blind"]
    text: str
    client_id: str | None = None
    from_this_device: bool = False
    created_at: str
    relative_time: str


class BridgeConversation(BaseModel):
    code: str
    created_at: str
    expires_at: str
    devices: int
    max_devices: int
    partner_joined: bool
    is_member: bool


class ObservationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_id: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    confidence: float = Field(ge=0, le=1)
    privacy_scope: Literal["personal", "shared"] = "personal"
    verified: bool = False
    room_x: float | None = Field(default=None, ge=0, le=1)
    room_y: float | None = Field(default=None, ge=0, le=1)
    expires_in_seconds: int = Field(default=86400, ge=60, le=2592000)
    origin: Literal["manual", "detector"] = "manual"


class Observation(BaseModel):
    id: int
    category: str
    label: str
    description: str
    zone_id: str
    timestamp: str
    source_device: str
    source_session: str
    confidence: float
    verification_status: Literal["verified", "unverified"]
    privacy_scope: Literal["personal", "shared"]
    room_x: float | None = Field(default=None, ge=0, le=1)
    room_y: float | None = Field(default=None, ge=0, le=1)
    expires_at: str
    origin: Literal["manual", "detector"]


class ObservationChanges(BaseModel):
    zone_id: str
    generated_at: str
    compared_seconds: int
    added: list[str]
    previously_seen: list[str]
    summary: str
    verified_only: bool = True


class SharedSightDashboard(BaseModel):
    zone_id: str
    connected_devices: int
    recent_observations: list[Observation]
    tracking_latency_ms: int | None = None
    tracking_requests_last_5m: int = 0
    # nvidia-smi on the DGX Spark: {"available": bool, "gpus": [...]}.
    gpu: dict[str, object] | None = None


class RecallRememberRequest(BaseModel):
    """One thing worth remembering, on its way to the user's memory graph."""

    content: str = Field(min_length=1, max_length=4000)
    kind: str = Field(default="object", max_length=32)
    id: str | None = Field(default=None, max_length=255)
    supportingContext: str | None = Field(default=None, max_length=1500)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)
    date: str | None = Field(default=None, max_length=40)


class RecallRememberResponse(BaseModel):
    id: str
    status: str


class RecallSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    limit: int = Field(default=8, ge=1, le=100)
    kinds: list[str] = Field(default_factory=list, max_length=8)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class RecallRelation(BaseModel):
    id: str
    text: str
    relation: str


class RecallHit(BaseModel):
    id: str
    text: str
    similarity: float
    kind: str | None = None
    metadata: dict = Field(default_factory=dict)
    updatedAt: str | None = None
    related: list[RecallRelation] = Field(default_factory=list)


class RecallSearchResponse(BaseModel):
    results: list[RecallHit] = Field(default_factory=list)


class RecallStatusResponse(BaseModel):
    configured: bool
    reason: str | None = None
