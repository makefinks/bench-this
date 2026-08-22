"""Resolve best-effort baseline model prices from the Models.dev provider catalog."""

import json
import math
import threading
import urllib.request
from typing import Any, Dict, Optional

from .models import ModelPrice


MODELS_DEV_API_URL = "https://models.dev/api.json"


class ModelsDevPricing:
    """Fetch the provider catalog once and tolerate unavailable or malformed remote data."""

    def __init__(self, url: str = MODELS_DEV_API_URL, timeout_seconds: float = 5.0):
        self.url = url
        self.timeout_seconds = timeout_seconds
        self._catalog: Optional[Dict[str, Any]] = None
        self._loaded = False
        self._lock = threading.Lock()

    def _load(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._loaded:
                return self._catalog
            self._loaded = True
            try:
                request = urllib.request.Request(
                    self.url,
                    headers={"User-Agent": "bench-this/0.1 (+https://github.com/makefinks/bench-this)"},
                )
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    data = json.load(response)
                if isinstance(data, dict):
                    self._catalog = data
            except (OSError, ValueError, TypeError):
                pass
            return self._catalog

    def price(self, provider: str, model: str) -> Optional[ModelPrice]:
        """Return per-million-token rates for an exact provider/model pair when published."""

        catalog = self._load()
        if catalog is None:
            return None
        provider_data = catalog.get(provider)
        if not isinstance(provider_data, dict):
            return None
        models = provider_data.get("models")
        if not isinstance(models, dict):
            return None
        model_data = models.get(model)
        if not isinstance(model_data, dict):
            return None
        cost = model_data.get("cost")
        if not isinstance(cost, dict):
            return None

        try:
            input_rate = float(cost["input"])
            output_rate = float(cost["output"])
            cache_read_rate = float(cost.get("cache_read", 0.0))
            cache_write_rate = float(cost.get("cache_write", 0.0))
        except (KeyError, TypeError, ValueError):
            return None
        rates = (input_rate, output_rate, cache_read_rate, cache_write_rate)
        if not all(math.isfinite(rate) and rate >= 0 for rate in rates):
            return None
        return ModelPrice(
            input_per_million_usd=input_rate,
            output_per_million_usd=output_rate,
            reasoning_per_million_usd=output_rate,
            cache_read_per_million_usd=cache_read_rate,
            cache_write_per_million_usd=cache_write_rate,
        )
