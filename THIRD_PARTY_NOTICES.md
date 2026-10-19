# Third-party notices

This file documents map-specific third-party components. Python packages installed from `requirements.txt` remain subject to their own licenses and notices.

## Leaflet 1.9.4

- Project: <https://leafletjs.com/>
- Source and license: <https://github.com/Leaflet/Leaflet>
- License: BSD 2-Clause (`BSD-2-Clause`)

The application currently loads Leaflet JavaScript and CSS from `unpkg.com`. Leaflet attribution remains visible in the map UI. If Leaflet is vendored for offline distribution, its copyright notice, license conditions and disclaimer must be shipped with the copied files.

## OpenStreetMap

- Copyright and licence: <https://www.openstreetmap.org/copyright>
- Raster tile usage policy: <https://operations.osmfoundation.org/policies/tiles/>
- Data license: Open Data Commons Open Database License (`ODbL`)

The UI displays `© OpenStreetMap contributors` with a link to the copyright page. The local proxy requests only tiles needed for the visible interactive viewport, uses an application-specific User-Agent and advertises a seven-day browser cache. Bulk download, prefetch and offline tile archives are not supported.

The public tile service is best-effort and may block clients that violate its policy. A distributed or higher-volume deployment must configure a suitable tile provider or self-hosted service instead of assuming availability of `tile.openstreetmap.org`.

## Project license

GoogleFindMyTools is distributed under the GNU General Public License version 3 as recorded in [LICENSE](LICENSE). This notice does not replace the full project or dependency license texts and is not legal advice.
