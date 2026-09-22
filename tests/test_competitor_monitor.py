from logistics_monitor.competitor_monitor import (
    EventKind,
    MonitorRequest,
    ShipmentEvent,
    decide_monitoring,
)


class MatchingEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        assert len(texts) == 2
        return [[1.0, 0.0], [0.99, 0.01]]


def test_lower_matching_offer_holds_catalog_during_normal_transit() -> None:
    request = MonitorRequest(
        catalog_sku="AIR-SHA-LAX",
        catalog_description="Air freight Shanghai to Los Angeles, 100 kg",
        current_amount=820.0,
        competitor_description="100 kg air cargo from Shanghai to Los Angeles",
        competitor_amount=775.0,
        currency="USD",
        shipment_events=[
            ShipmentEvent(
                shipment_id="SHP-1042",
                kind=EventKind.IN_TRANSIT,
                occurred_at="2026-09-03T08:15:00Z",
            )
        ],
    )

    decision = decide_monitoring(request, MatchingEmbedder())

    assert decision.action == "hold"
    assert decision.reason == "matching competitor listing has a lower amount"
    assert decision.shipment_state == EventKind.IN_TRANSIT

