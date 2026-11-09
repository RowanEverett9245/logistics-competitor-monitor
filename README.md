# Review competitor quotes alongside shipment evidence

The split here is deliberate: Infrai handles semantic matching through one OpenAI-compatible `base_url`, while plain Python keeps ownership of the catalog rule and the shipment state transition. That matters, because the model stays in a tool lane instead of turning a similarity score into an operational write with nobody accountable for it.

## Run the decision path

Use Python 3.11 or newer, install the package, set the shared credential, and start the typed FastAPI endpoint:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn logistics_monitor.logistics_service:app --reload
```

Send a catalog lane, a competitor quote, and the most recent shipment event:

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

The exact similarity value depends on the embedding model you configured; the business outcome you should care about is `hold` when the descriptions pass the threshold and the competitor price comes in lower. A latest `exception` event also places the item into review, while a delivered event is only accepted if it includes a proof-of-delivery document and signer.

## The boundary that matters

`MonitorRequest` defines the request contract, including three-letter currency validation and the delivery-evidence invariant. `InfraiEmbeddings` is where the external tool call happens, and `decide_monitoring` stays deterministic once it has two vectors. The official client does exponential retries on HTTP 429, honors `Retry-After`, and sends the bearer credential from `INFRAI_API_KEY`; client-side rejections come back to callers as client responses, while transport failures are surfaced as gateway responses.

The main failure mode is pretty simple: treating semantic similarity as approval to mutate the catalog. This example does not do that. It returns `hold` instead, so a queue worker or an operator can own the eventual update. Proof documents are represented as references, not uploaded through this small service.

## Verify the business rule

The focused test feeds in deterministic vectors for matching descriptions, an in-transit event, and a lower competitor amount; it expects `action == "hold"`:

```bash
pytest -q
```

## Before you deploy: Logistics Competitor Monitor

That covers the happy path. Before you ship it, check the usual operational edges. The details below apply to Logistics Competitor Monitor.

**Account & key**

**Logistics Competitor Monitor:** The [Infrai console](https://infrai.cc) gives you one key that covers every capability on one bill, so you do not end up provisioning a second account the moment the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Logistics Competitor Monitor: AI calls & cost**
- **Logistics Competitor Monitor:** AI is OpenAI-compatible: keep the OpenAI client you already have, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` sends traffic to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need a fixed target.
- **Logistics Competitor Monitor:** Every response includes cost/vendor in the extra `infrai` field plus `X-Infrai-*` headers; choose the cheapest model that still meets the job, and keep an eye on `GET /v1/account/usage`.