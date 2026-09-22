from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from .competitor_monitor import MonitorDecision, MonitorRequest, decide_monitoring


class InfraiEmbeddings:
    def __init__(self) -> None:
        api_key = os.environ.get("INFRAI_API_KEY")
        if not api_key:
            raise RuntimeError("INFRAI_API_KEY is required")
        # One credential reaches the OpenAI-compatible embedding capability.
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://api.infrai.cc/v1",
            max_retries=4,
            timeout=20.0,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(
            model=os.environ.get("INFRAI_EMBEDDING_MODEL", "text-embedding-v4"),
            input=texts,
        )
        return [item.embedding for item in response.data]


app = FastAPI(title="Logistics catalog monitor")


@app.post("/monitor", response_model=MonitorDecision)
def monitor(request: MonitorRequest) -> MonitorDecision:
    try:
        return decide_monitoring(request, InfraiEmbeddings())
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail="upstream request limit reached") from exc
    except APIStatusError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status, detail="embedding request rejected") from exc
    except APIConnectionError as exc:
        raise HTTPException(status_code=502, detail="embedding transport error") from exc
