# GoogleFindMyTools

This repository contains experimental tools that reimplement parts of Google's Find My Device Network, now called the Find Hub Network. It can query compatible trackers and Android devices, obtain their end-to-end encryption keys, and decrypt location reports. It also contains firmware for custom ESP32 and Zephyr trackers.

> [!WARNING]
> This project uses reimplemented, undocumented Google interfaces. It is not an official Google API or Google product, and upstream behavior may change without notice.

## Local Find Hub map

`main.py` starts a localhost-only web application backed by SQLite. The frontend reads cached devices and locations first; Google is contacted only when the user explicitly starts a synchronization.

### Requirements

- Python 3.12 or a compatible current Python 3 release;
- an up-to-date Google Chrome installation for authentication and browser E2E tests;
- network access for the real Google integration and OpenStreetMap tiles.

### Quick start on Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --demo
```

Open `http://127.0.0.1:8765/` if the browser does not open automatically. Demo mode uses synthetic devices and coordinates and never authenticates with Google.

For the real integration:

```powershell
.\.venv\Scripts\python.exe main.py
```

The first real synchronization can open the existing interactive Chrome authentication flow. Never paste credentials into the terminal, commit `Auth/secrets.json`, or expose the local server outside loopback.

Useful options:

```text
--host 127.0.0.1       loopback bind; non-loopback binds are refused
--port 8765            localhost HTTP port
--database PATH        override the per-user SQLite path
--demo                 synthetic, network-free Google gateway
--no-browser           do not open the default browser automatically
```

Without `--database`, data is stored under `%LOCALAPPDATA%\GoogleFindMyTools\find_hub.db` on Windows. The database contains location history and must be treated as private. Do not place it inside the repository or attach it to issues and pull requests.

### Authentication

On the first real synchronization, authentication may require a visible Google Chrome window. Authentication results are stored locally in `Auth/secrets.json`.

Treat that file as a credential: do not display, copy, share or commit it. Reauthenticate through the official interactive window when necessary.

### Tests

The default automated suite uses synthetic fixtures and does not contact Google:

```powershell
python -B -m unittest discover -s tests -v
```

The browser test is opt-in and requires Chrome plus Selenium:

```powershell
$env:RUN_BROWSER_E2E = '1'
python -B -m unittest tests.e2e.test_frontend_v1 -v
```

Real-account smoke testing is manual/opt-in. See [the architecture blueprint](arquitetura.md) and the sanitized [ARCH-013 smoke record](artifacts/ARCH-013-SMOKE.md). Never record real coordinates, device names, internal IDs, tokens or decrypted payloads in test artifacts.

### Architecture and API

The application is split into domain, application, infrastructure and presentation layers. SQLite migrations live in `migrations/`; the versioned localhost API is under `/api/v1`. The complete component map, contracts and incremental plan are maintained in [arquitetura.md](arquitetura.md).

### Privacy and security

- the HTTP server accepts loopback binds only;
- mutating endpoints validate `Host`, `Origin` and an ephemeral CSRF token;
- canonical Google IDs, credentials and raw payloads do not cross the presentation boundary;
- automated tests use synthetic identities and coordinates;
- location databases and screenshots are ignored by Git.

### Map attribution and third-party terms

The UI uses Leaflet and OpenStreetMap. Visible attribution must remain enabled. The public OpenStreetMap tile service is for normal interactive viewing only—no bulk download, prefetch or offline archive. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Known issues

- "Your encryption data is locked on your device" can appear if Find My Device was never configured on an Android device. Enable offline finding in Android under Settings → Google → Find My Device.
- trackers using the P-256 curve and 32-byte advertisements are not supported;
- the authentication process is not supported on ARM Linux;
- the frontend currently loads Leaflet from a CDN, so the map library itself requires network access;
- Google and the public OpenStreetMap tile service provide no compatibility or availability guarantee for this application.

## Firmware for custom trackers

Firmware and device-specific instructions are maintained separately:

- [ESP32 firmware](ESP32Firmware/README.md)
- [Zephyr firmware](ZephyrFirmware/README.md)

The map entrypoint no longer contains the legacy interactive tracker-registration menu. Follow the firmware-specific documentation and scripts instead.

## License and citation

The project is distributed under the [GNU General Public License version 3](LICENSE). Preserve the original copyright and license notices when redistributing modified versions.

Citation metadata is available in [CITATION.cff](CITATION.cff).
