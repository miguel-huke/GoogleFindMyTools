"""Default UTC clock for application use cases."""

import time


class SystemClock:
    def now_utc_seconds(self) -> int:
        return int(time.time())
