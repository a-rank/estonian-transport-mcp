"""Unit tests for Estonian Transport MCP server (mocked HTTP)."""

import pytest
import httpx
import respx

from estonian_transport_mcp import (
    graphql,
    fmt_seconds,
    fmt_time_of_day,
    search_stops,
    get_departures,
    plan_trip,
    nearby_stops,
    get_route,
    get_trip_stops,
    tallinn_vehicles,
    OTP_GRAPHQL_URL,
    TALLINN_GPS_URL,
)


# --- Unit tests for formatting helpers ---


class TestFormatSeconds:
    def test_minutes_only(self):
        assert fmt_seconds(300) == "5m"

    def test_hours_and_minutes(self):
        assert fmt_seconds(3900) == "1h 5m"

    def test_zero(self):
        assert fmt_seconds(0) == "0m"

    def test_exact_hour(self):
        assert fmt_seconds(7200) == "2h 0m"


class TestFormatTimeOfDay:
    def test_morning(self):
        assert fmt_time_of_day(8 * 3600 + 30 * 60) == "08:30"

    def test_midnight(self):
        assert fmt_time_of_day(0) == "00:00"

    def test_afternoon(self):
        assert fmt_time_of_day(15 * 3600 + 45 * 60) == "15:45"

    def test_past_midnight(self):
        # OTP can return >24h for next-day trips
        assert fmt_time_of_day(25 * 3600) == "25:00"


# --- Unit tests for GraphQL client ---


class TestGraphqlClient:
    @respx.mock
    @pytest.mark.asyncio
    async def test_successful_request(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"stops": []}})
        )
        result = await graphql("{ stops { name } }")
        assert result == {"stops": []}

    @respx.mock
    @pytest.mark.asyncio
    async def test_500_error(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        with pytest.raises(RuntimeError, match="peatus.ee API returned a server error"):
            await graphql("{ stops { name } }")

    @respx.mock
    @pytest.mark.asyncio
    async def test_graphql_error(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200, json={"errors": [{"message": "Field not found"}]}
            )
        )
        with pytest.raises(RuntimeError, match="Field not found"):
            await graphql("{ bad_query }")

    @respx.mock
    @pytest.mark.asyncio
    async def test_http_error(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(403, text="Forbidden")
        )
        with pytest.raises(httpx.HTTPStatusError):
            await graphql("{ stops { name } }")


# --- Tests for search_stops ---


class TestSearchStops:
    @respx.mock
    @pytest.mark.asyncio
    async def test_found(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"stops": [
                {
                    "gtfsId": "estonia:1234",
                    "name": "Viru",
                    "code": "A1",
                    "lat": 59.4369,
                    "lon": 24.7535,
                    "vehicleMode": "BUS",
                    "routes": [{"shortName": "2", "longName": "Route 2", "mode": "BUS"}],
                }
            ]}})
        )
        result = await search_stops("Viru")
        assert "Viru" in result
        assert "estonia:1234" in result
        assert "BUS 2" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_not_found(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"stops": []}})
        )
        result = await search_stops("nonexistent_xyz")
        assert "No stops found" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_code(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"stops": [
                {
                    "gtfsId": "estonia:5678",
                    "name": "Test Stop",
                    "code": None,
                    "lat": 59.0,
                    "lon": 24.0,
                    "vehicleMode": None,
                    "routes": [],
                }
            ]}})
        )
        result = await search_stops("Test")
        assert "no code" in result
        assert "unknown" in result


# --- Tests for get_departures ---


class TestGetDepartures:
    @respx.mock
    @pytest.mark.asyncio
    async def test_with_departures(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"stop": {
                "name": "Viru",
                "code": "A1",
                "gtfsId": "estonia:1234",
                "stoptimesWithoutPatterns": [
                    {
                        "scheduledDeparture": 36000,  # 10:00
                        "realtimeDeparture": 36120,   # 10:02
                        "realtime": True,
                        "headsign": "Kadriorg",
                        "trip": {"gtfsId": "1:tram1_trip", "route": {
                            "shortName": "1",
                            "longName": "Tram 1",
                            "mode": "TRAM",
                            "agency": {"name": "TLT"},
                        }},
                    }
                ],
            }}})
        )
        result = await get_departures("estonia:1234", 5)
        assert "Viru" in result
        assert "10:02" in result
        assert "(scheduled 10:00)" in result
        assert "Kadriorg" in result
        assert "TRAM" in result
        assert "trip `1:tram1_trip`" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_realtime_diff(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"stop": {
                "name": "Balti jaam",
                "code": "B1",
                "gtfsId": "estonia:5678",
                "stoptimesWithoutPatterns": [
                    {
                        "scheduledDeparture": 43200,
                        "realtimeDeparture": 43200,
                        "realtime": True,
                        "headsign": "Tartu",
                        "trip": {"gtfsId": "1:e1_trip", "route": {
                            "shortName": "E1",
                            "longName": "Express",
                            "mode": "RAIL",
                            "agency": {"name": "Elron"},
                        }},
                    }
                ],
            }}})
        )
        result = await get_departures("estonia:5678")
        assert "12:00" in result
        assert "(scheduled" not in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_stop_not_found(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"stop": None}})
        )
        result = await get_departures("estonia:9999")
        assert "Stop not found" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_departures(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"stop": {
                "name": "Empty Stop",
                "code": "X1",
                "gtfsId": "estonia:0000",
                "stoptimesWithoutPatterns": [],
            }}})
        )
        result = await get_departures("estonia:0000")
        assert "No upcoming departures" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_limit_capped_at_50(self):
        route = respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"stop": {
                "name": "Test",
                "code": "T1",
                "gtfsId": "estonia:1111",
                "stoptimesWithoutPatterns": [],
            }}})
        )
        await get_departures("estonia:1111", 100)
        request_body = route.calls[0].request.content
        assert b'"n": 50' in request_body or b'"n":50' in request_body


# --- Tests for plan_trip ---


class TestPlanTrip:
    @respx.mock
    @pytest.mark.asyncio
    async def test_with_results(self):
        resolve_resp = httpx.Response(200, json={"data": {"stops": [
            {"name": "Test Stop", "lat": 59.43, "lon": 24.75}
        ]}})
        plan_resp = httpx.Response(200, json={"data": {"plan": {"itineraries": [
            {
                "startTime": 1711616400000,
                "endTime": 1711618200000,
                "duration": 1800,
                "walkDistance": 500,
                "legs": [
                    {
                        "mode": "WALK",
                        "startTime": 1711616400000,
                        "endTime": 1711616700000,
                        "duration": 300,
                        "distance": 250,
                        "from": {"name": "Origin", "stop": None},
                        "to": {"name": "Bus Stop", "stop": {"code": "A1", "name": "Bus Stop"}},
                        "trip": None,
                        "route": None,
                    },
                    {
                        "mode": "BUS",
                        "startTime": 1711616700000,
                        "endTime": 1711618000000,
                        "duration": 1300,
                        "distance": 5000,
                        "from": {"name": "Bus Stop", "stop": {"code": "A1", "name": "Bus Stop"}},
                        "to": {"name": "Destination", "stop": {"code": "B1", "name": "Destination"}},
                        "trip": {"tripHeadsign": "Kadriorg"},
                        "route": {"shortName": "5", "longName": "Bus 5", "agency": {"name": "TLT"}},
                    },
                ],
            }
        ]}}})
        respx.post(OTP_GRAPHQL_URL).mock(side_effect=[resolve_resp, resolve_resp, plan_resp])
        result = await plan_trip("Origin", "Destination")
        assert "Option 1" in result
        assert "Walk" in result
        assert "BUS" in result
        assert "Kadriorg" in result
        assert "0.5km" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_routes(self):
        resolve_resp = httpx.Response(200, json={"data": {"stops": [
            {"name": "Test Stop", "lat": 59.43, "lon": 24.75}
        ]}})
        plan_resp = httpx.Response(200, json={"data": {"plan": {"itineraries": []}}})
        respx.post(OTP_GRAPHQL_URL).mock(side_effect=[resolve_resp, resolve_resp, plan_resp])
        result = await plan_trip("Origin", "Destination")
        assert "No routes found" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_unknown_place(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"stops": []}})
        )
        result = await plan_trip("xyznonexistent", "Viru")
        assert "Could not find" in result


# --- Tests for nearby_stops ---


class TestNearbyStops:
    @respx.mock
    @pytest.mark.asyncio
    async def test_found(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"stopsByRadius": {"edges": [
                {"node": {"distance": 150, "stop": {
                    "gtfsId": "estonia:1234",
                    "name": "Nearby Stop",
                    "code": "N1",
                    "lat": 59.437,
                    "lon": 24.754,
                    "vehicleMode": "BUS",
                    "routes": [{"shortName": "3", "mode": "BUS"}],
                }}},
            ]}}})
        )
        result = await nearby_stops(59.4369, 24.7535)
        assert "Nearby Stop" in result
        assert "150m" in result
        assert "estonia:1234" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_none_found(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"stopsByRadius": {"edges": []}}})
        )
        result = await nearby_stops(60.0, 25.0, 100)
        assert "No stops found" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_radius_capped(self):
        route = respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"stopsByRadius": {"edges": []}}})
        )
        await nearby_stops(59.0, 24.0, 5000)
        request_body = route.calls[0].request.content
        assert b'"radius": 2000' in request_body or b'"radius":2000' in request_body


# --- Tests for get_route ---


class TestGetRoute:
    @respx.mock
    @pytest.mark.asyncio
    async def test_found(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"route": {
                "gtfsId": "estonia:1",
                "shortName": "1",
                "longName": "Kopli - Kadriorg",
                "mode": "TRAM",
                "agency": {"name": "TLT"},
                "patterns": [
                    {
                        "name": "Pattern 1",
                        "headsign": "Kadriorg",
                        "stops": [
                            {"gtfsId": "estonia:100", "name": "Kopli", "code": "K1"},
                            {"gtfsId": "estonia:101", "name": "Kadriorg", "code": "K2"},
                        ],
                    }
                ],
            }}})
        )
        result = await get_route("estonia:1")
        assert "Route 1" in result
        assert "Kopli - Kadriorg" in result
        assert "TRAM" in result
        assert "Kadriorg" in result
        assert "Kopli" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_not_found(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"route": None}})
        )
        result = await get_route("estonia:9999")
        assert "Route not found" in result


# --- Tests for get_trip_stops ---


class TestGetTripStops:
    @respx.mock
    @pytest.mark.asyncio
    async def test_found(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"trip": {
                "gtfsId": "1:151_20250329_1_1",
                "tripHeadsign": "Balti jaam",
                "route": {
                    "shortName": "151",
                    "longName": "Rihumägi - Balti jaam",
                    "mode": "BUS",
                    "agency": {"name": "Harjumaa ÜTK"},
                },
                "stoptimes": [
                    {
                        "scheduledArrival": 32400, "scheduledDeparture": 32400,
                        "realtimeArrival": 32400, "realtimeDeparture": 32400,
                        "realtime": False,
                        "stop": {"gtfsId": "1:5432", "name": "Rihumägi", "code": "5432"},
                    },
                    {
                        "scheduledArrival": 33300, "scheduledDeparture": 33360,
                        "realtimeArrival": 33300, "realtimeDeparture": 33360,
                        "realtime": False,
                        "stop": {"gtfsId": "1:11501", "name": "Laulupeo", "code": "11501"},
                    },
                    {
                        "scheduledArrival": 34500, "scheduledDeparture": 34500,
                        "realtimeArrival": 34500, "realtimeDeparture": 34500,
                        "realtime": False,
                        "stop": {"gtfsId": "1:5001", "name": "Balti jaam", "code": "5001"},
                    },
                ],
            }}})
        )
        result = await get_trip_stops("1:151_20250329_1_1")
        assert "151" in result
        assert "Rihumägi" in result
        assert "Laulupeo" in result
        assert "Balti jaam" in result
        assert "09:00" in result  # 32400 = 9:00
        assert "09:15" in result  # 33300 = 9:15
        assert "09:35" in result  # 34500 = 9:35

    @respx.mock
    @pytest.mark.asyncio
    async def test_realtime_delay(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"trip": {
                "gtfsId": "1:2_20250329_1_1",
                "tripHeadsign": "Kopli",
                "route": {
                    "shortName": "2",
                    "longName": "Kopli - Kadriorg",
                    "mode": "TRAM",
                    "agency": {"name": "TLT"},
                },
                "stoptimes": [
                    {
                        "scheduledArrival": 36000, "scheduledDeparture": 36000,
                        "realtimeArrival": 36120, "realtimeDeparture": 36120,
                        "realtime": True,
                        "stop": {"gtfsId": "1:100", "name": "Kadriorg", "code": "K1"},
                    },
                ],
            }}})
        )
        result = await get_trip_stops("1:2_20250329_1_1")
        assert "10:02" in result  # realtime arrival (36120)
        assert "scheduled 10:00" in result  # scheduled was 36000

    @respx.mock
    @pytest.mark.asyncio
    async def test_not_found(self):
        respx.post(OTP_GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"trip": None}})
        )
        result = await get_trip_stops("1:nonexistent")
        assert "Trip not found" in result


# --- Tests for tallinn_vehicles ---


SAMPLE_GPS_DATA = """\
3,2,24669000,59461300,,316,96,Z,248,Kopli
2,17,24745200,59437100,,180,1908,Z,85,Kadriorg
1,3,24700000,59440000,,90,42,Z,120,Tondi
2,0,24700000,59440000,,90,55,Z,0,
2,5,0,0,,999,77,Z,0,
"""


class TestTallinnVehicles:
    @respx.mock
    @pytest.mark.asyncio
    async def test_all_vehicles(self):
        respx.get(TALLINN_GPS_URL).mock(
            return_value=httpx.Response(200, text=SAMPLE_GPS_DATA)
        )
        result = await tallinn_vehicles()
        assert "Tram 2" in result
        assert "Bus 17" in result
        assert "Trolleybus 3" in result
        assert "vehicle 55" not in result
        assert "vehicle 77" not in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_filter_by_type(self):
        respx.get(TALLINN_GPS_URL).mock(
            return_value=httpx.Response(200, text=SAMPLE_GPS_DATA)
        )
        result = await tallinn_vehicles(vehicle_type="tram")
        assert "Tram 2" in result
        assert "Bus" not in result
        assert "Trolleybus" not in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_filter_by_line(self):
        respx.get(TALLINN_GPS_URL).mock(
            return_value=httpx.Response(200, text=SAMPLE_GPS_DATA)
        )
        result = await tallinn_vehicles(line="17")
        assert "Bus 17" in result
        assert "Tram" not in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_unknown_type(self):
        result = await tallinn_vehicles(vehicle_type="helicopter")
        assert "Unknown vehicle type" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_vehicles(self):
        respx.get(TALLINN_GPS_URL).mock(
            return_value=httpx.Response(200, text="2,0,24700000,59440000,,90,55,Z,0,\n")
        )
        result = await tallinn_vehicles()
        assert "No active vehicles" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_heading_999_filtered(self):
        respx.get(TALLINN_GPS_URL).mock(
            return_value=httpx.Response(200, text="2,5,24700000,59440000,,999,88,Z,100,Tondi\n")
        )
        result = await tallinn_vehicles()
        assert "heading" not in result
        assert "Bus 5" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_coordinate_parsing(self):
        respx.get(TALLINN_GPS_URL).mock(
            return_value=httpx.Response(200, text="3,1,24669000,59461300,,316,96,Z,248,Kopli\n")
        )
        result = await tallinn_vehicles()
        assert "59.461300" in result
        assert "24.669000" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_destination_shown(self):
        respx.get(TALLINN_GPS_URL).mock(
            return_value=httpx.Response(200, text="3,2,24669000,59461300,,316,96,Z,248,Kopli\n")
        )
        result = await tallinn_vehicles()
        assert "Kopli" in result
