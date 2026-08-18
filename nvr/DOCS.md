# NVR Stream

Streams cameras from your NVR to Home Assistant via go2rtc.

## Installation

1. Go to **Settings** → **Add-ons** → **Add-on Store**
2. Click the three-dot menu (top right) → **Repositories**
3. Paste your repository URL and click **Save**
4. Find **NVR Stream** and click **Install**

## Configuration

Set these options in the add-on configuration tab:

| Option | Description | Default |
|--------|-------------|---------|
| `nvr_host` | NVR IP address | `192.168.1.250` |
| `nvr_port` | NVR RTMP port | `80` |
| `nvr_user` | NVR username | `admin` |
| `nvr_pass` | NVR password | (empty) |
| `channels` | Comma-separated channel indices | `0,1,2,3` |
| `streams` | Stream types to enable | `main,sub` |

## Home Assistant Integration

The add-on exposes go2rtc on ports 1984 (Web UI) and 8554 (RTSP).

### Automatic discovery

If you have the built-in go2rtc integration, add this to `configuration.yaml`:

```yaml
go2rtc:
  url: http://localhost:1984
```

Then restart Home Assistant. Cameras will appear automatically.

### Manual camera setup

You can also add cameras via **Settings** → **Devices & Services** → **Generic Camera**:
- Stream URL: `rtsp://localhost:8554/cam0_sub`

## Dashboard

Add a camera card to your dashboard:

```yaml
type: picture-entity
entity: camera.cam0_sub
show_state: false
show_name: false
```

## Exposed Streams

With default settings (4 channels, main+sub), these streams are available:

- `cam0_main`, `cam0_sub` - Channel 1
- `cam1_main`, `cam1_sub` - Channel 2
- `cam2_main`, `cam2_sub` - Channel 3
- `cam3_main`, `cam3_sub` - Channel 4

Access via RTSP: `rtsp://localhost:8554/cam0_main`
Web UI: `http://localhost:1984/`
