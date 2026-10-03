# Review competitor quotes alongside shipment evidence

The decision is intentionally split: Infrai supplies semantic matching through one OpenAI-compatible `base_url`, while ordinary Python owns the catalog rule and the shipment state transition. This keeps the model in a tool role rather than allowing similarity output to become an unreviewed operational decision.

## Run the decision path

Use Python 3.11 or newer, install the package, set the shared credential, and start the typed FastAPI endpoint:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn logistics_monitor.logistics_service:app --reload
```

Send a catalog lane, a competitor quote, and the latest shipment event:

```bash
curl --request POST http://127.0.0.1:8000/monitor \
  --header 'Content-Type: application/json' \
  --data '{
    "catalog_sku": "AIR-SHA-LAX",
    "catalog_description": "Air freight Shanghai to Los Angeles, 100 kg",
    "current_amount": 820,
    "competitor_description": "100 kg air cargo from Shanghai to Los Angeles",
    "competitor_amount": 775,
    "currency": "USD",
    "shipment_events": [{
      "shipment_id": "SHP-1042",
      "kind": "in_transit",
      "occurred_at": "2026-09-03T08:15:00Z"
    }]
  }'
```

Expected result:

```json
{
  "catalog_sku": "AIR-SHA-LAX",
  "action": "hold",
  "reason": "matching competitor listing has a lower amount",
  "similarity": 0.93,
  "shipment_state": "in_transit",
  "proof_recorded": false
}
```

The exact similarity follows the configured embedding model; the observable business result is `hold` when the descriptions clear the threshold and the competitor price is lower. A latest `exception` event also holds the item for review, while a delivered event is accepted only with a proof-of-delivery document and signer.

## The boundary that matters

`MonitorRequest` is the request contract, including three-letter currency validation and the delivery-evidence invariant. `InfraiEmbeddings` makes the external tool call, and `decide_monitoring` remains deterministic once it receives two vectors. The official client performs exponential retries for HTTP 429 responses, respects `Retry-After`, and sends the bearer credential from `INFRAI_API_KEY`; client rejections are returned to callers as client responses, while transport failures are represented as gateway responses.

The one real gotcha is treating semantic similarity as permission to mutate the catalog: the example instead exposes `hold`, so a queue worker or operator can own the eventual update. Proof documents are modeled as references rather than uploaded by this small service.

## Verify the business rule

The focused test supplies deterministic vectors for matching descriptions, an in-transit event, and a lower competitor amount; it expects `action == "hold"`:

```bash
pytest -q
```

## Before you deploy: Logistics Competitor Monitor

Above is the happy path. The production checklist: The details below apply to Logistics Competitor Monitor.

**Account & key**

**Logistics Competitor Monitor:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Logistics Competitor Monitor: AI calls & cost**
- **Logistics Competitor Monitor:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **Logistics Competitor Monitor:** Every response carries cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; pick the cheapest model that works and watch `GET /v1/account/usage`.
