"""MCP tool definitions for Estonian transport."""

from estonian_transport_mcp.api import graphql, fetch_tallinn_gps, VEHICLE_TYPES
from estonian_transport_mcp.formatting import fmt_seconds, fmt_time_of_day
from estonian_transport_mcp.server import mcp


@mcp.tool()
async def search_stops(name: str) -> str:
    """Search for Estonian public transport stops by name.

    Args:
        name: Stop name to search for (e.g. 'Viru', 'Balti jaam', 'Tartu')
    """
    data = await graphql(
        """
        query($name: String!) {
            stops(name: $name) {
                gtfsId name code lat lon vehicleMode
                routes { shortName longName mode }
            }
        }
        """,
        {"name": name},
    )
    stops = data["stops"]
    if not stops:
        return f'No stops found matching "{name}".'

    lines = []
    for s in stops[:30]:
        routes = ", ".join(f"{r['mode']} {r['shortName']}" for r in s["routes"])
        lines.append(
            f"**{s['name']}** ({s.get('code') or 'no code'}) — ID: `{s['gtfsId']}`\n"
            f"  Mode: {s.get('vehicleMode') or 'unknown'} | Routes: {routes or 'none'}\n"
            f"  {s['lat']}, {s['lon']}"
        )
    return f'Found {len(stops)} stops matching "{name}":\n\n' + "\n\n".join(lines)


@mcp.tool()
async def get_departures(stop_id: str, limit: int = 15) -> str:
    """Get upcoming departures from a specific stop.

    Args:
        stop_id: GTFS stop ID (e.g. '1:4173'). Use search_stops to find IDs.
        limit: Number of departures to return (default 15, max 50)
    """
    n = min(limit, 50)
    data = await graphql(
        """
        query($id: String!, $n: Int!) {
            stop(id: $id) {
                name code gtfsId
                stoptimesWithoutPatterns(numberOfDepartures: $n) {
                    scheduledDeparture realtimeDeparture realtime headsign
                    trip { route { shortName longName mode agency { name } } }
                }
            }
        }
        """,
        {"id": stop_id, "n": n},
    )
    stop = data["stop"]
    if not stop:
        return f"Stop not found: {stop_id}"

    deps = stop["stoptimesWithoutPatterns"]
    if not deps:
        return f"No upcoming departures from {stop['name']}."

    lines = []
    for d in deps:
        time = fmt_time_of_day(d["realtimeDeparture"])
        scheduled = fmt_time_of_day(d["scheduledDeparture"])
        rt = f" (scheduled {scheduled})" if d["realtime"] and d["realtimeDeparture"] != d["scheduledDeparture"] else ""
        r = d["trip"]["route"]
        lines.append(f"{time}{rt} — {r['mode']} **{r['shortName']}** → {d['headsign']} ({r['agency']['name']})")

    return f"Departures from **{stop['name']}** ({stop.get('code') or stop['gtfsId']}):\n\n" + "\n".join(lines)


@mcp.tool()
async def plan_trip(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    date: str | None = None,
    time: str | None = None,
    arrive_by: bool = False,
    num_results: int = 3,
) -> str:
    """Plan a public transport trip between two locations in Estonia.

    Args:
        from_lat: Origin latitude
        from_lon: Origin longitude
        to_lat: Destination latitude
        to_lon: Destination longitude
        date: Travel date YYYY-MM-DD (default: today)
        time: Travel time HH:MM (default: now)
        arrive_by: If true, time is desired arrival time
        num_results: Number of itinerary options (default 3)
    """
    data = await graphql(
        """
        query($fromLat: Float!, $fromLon: Float!, $toLat: Float!, $toLon: Float!,
              $numItineraries: Int!, $arriveBy: Boolean, $date: String, $time: String) {
            plan(from: {lat: $fromLat, lon: $fromLon}, to: {lat: $toLat, lon: $toLon},
                 numItineraries: $numItineraries, arriveBy: $arriveBy, date: $date, time: $time) {
                itineraries {
                    startTime endTime duration walkDistance
                    legs {
                        mode startTime endTime duration distance headsign
                        from { name stop { code name } }
                        to { name stop { code name } }
                        route { shortName longName agency { name } }
                    }
                }
            }
        }
        """,
        {
            "fromLat": from_lat, "fromLon": from_lon,
            "toLat": to_lat, "toLon": to_lon,
            "numItineraries": num_results, "arriveBy": arrive_by,
            "date": date, "time": time,
        },
    )
    itineraries = data["plan"]["itineraries"]
    if not itineraries:
        return "No routes found for this trip."

    results = []
    for i, it in enumerate(itineraries, 1):
        dur = fmt_seconds(it["duration"])
        walk_km = it["walkDistance"] / 1000

        legs = []
        for leg in it["legs"]:
            if leg["mode"] == "WALK":
                legs.append(f"  Walk {leg['distance']/1000:.1f}km ({fmt_seconds(leg['duration'])}) to {leg['to']['name']}")
            else:
                route = leg.get("route") or {}
                name = f"{route.get('shortName', '')} ({route.get('agency', {}).get('name', '')})" if route else leg["mode"]
                legs.append(
                    f"  {leg['mode']} **{name}** → {leg.get('headsign') or leg['to']['name']}\n"
                    f"    {leg['from']['name']} → {leg['to']['name']}"
                )

        results.append(f"**Option {i}**: {dur}, walk {walk_km:.1f}km\n" + "\n".join(legs))

    return "Trip options:\n\n" + "\n\n---\n\n".join(results)


@mcp.tool()
async def nearby_stops(lat: float, lon: float, radius: int = 500) -> str:
    """Find public transport stops near a given location.

    Args:
        lat: Latitude
        lon: Longitude
        radius: Search radius in meters (default 500, max 2000)
    """
    r = min(radius, 2000)
    data = await graphql(
        """
        query($lat: Float!, $lon: Float!, $radius: Int!) {
            stopsByRadius(lat: $lat, lon: $lon, radius: $radius) {
                edges { node { distance stop { gtfsId name code lat lon vehicleMode routes { shortName mode } } } }
            }
        }
        """,
        {"lat": lat, "lon": lon, "radius": r},
    )
    edges = data["stopsByRadius"]["edges"]
    if not edges:
        return f"No stops found within {r}m of {lat}, {lon}."

    lines = []
    for e in edges[:25]:
        s = e["node"]["stop"]
        dist = e["node"]["distance"]
        routes = ", ".join(r["shortName"] for r in s["routes"])
        lines.append(f"**{s['name']}** ({s.get('code') or 'no code'}) — {dist}m — ID: `{s['gtfsId']}`\n  Routes: {routes or 'none'}")

    return f"Stops within {r}m of {lat}, {lon}:\n\n" + "\n\n".join(lines)


@mcp.tool()
async def get_route(route_id: str) -> str:
    """Get details about a transport route including its stops.

    Args:
        route_id: GTFS route ID (e.g. '1:1'). Find these from stop search results.
    """
    data = await graphql(
        """
        query($id: String!) {
            route(id: $id) {
                gtfsId shortName longName mode
                agency { name }
                patterns { name headsign stops { gtfsId name code } }
            }
        }
        """,
        {"id": route_id},
    )
    route = data["route"]
    if not route:
        return f"Route not found: {route_id}"

    patterns = []
    for p in route["patterns"]:
        stops = "\n".join(f"  {s['name']} (`{s['gtfsId']}`)" for s in p["stops"])
        patterns.append(f"**{p.get('headsign') or p['name']}**:\n{stops}")

    return (
        f"**Route {route['shortName']}** — {route['longName']}\n"
        f"Mode: {route['mode']} | Agency: {route['agency']['name']}\n"
        f"ID: `{route['gtfsId']}`\n\n"
        f"Patterns:\n\n" + "\n\n".join(patterns)
    )


@mcp.tool()
async def tallinn_vehicles(
    vehicle_type: str | None = None,
    line: str | None = None,
) -> str:
    """Get real-time GPS positions of Tallinn public transport vehicles.

    Args:
        vehicle_type: Filter by type: 'bus', 'tram', or 'trolleybus' (default: all)
        line: Filter by line/route number (e.g. '2', '17', '42A')
    """
    type_filter = None
    if vehicle_type:
        for code, name in VEHICLE_TYPES.items():
            if name == vehicle_type.lower():
                type_filter = code
                break
        if type_filter is None:
            return f"Unknown vehicle type '{vehicle_type}'. Use 'bus', 'tram', or 'trolleybus'."

    raw = await fetch_tallinn_gps()

    vehicles = []
    for row in raw.strip().splitlines():
        parts = row.split(",")
        if len(parts) < 7:
            continue

        vtype, vline, lng_raw, lat_raw, _, heading, vid = parts[:7]
        destination = parts[9] if len(parts) > 9 else ""

        if lat_raw == "0" or lng_raw == "0":
            continue
        if vline == "0":
            continue

        if type_filter and vtype != type_filter:
            continue
        if line and vline != line:
            continue

        lat = int(lat_raw) / 1_000_000
        lon = int(lng_raw) / 1_000_000
        hdg = int(heading) if heading != "999" else None

        vehicles.append({
            "type": VEHICLE_TYPES.get(vtype, vtype),
            "line": vline,
            "lat": lat,
            "lon": lon,
            "heading": hdg,
            "vehicle_id": vid,
            "destination": destination,
        })

    if not vehicles:
        filters = []
        if vehicle_type:
            filters.append(f"type={vehicle_type}")
        if line:
            filters.append(f"line={line}")
        fstr = f" ({', '.join(filters)})" if filters else ""
        return f"No active vehicles found{fstr}."

    lines_out = []
    for v in vehicles[:50]:
        hdg_str = f" heading {v['heading']}°" if v["heading"] is not None else ""
        dest_str = f" → {v['destination']}" if v["destination"] else ""
        lines_out.append(
            f"**{v['type'].title()} {v['line']}**{dest_str} — vehicle {v['vehicle_id']}\n"
            f"  {v['lat']:.6f}, {v['lon']:.6f}{hdg_str}"
        )

    return f"Active Tallinn vehicles ({len(vehicles)} total, showing up to 50):\n\n" + "\n\n".join(lines_out)
