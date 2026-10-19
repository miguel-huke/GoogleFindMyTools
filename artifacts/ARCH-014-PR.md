# Pull request draft

## Suggested title

`feat: add SQLite-backed Find Hub map with Google integration jobs`

## Summary

- introduce domain, application, infrastructure and presentation layers;
- persist beacon inventory, location history and job state in SQLite migrations;
- adapt the existing Nova, FCM, Protobuf and decrypt flows behind a typed Google gateway;
- add a localhost API v1 with jobs, sanitized public IDs, CSRF and Host/Origin checks;
- migrate the Leaflet frontend to cached state, progress polling and on-demand history;
- wire `main.py` to real and synthetic demo gateways;
- document privacy, operation, licensing and third-party map requirements.

## Validation

- 67 automated tests pass, including unit, contract, SQLite, gateway, jobs, HTTP and bootstrap coverage;
- opt-in Chrome E2E passes with synthetic devices, locations and tiles;
- clean Python 3.12 virtualenv installation from `requirements.txt` passes;
- real Google smoke: inventory and one location refresh succeeded; only sanitized counts were retained;
- JavaScript syntax, Python AST, Markdown links, secret patterns and legacy-route references audited.

## Privacy

- no real coordinate, device name, canonical ID, token, key or payload is included;
- `Auth/secrets.json`, SQLite files and screenshots remain ignored;
- the sanitized real-smoke record documents the result and its reauthentication limitation.

## Known limitations

- Google integration relies on undocumented/reimplemented interfaces;
- fresh-login reauthentication was not forced because a valid cached session existed;
- Leaflet is loaded from `unpkg.com` and is not yet vendored;
- public OpenStreetMap tiles are best-effort and intended only for normal interactive use.

## Reviewer checklist

- [ ] verify architecture boundaries and API contracts;
- [ ] verify migrations on empty and existing databases;
- [ ] confirm no sensitive file is staged;
- [ ] review GPL-3.0 and third-party notices;
- [ ] run demo mode and inspect map buttons;
- [ ] keep real-account smoke manual and opt-in.
