"""Live API integration tests for Estonian Transport MCP server.

These tests hit the real peatus.ee and transport.tallinn.ee APIs.
Run with: pytest test_live_api.py -v
Skip with: pytest --ignore=test_live_api.py
"""

import pytest

from estonian_transport_mcp import (
    _graphql,
    search_stops,
    get_departures,
    plan_trip,
    nearby_stops,
    get_route,
    tallinn_vehicles,
)


# --- GraphQL API connectivity ---


class TestApiConnectivity:
    @pytest.mark.asyncio
    async def test_graphql_endpoint_responds(self):
        """Verify the peatus.ee GraphQL API is reachable and returns valid data."""
        data = await _graphql("{ feeds { feedId } }")
        assert "feeds" in data
        assert len(data["feeds"]) > 0

    @pytest.mark.asyncio
    async def test_graphql_with_variables(self):
        """Verify variables are passed correctly."""
        data = await _graphql(
            'query($name: String!) { stops(name: $name) { gtfsId name } }',
            {"name": "Viru"},
        )
        assert "stops" in data


# --- search_stops live tests ---


class TestSearchStopsLive:
    @pytest.mark.asyncio
    async def test_viru(self):
        """Viru is a major stop in Tallinn — should always exist."""
        result = await search_stops("Viru")
        assert "Viru" in result
        assert "estonia:" in result

    @pytest.mark.asyncio
    async def test_balti_jaam(self):
        """Balti jaam (Baltic Station) — main train station."""
        result = await search_stops("Balti jaam")
        assert "Balti" in result

    @pytest.mark.asyncio
    async def test_nonexistent_stop(self):
        result = await search_stops("xyznonexistent12345")
        assert "No stops found" in result

    @pytest.mark.asyncio
    async def test_estonian_characters(self):
        """Test that Estonian special characters (õ, ä, ö, ü) work."""
        result = await search_stops("Põhja")
        assert "No stops found" not in result or "Põhja" in result


# --- get_departures live tests ---


class TestGetDeparturesLive:
    @pytest.mark.asyncio
    async def test_known_stop(self):
        """First search for a stop, then get its departures."""
        # Search for Viru to get a valid stop ID
        data = await _graphql(
            'query { stops(name: "Viru") { gtfsId name } }',
        )
        stops = data["stops"]
        assert len(stops) > 0, "Expected to find Viru stop"

        stop_id = stops[0]["gtfsId"]
        result = await get_departures(stop_id, 5)
        # Should either have departures or say "No upcoming departures"
        assert stops[0]["name"] in result or "No upcoming departures" in result

    @pytest.mark.asyncio
    async def test_invalid_stop_id(self):
        result = await get_departures("estonia:9999999")
        assert "Stop not found" in result

    @pytest.mark.asyncio
    async def test_limit_respected(self):
        """Request a small number of departures."""
        data = await _graphql(
            'query { stops(name: "Viru") { gtfsId } }',
        )
        stop_id = data["stops"][0]["gtfsId"]
        result = await get_departures(stop_id, 3)
        # Count departure lines (lines with " — " pattern)
        dep_lines = [l for l in result.split("\n") if " — " in l]
        assert len(dep_lines) <= 3


# --- plan_trip live tests ---


class TestPlanTripLive:
    @pytest.mark.asyncio
    async def test_tallinn_short_trip(self):
        """Plan a trip within central Tallinn — Viru to Balti jaam."""
        # Viru: 59.4369, 24.7535
        # Balti jaam: 59.4403, 24.7372
        result = await plan_trip(59.4369, 24.7535, 59.4403, 24.7372)
        assert "Option 1" in result or "No routes found" in result

    @pytest.mark.asyncio
    async def test_tallinn_to_tartu(self):
        """Longer trip — Tallinn to Tartu. May fail if OTP can't route it."""
        # Tallinn center: 59.437, 24.753
        # Tartu center: 58.378, 26.729
        result = await plan_trip(59.437, 24.753, 58.378, 26.729)
        # Either returns options or no routes — both are valid
        assert "Option 1" in result or "No routes found" in result

    @pytest.mark.asyncio
    async def test_outside_estonia(self):
        """Coordinates outside Estonia should not crash."""
        # Helsinki to Tallinn — should either route (ferry) or return no routes
        try:
            result = await plan_trip(60.17, 24.94, 59.44, 24.75)
            assert "Option" in result or "No routes found" in result
        except RuntimeError as e:
            # 500 from OTP is acceptable for out-of-bounds coordinates
            assert "server error" in str(e).lower()

    @pytest.mark.asyncio
    async def test_with_date_and_time(self):
        """Verify date and time parameters are accepted."""
        result = await plan_trip(
            59.4369, 24.7535, 59.4403, 24.7372,
            date="2026-04-01", time="09:00",
        )
        assert "Option 1" in result or "No routes found" in result

    @pytest.mark.asyncio
    async def test_arrive_by(self):
        """Test arrive_by parameter."""
        result = await plan_trip(
            59.4369, 24.7535, 59.4403, 24.7372,
            time="10:00", arrive_by=True,
        )
        assert "Option 1" in result or "No routes found" in result


# --- nearby_stops live tests ---


class TestNearbyStopsLive:
    @pytest.mark.asyncio
    async def test_tallinn_center(self):
        """Central Tallinn should have many stops nearby."""
        result = await nearby_stops(59.4369, 24.7535, 500)
        assert "estonia:" in result
        assert "No stops found" not in result

    @pytest.mark.asyncio
    async def test_middle_of_sea(self):
        """A point in the Baltic Sea should have no stops."""
        result = await nearby_stops(59.5, 24.0, 500)
        assert "No stops found" in result

    @pytest.mark.asyncio
    async def test_small_radius(self):
        """Very small radius in a residential area might find nothing."""
        # A point in a park
        result = await nearby_stops(59.45, 24.80, 10)
        # Either finds something or doesn't — both valid
        assert "stops" in result.lower() or "No stops found" in result


# --- get_route live tests ---


class TestGetRouteLive:
    @pytest.mark.asyncio
    async def test_known_route(self):
        """Find a route via stop search, then get its details."""
        # Search for a stop to find a route ID
        data = await _graphql(
            """query {
                stops(name: "Viru") {
                    routes { gtfsId shortName longName mode }
                }
            }""",
        )
        routes = []
        for stop in data["stops"]:
            routes.extend(stop["routes"])
        assert len(routes) > 0, "Expected routes serving Viru"

        route_id = routes[0]["gtfsId"]
        result = await get_route(route_id)
        assert "Route" in result
        assert "Mode:" in result

    @pytest.mark.asyncio
    async def test_invalid_route(self):
        result = await get_route("estonia:99999")
        assert "Route not found" in result


# --- tallinn_vehicles live tests ---


class TestTallinnVehiclesLive:
    @pytest.mark.asyncio
    async def test_all_vehicles(self):
        """Should return some active vehicles (may be empty at night)."""
        result = await tallinn_vehicles()
        # Either has vehicles or says none found
        assert "Active Tallinn vehicles" in result or "No active vehicles" in result

    @pytest.mark.asyncio
    async def test_filter_bus(self):
        result = await tallinn_vehicles(vehicle_type="bus")
        if "No active vehicles" not in result:
            assert "Bus" in result
            assert "Tram" not in result
            assert "Trolleybus" not in result

    @pytest.mark.asyncio
    async def test_filter_tram(self):
        result = await tallinn_vehicles(vehicle_type="tram")
        if "No active vehicles" not in result:
            assert "Tram" in result

    @pytest.mark.asyncio
    async def test_filter_by_line(self):
        result = await tallinn_vehicles(line="2")
        if "No active vehicles" not in result:
            assert "2" in result

    @pytest.mark.asyncio
    async def test_coordinates_in_tallinn(self):
        """All returned coordinates should be in the Tallinn area."""
        result = await tallinn_vehicles()
        if "Active Tallinn vehicles" in result:
            # Extract coordinate lines
            for line in result.split("\n"):
                if line.strip().startswith("59.") or line.strip().startswith("24."):
                    parts = line.strip().split(",")
                    if len(parts) >= 2:
                        lat = float(parts[0].strip())
                        lon = float(parts[1].strip().split()[0])
                        assert 59.3 < lat < 59.6, f"Latitude {lat} outside Tallinn"
                        assert 24.5 < lon < 25.0, f"Longitude {lon} outside Tallinn"
