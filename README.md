# Estonian Transport MCP

An MCP (Model Context Protocol) server that provides Estonian public transport timetable data. Powered by the [peatus.ee](https://peatus.ee) OpenTripPlanner API.

## Tools

| Tool | Description |
|------|-------------|
| `search_stops` | Search for stops by name |
| `get_departures` | Get upcoming departures from a stop |
| `plan_trip` | Plan a trip between two coordinates |
| `nearby_stops` | Find stops near a location |
| `get_route` | Get route details and stop patterns |
| `tallinn_vehicles` | Real-time GPS positions of Tallinn buses, trams, trolleybuses |

## Usage with Claude Code

```json
{
  "mcpServers": {
    "estonian-transport": {
      "command": "uvx",
      "args": ["estonian-transport-mcp"]
    }
  }
}
```

## Data Sources

- **API**: `api.peatus.ee` — OpenTripPlanner GraphQL endpoint maintained by the Estonian Transport Administration (Transpordiamet)
- **Coverage**: All Estonian public transport including buses, trams, trolleybuses, trains, and ferries
- **Realtime**: Includes real-time arrival predictions where available
- **Tallinn GPS**: `transport.tallinn.ee/gps.txt` — live vehicle positions updated every ~10 seconds (Tallinn only)
