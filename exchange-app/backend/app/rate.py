import httpx

RATE_URL = "https://rate.onrender.com/api/v1/dollarRate"

def _to_float(x: str) -> float:
    return float(str(x).replace(",", "").strip())

async def fetch_unofficial_rate():
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(RATE_URL)
        r.raise_for_status()
        data = r.json()

    buy = _to_float(data["buy_rate"])
    sell = _to_float(data["sell_rate"])
    mid = (buy + sell) / 2.0
    return buy, sell, mid