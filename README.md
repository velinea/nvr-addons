# NVR Stream — Home Assistant Add-on

Stream cameras from an RTMP NVR to Home Assistant via [go2rtc](https://github.com/AlexxIT/go2rtc).

```
NVR (RTMP)  ──▶  connect.py  ──▶  go2rtc  ──▶  Home Assistant
                   (H.264)        (RTSP)
```

`connect.py` connects to the NVR via RTMP, extracts the H.264 Annex B bitstream, and pipes it to go2rtc. go2rtc serves each camera as an RTSP stream that Home Assistant can consume.

## Requirements

- **Home Assistant OS** (or Container)
- An NVR that serves cameras over RTMP with MD5 digest authentication
- Tested with NVR firmware that uses `view2.js` stream naming (`ch{N}_{M}.264`)

## Installation

1. Go to **Settings → Add-ons → Add-on Store**
2. Click the three-dot menu (top right) → **Repositories**
3. Add this repository URL:
   ```
   https://github.com/velinea/nvr-addons
   ```
4. Click **Save**, then find **NVR Stream** and click **Install**
5. Open the add-on **Configuration** tab and set your NVR details

## Configuration

| Option | Description | Default |
|---|---|---|
| `nvr_host` | NVR IP address | `192.168.1.250` |
| `nvr_port` | NVR RTMP port | `80` |
| `nvr_user` | NVR username | `admin` |
| `nvr_pass` | NVR password | _(empty)_ |
| `channels` | Comma-separated channel indices (0-based) | `0,1,2,3` |
| `streams` | Stream types to enable | `main,sub` |

### Stream naming

Streams are named `cam{channel}_{stream}`:

| Stream name | Channel | Type |
|---|---|---|
| `cam0_main` | 0 | Main (high res) |
| `cam0_sub` | 0 | Sub (low res) |
| `cam1_main` | 1 | Main (high res) |
| `cam1_sub` | 1 | Sub (low res) |
| ... | ... | ... |

### Ports

| Port | Protocol | Description |
|---|---|---|
| 1984 | TCP | go2rtc Web UI |
| 8554 | TCP | go2rtc RTSP server |

## Adding cameras to Home Assistant

### Option 1: Generic Camera (recommended)

1. **Settings → Devices & Services → + Integration → Generic Camera**
2. Set **Stream Source URL** to the RTSP address of a camera:
   ```
   rtsp://<HA_IP>:8554/cam0_sub
   ```
3. Set **RTSP transport** to **TCP**
4. Repeat for each camera/stream you want

### Option 2: go2rtc integration (WebRTC support)

If you want WebRTC live view for lower latency, also configure the go2rtc integration:

```yaml
# configuration.yaml
go2rtc:
  url: http://localhost:1984
```

Then restart Home Assistant. The go2rtc integration provides a WebRTC proxy for cameras already added via Generic Camera.

### Dashboard card

```yaml
type: picture-entity
entity: camera.cam0_sub
show_state: false
show_name: false
```

## Browser playback

go2rtc serves streams in multiple browser-friendly formats. Replace `<HA_IP>` with your Home Assistant IP.

### go2rtc Web UI (easiest)

Open `http://<HA_IP>:1984` — select a stream from the dropdown and play it directly. You can bookmark this page for quick access.

### MSE (low latency, Chrome/Edge)

```
http://<HA_IP>:1984/stream.html?src=cam0_sub
```

### HLS (Safari, iOS)

```
http://<HA_IP>:1984/api/stream.m3u8?src=cam0_sub
```

### WebRTC (lowest latency)

```
http://<HA_IP>:1984/webrtc.html?src=cam0_sub
```

## External access (Cloudflare tunnel)

If you access HA from outside your home network via a Cloudflare tunnel, you can expose go2rtc on a separate subdomain.

### Tunnel configuration

Add go2rtc as a route in your `config.yml` (usually `~/.cloudflared/config.yml`):

```yaml
ingress:
  - hostname: ha.mannikko.cc
    service: http://localhost:8123
  - hostname: go2rtc.mannikko.cc
    service: http://localhost:1984
  - service: http_status:404
```

Then restart cloudflared: `sudo systemctl restart cloudflared`

### What works through Cloudflare

| Protocol | Works? | URL |
|---|---|---|
| go2rtc Web UI | Yes | `https://go2rtc.mannikko.cc` |
| HLS | Yes | `https://go2rtc.mannikko.cc/api/stream.m3u8?src=cam0_sub` |
| MSE | Maybe | Depends on WebSocket support in your Cloudflare plan |
| WebRTC | No | Requires UDP — Cloudflare tunnels are HTTP-only |
| RTSP | No | Non-HTTP protocol |

The Web UI at `https://go2rtc.mannikko.cc` lets you select and play any stream directly in the browser from anywhere.

## Standalone usage

`connect.py` can also be used outside Home Assistant.

### Requirements

```bash
pip install python-librtmp
```

### Output raw H.264 to ffplay

```bash
python3 connect.py --nvr-host 192.168.1.250 --nvr-user admin --nvr-pass SECRET \
  -c 0 -s sub | ffplay -f h264 -i pipe:0
```

### Output FLV to ffplay

```bash
python3 connect.py --flv --nvr-host 192.168.1.250 --nvr-user admin --nvr-pass SECRET \
  -c 0 -s sub | ffplay -i pipe:0
```

### Generate go2rtc config snippet

```bash
python3 connect.py --go2rtc -c 0 -s sub --nvr-host 192.168.1.250
```

Output:
```yaml
streams:
  cam0_sub: exec:python3 /app/connect.py -c 0 -s sub --nvr-host 192.168.1.250#killsignal=15
```

### CLI options

| Flag | Description |
|---|---|
| `-c`, `--channel` | Camera channel (0–3, default: 0) |
| `-s`, `--stream` | Stream type: `main` or `sub` (default: `sub`) |
| `--flv` | Output FLV instead of raw H.264 |
| `--serve [PORT]` | Start HTTP-FLV server (default port 8080) |
| `--stdout` | Write to stdout (default when `--serve` is set) |
| `--go2rtc` | Print go2rtc YAML config and exit |
| `--nvr-host` | NVR host (or env `NVR_HOST`) |
| `--nvr-port` | NVR port (or env `NVR_PORT`) |
| `--nvr-user` | NVR username (or env `NVR_USER`) |
| `--nvr-pass` | NVR password (or env `NVR_PASS`) |

## Environment variables

`connect.py` reads from the environment when CLI args are not provided:

`NVR_HOST`, `NVR_PORT`, `NVR_USER`, `NVR_PASS`

## How it works

1. `connect.py` connects to the NVR via RTMP and authenticates using MD5 digest
2. It subscribes to the requested channel/stream and reads RTMP video packets
3. H.264 AVCC packets are converted to Annex B bitstream (SPS/PPS extracted from the AVC decoder configuration record)
4. The raw H.264 bitstream is piped to go2rtc via stdout
5. go2rtc detects the H.264 format and serves it as RTSP on port 8554
6. Home Assistant connects to the RTSP stream via the Generic Camera integration

## Troubleshooting

### Camera not playing in Home Assistant

- Make sure the RTSP transport is set to **TCP** in the Generic Camera configuration
- Check the add-on logs for connection errors
- Test the RTSP URL directly: `ffplay rtsp://<HA_IP>:8554/cam0_sub`

### go2rtc Web UI shows no streams

- Check the add-on logs — the generated `go2rtc.yaml` should be printed on startup
- Open `http://<HA_IP>:1984` to access the go2rtc Web UI and inspect streams

### Stream starts but is black/laggy

- Try the sub stream (`cam0_sub`) instead of main — it has lower bandwidth requirements
- Ensure your NVR supports the channel/stream you selected

### Adding the repository fails

- Make sure you're using the full URL: `https://github.com/velinea/nvr-addons`
- The repository must be added before the add-on appears in the store
