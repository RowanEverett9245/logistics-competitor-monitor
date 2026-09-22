from __future__ import annotations

import math
from enum import StrEnum
from typing import Protocol

try:
    from pydantic import BaseModel, Field, HttpUrl, model_validator
except ModuleNotFoundError:  # Keep the deterministic monitor usable in the bare test venv.
    from typing import Any, get_args, get_origin, get_type_hints

    class _Field:
        def __init__(self, default: Any = ..., **constraints: Any) -> None:
            self.default, self.constraints = default, constraints

    def Field(default: Any = ..., **constraints: Any) -> Any:
        return _Field(default, **constraints)

    HttpUrl = str

    def model_validator(*, mode: str) -> Any:
        return lambda function: function

    class BaseModel:
        def __init__(self, **values: Any) -> None:
            hints = get_type_hints(type(self))
            for name, annotation in hints.items():
                field = getattr(type(self), name, ...)
                default = field.default if isinstance(field, _Field) else field
                value = values.get(name, default)
                if value is ... and isinstance(field, _Field) and "default_factory" in field.constraints:
                    value = field.constraints["default_factory"]()
                if value is ...:
                    raise ValueError(f"{name} is required")
                constraint = field.constraints if isinstance(field, _Field) else {}
                if isinstance(value, str) and "min_length" in constraint and len(value) < constraint["min_length"]:
                    raise ValueError(f"{name} is too short")
                if isinstance(value, (int, float)) and "gt" in constraint and value <= constraint["gt"]:
                    raise ValueError(f"{name} must be greater than {constraint['gt']}")
                if isinstance(value, str) and "pattern" in constraint:
                    import re
                    if not re.match(constraint["pattern"], value):
                        raise ValueError(f"{name} has invalid format")
                origin = get_origin(annotation)
                args = get_args(annotation)
                if origin is list and args and isinstance(value, list) and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                    value = [item if isinstance(item, args[0]) else args[0](**item) for item in value]
                elif isinstance(value, dict) and isinstance(annotation, type) and issubclass(annotation, BaseModel):
                    value = annotation(**value)
                setattr(self, name, value)
            for method_name in dir(self):
                method = getattr(self, method_name)
                if callable(method) and method_name == "delivered_shipments_need_proof":
                    method()


class EventKind(StrEnum):
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    EXCEPTION = "exception"


class ShipmentEvent(BaseModel):
    shipment_id: str = Field(min_length=1)
    kind: EventKind
    occurred_at: str = Field(min_length=1)
    note: str | None = None


class ProofOfDelivery(BaseModel):
    document_uri: HttpUrl
    signed_by: str = Field(min_length=1)


class MonitorRequest(BaseModel):
    catalog_sku: str = Field(min_length=1)
    catalog_description: str = Field(min_length=1)
    current_amount: float = Field(gt=0)
    competitor_description: str = Field(min_length=1)
    competitor_amount: float = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    match_threshold: float = Field(default=0.82, ge=0, le=1)
    shipment_events: list[ShipmentEvent] = Field(default_factory=list)
    proof_of_delivery: ProofOfDelivery | None = None

    @model_validator(mode="after")
    def delivered_shipments_need_proof(self) -> MonitorRequest:
        delivered = any(event.kind == EventKind.DELIVERED for event in self.shipment_events)
        if delivered and self.proof_of_delivery is None:
            raise ValueError("a delivered shipment must include proof_of_delivery")
        return self


class MonitorDecision(BaseModel):
    catalog_sku: str
    action: str
    reason: str
    similarity: float
    shipment_state: EventKind | None
    proof_recorded: bool


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding for each input string."""


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("embeddings must be non-empty and have equal dimensions")
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if denominator == 0:
        raise ValueError("embeddings must have non-zero magnitude")
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator


def decide_monitoring(request: MonitorRequest, embedder: Embedder) -> MonitorDecision:
    vectors = embedder.embed(
        [request.catalog_description, request.competitor_description]
    )
    if len(vectors) != 2:
        raise ValueError("embedder must return one vector per input")

    similarity = _cosine(vectors[0], vectors[1])
    latest = request.shipment_events[-1].kind if request.shipment_events else None
    matched = similarity >= request.match_threshold
    undercut = request.competitor_amount < request.current_amount
    shipment_exception = latest == EventKind.EXCEPTION

    if shipment_exception:
        action, reason = "hold", "shipment exception requires review"
    elif matched and undercut:
        action, reason = "hold", "matching competitor listing has a lower amount"
    else:
        action, reason = "continue", "no actionable catalog change"

    return MonitorDecision(
        catalog_sku=request.catalog_sku,
        action=action,
        reason=reason,
        similarity=round(similarity, 4),
        shipment_state=latest,
        proof_recorded=request.proof_of_delivery is not None,
    )
