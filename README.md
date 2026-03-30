# Estonian Transport MCP

An [MCP](https://modelcontextprotocol.io/) server for Estonian public transport — timetables, trip planning, stop search, and real-time vehicle tracking.

## Tools

| Tool | Description |
|------|-------------|
| `search_stops` | Search for stops by name (e.g. "Viru", "Balti jaam") |
| `get_departures` | Get upcoming departures from a stop, with real-time predictions |
| `plan_trip` | Plan a trip between two coordinates with date/time options |
| `nearby_stops` | Find stops within a radius of a location |
| `get_route` | Get route details including all stop patterns |
| `tallinn_vehicles` | Real-time GPS positions of Tallinn buses, trams, and trolleybuses |

## Prerequisites

This server runs via [uvx](https://docs.astral.sh/uv/), a zero-install Python package runner. Install `uv` first:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# or via Homebrew
brew install uv
```

No other setup needed — `uvx` automatically downloads dependencies on first run.

## Usage

### Claude Code

Add to your MCP settings (`.claude/settings.json` or project-level `.mcp.json`):

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

### Claude Desktop

Config file location:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add to the `mcpServers` section:

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

> **Note**: Claude Desktop may not find `uvx` in its PATH. If the server fails to start, replace `"uvx"` with the full path. Find it by running `which uvx` in your terminal, then use that path:
>
> ```json
> {
>   "mcpServers": {
>     "estonian-transport": {
>       "command": "/Users/yourname/.local/bin/uvx",
>       "args": ["estonian-transport-mcp"]
>     }
>   }
> }
> ```

Restart Claude Desktop after saving the config.

### Remote server (HTTP)

Run as an HTTP server for remote access (e.g. from claude.ai/code on mobile):

```bash
estonian-transport-mcp --transport streamable-http --port 8000
```

Then connect to it from any MCP client using the URL `http://your-server:8000/mcp`.

Example deployment with systemd on a VPS:

```ini
[Unit]
Description=Estonian Transport MCP
After=network.target

[Service]
ExecStart=/home/user/.local/bin/estonian-transport-mcp --transport streamable-http --port 8000
Restart=always
User=user

[Install]
WantedBy=multi-user.target
```

### Manual testing

```bash
# stdio mode (default)
uvx estonian-transport-mcp

# HTTP mode
uvx estonian-transport-mcp --transport streamable-http --port 8000
```

Test interactively with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uvx estonian-transport-mcp
```

## Data Sources & APIs

### Peatus.ee — OpenTripPlanner GraphQL API

- **Endpoint**: `https://api.peatus.ee/routing/v1/routers/estonia/index/graphql`
- **Protocol**: GraphQL over HTTP POST
- **Authentication**: None (open access)
- **Maintained by**: Transpordiamet (Estonian Transport Administration)
- **Coverage**: All Estonian public transport — buses, trams, trolleybuses, trains, and ferries nationwide
- **Data**: Stop search, departure times, trip planning, route patterns, real-time arrival predictions
- **Based on**: [OpenTripPlanner](https://www.opentripplanner.org/) with [Digitransit](https://digitransit.fi/)
- **Underlying data**: National GTFS feed consolidated from all Estonian transport operators

Used by tools: `search_stops`, `get_departures`, `plan_trip`, `nearby_stops`, `get_route`

### Tallinn Transport — Real-Time Vehicle GPS

- **Endpoint**: `https://transport.tallinn.ee/gps.txt`
- **Protocol**: Plain-text CSV over HTTP GET
- **Authentication**: None (open access)
- **Update frequency**: ~10 seconds
- **Coverage**: Tallinn city only — buses, trams, and trolleybuses operated by TLT (Tallinna Linnatransport)
- **Data**: Vehicle type, line number, GPS coordinates (WGS84 microdegrees), heading, vehicle ID, destination
- **Format**: Each line is one vehicle: `type,line,lon,lat,,heading,vehicle_id,status,unknown,destination`
  - Vehicle types: `1` = trolleybus, `2` = bus, `3` = tram
  - Coordinates: integer microdegrees (divide by 1,000,000 for decimal degrees)
  - Heading `999` = unknown

Used by tools: `tallinn_vehicles`

## Tech Stack

- **Python** with [FastMCP](https://github.com/modelcontextprotocol/python-sdk) (`mcp[cli]`)
- **httpx** for async HTTP requests
- **Transport**: stdio (standard MCP transport for local integrations)
