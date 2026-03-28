"""API clients for Estonian transport data sources."""

import httpx

OTP_GRAPHQL_URL = "https://api.peatus.ee/routing/v1/routers/estonia/index/graphql"
TALLINN_GPS_URL = "https://transport.tallinn.ee/gps.txt"

VEHICLE_TYPES = {"1": "trolleybus", "2": "bus", "3": "tram"}


async def graphql(query: str, variables: dict | None = None) -> dict:
    """Execute a GraphQL query against the peatus.ee OTP API."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            OTP_GRAPHQL_URL,
            json={"query": query, "variables": variables or {}},
        )
        if resp.status_code == 500:
            # Try to extract error details from response body
            detail = ""
            try:
                body = resp.json()
                if errors := body.get("errors"):
                    detail = " Details: " + ", ".join(e.get("message", "") for e in errors)
            except Exception:
                pass
            raise RuntimeError(
                "The peatus.ee API returned a server error. This can happen when "
                "coordinates are outside Estonia, the date is too far in the future, "
                "or no route exists between the given points. Try adjusting your query."
                + detail
            )
        resp.raise_for_status()
        data = resp.json()
        if errors := data.get("errors"):
            raise RuntimeError(f"GraphQL error: {', '.join(e['message'] for e in errors)}")
        return data["data"]


async def fetch_tallinn_gps() -> str:
    """Fetch raw GPS text from Tallinn transport API."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(TALLINN_GPS_URL)
        resp.raise_for_status()
        return resp.text
