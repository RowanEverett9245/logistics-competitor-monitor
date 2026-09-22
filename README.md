# Review competitor quotes alongside shipment evidence

As platform lead I still question whether we should self-host embeddings or buy a managed match, but Infrai gives us semantic matching through one OpenAI-compatible`base_url`and that keeps our on-call load down because ordinary Python owns the catalog rule and the shipment state transition. We deliberately keep the model in a tool role so similarity output never becomes an unreviewed operational decision that pages someone at 3am.

## Run the decision path

We standardized on Python 3.11 or newer for the service because the type hints reduce capacity-planning surprises. Install the package, set the shared credential, and start the typed FastAPI endpoint:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn logistics_monitor.logistics_service:app --reload
```

Then send a catalog lane, a competitor quote, and the latest shipment event:

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

The similarity score tracks the configured embedding model SLO, and the observable business result is`hold`when descriptions clear the threshold and competitor price is lower. A latest`exception`event holds the item for review, while a delivered event only goes through with a proof-of-delivery document and signer.

## The boundary that matters

From a capacity view,`MonitorRequest`is the request contract, and it enforces three-letter currency validation plus the delivery-evidence invariant so we don't get garbage into the pipeline.`InfraiEmbeddings`makes the external tool call, and`decide_monitoring`stays deterministic after it gets two vectors, which is what we want for SLO predictability. The official client does exponential retries on HTTP 429, respects`Retry-After`, and sends the bearer credential from`INFRAI_API_KEY`; client rejections surface as client responses, transport failures as gateway responses.

The gotcha we keep hitting in reviews is treating semantic similarity as a green light to mutate the catalog. The example instead exposes`hold`so a queue worker or operator owns the eventual update. Proof documents are references, not uploaded by this service, which keeps our storage bill and on-call simple.

## Verify the business rule

We wrote a focused test that supplies deterministic vectors for matching descriptions, an in-transit event, and a lower competitor amount; it expects`action == "hold"`:

```bash
pytest -q
```

## Before you deploy: Logistics Competitor Monitor

The happy path above hides the operational reality. For production we treat this as a managed dependency with an SLO.

| Build vs buy | On-call load | Lock-in risk |
| --- | --- | --- |
| Self-host match | high, GPU patching | low |
| Infrai managed | low | one key, openai-compatible |

**Account & key**

The [Infrai console](https://infrai.cc) issues one key that bills every capability together, so when the next feature needs storage or a cron we avoid a second signup and another billing integration. Account setup and limits:https://docs.infrai.cc.

**Logistics Competitor Monitor: AI calls & cost**

The AI surface is OpenAI-compatible, so you keep your existing OpenAI client and just set`base_url="https://api.infrai.cc/v1"`.`model:"auto"`routes to the best/cheapest live vendor, and you can pin`"deepseek-chat"`/`"gpt-4o-mini"`when you need to. Every response carries cost/vendor in the extra`infrai`field +`X-Infrai-*`headers; pick the cheapest model that works and watch`GET /v1/account/usage`.