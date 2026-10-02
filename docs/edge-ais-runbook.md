# Edge AIS operations runbook

This runbook starts SeaWatch on one Windows laptop with a local AIS radio feed.
Edge coverage is only what the attached VHF/AIS antenna can receive; it is not
the Taiwan-wide network coverage shown in Cloud Live.

## Hardware and power

- Windows laptop with the prepared repository, Python environment, built web UI,
  and provisioned Playwright Chromium
- RTL-SDR supported by AIS-catcher
- VHF/AIS antenna suitable for 161.975 MHz and 162.025 MHz, feed line, and the
  correct adapter
- laptop battery and/or tested UPS; mains power alone is not resilient

Position the antenna legally and safely. Do not transmit: this workflow is
receive-only. Verify battery runtime before an exercise.

## Start a real local receiver

Install and validate AIS-catcher separately. A representative command shape is:

```powershell
AIS-catcher.exe -d:0 -u 127.0.0.1 10110
```

Device selection and gain flags vary by receiver and AIS-catcher release; use
`AIS-catcher.exe -h` for the installed version. The invariant is UDP NMEA output
to `127.0.0.1:10110`. Do not bind an unauthenticated receiver feed publicly.

In a second PowerShell window at the repository root:

```powershell
$env:SEAWATCH_LIVE_INGEST = "true"
$env:SEAWATCH_EDGE_INGEST = "true"
$env:SEAWATCH_EDGE_HOST = "127.0.0.1"
$env:SEAWATCH_EDGE_PORT = "10110"
$env:SEAWATCH_POWER_MODE = "battery_ups"
$env:SEAWATCH_SERVE_WEB = "true"
$env:SEAWATCH_WEB_DIST = "apps/web/dist"
.\.venv\Scripts\python.exe -m uvicorn apps.api.seawatch.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/live/health
Invoke-RestMethod http://127.0.0.1:8000/edge/health
Invoke-RestMethod http://127.0.0.1:8000/resilience/status
```

`EDGE_LIVE` is valid only after real AIS is decoded from the local AIS-catcher
UDP input. With no SDR, no AIS-catcher, no bind, or no decodable reception, the
API and Cloud Live remain available and Edge health reports the bounded failure.

## Explicit replay and drill modes

Recorded NMEA is never RF live. To test replay, disable UDP Edge ingest and set:

```powershell
$env:SEAWATCH_EDGE_INGEST = "false"
$env:SEAWATCH_EDGE_REPLAY_ENABLED = "true"
$env:SEAWATCH_EDGE_REPLAY_FILE = "tests/fixtures/ais/edge_nmea.txt"
```

The UI must say `EDGE_REPLAY`. For a deterministic policy demonstration that
does not start a server or bind a port:

```powershell
.\.venv\Scripts\python.exe scripts/resilience_drill.py --enable-simulation
```

Every drill record is labeled `SIMULATED`.

## Failure and recovery exercise

1. Start Cloud and real Edge sources; confirm `CLOUD_LIVE`.
2. Disconnect Internet only after the local page and map assets are ready.
3. Confirm `EDGE_LIVE`, local-antenna coverage text, and continuing local fixes.
4. Confirm `/resilience/status` reports Cloud stale and Edge fresh.
5. Restore Internet. Cloud remains held until
   `SEAWATCH_CLOUD_RECOVERY_SECONDS` elapses continuously.
6. Confirm the restoration banner and `CLOUD_LIVE`.

Do not disable Windows networking as part of the simulation-only script. A real
disconnect exercise is an operator action outside SeaWatch.

## Troubleshooting

- No receiver detected: check USB driver/device selection and AIS-catcher output.
- Receiver active, no AIS: check antenna, cable, gain, location, and local vessel
  traffic. Local reception can legitimately be empty.
- Bind failure: ensure only one process owns UDP 10110 and host is loopback.
- Cloud remains selected: Edge does not supersede a fresh Cloud source.
- Replay says `EDGE_LIVE`: stop; configuration or code is wrong. Replay must be
  `EDGE_REPLAY`.
- Laptop loses power: use a charged battery or UPS; software cannot supply power
  resilience.
