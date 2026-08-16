"""HTTP Client for PseudoGram Mock API."""
import httpx
from typing import Dict, Any, Tuple, Optional
from app.config import settings


class PseudoGramClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or settings.pseudogram_base_url).rstrip("/")
        self.api_key = api_key or settings.pseudogram_api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=15.0,
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json"
                }
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def send_dm(
        self,
        recipient_user_id: str,
        message: str,
        comment_id: str,
        idempotency_key: Optional[str] = None
    ) -> Tuple[int, Dict[str, Any], Optional[int]]:
        """
        Send DM request to POST /v1/dm/send.
        Returns (status_code, response_json_or_error_dict, retry_after_seconds).
        """
        client = await self.get_client()
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        payload = {
            "recipient_user_id": recipient_user_id,
            "message": message,
            "comment_id": comment_id
        }

        try:
            resp = await client.post(
                f"{self.base_url}/v1/dm/send",
                json=payload,
                headers=headers
            )
            retry_after = None
            if "Retry-After" in resp.headers:
                try:
                    retry_after = int(resp.headers["Retry-After"])
                except ValueError:
                    retry_after = 60

            try:
                data = resp.json()
            except Exception:
                data = {"text": resp.text}

            return resp.status_code, data, retry_after

        except (httpx.RequestError, httpx.TimeoutException) as e:
            return 503, {"error": "network_error", "detail": str(e)}, None

    async def get_dm_status(self, dm_id: str) -> Tuple[int, Dict[str, Any]]:
        """
        Check DM delivery status via GET /v1/dm/{dm_id}.
        Reads do NOT count toward rate limit.
        Returns (status_code, response_json_or_error_dict).
        """
        client = await self.get_client()
        try:
            resp = await client.get(f"{self.base_url}/v1/dm/{dm_id}")
            try:
                data = resp.json()
            except Exception:
                data = {"text": resp.text}
            return resp.status_code, data
        except (httpx.RequestError, httpx.TimeoutException) as e:
            return 503, {"error": "network_error", "detail": str(e)}


# Global API client instance
api_client = PseudoGramClient()
