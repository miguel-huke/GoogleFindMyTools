import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from Auth.token_cache import get_cached_value, set_cached_value


class TokenCacheConfigurationTest(unittest.TestCase):
    def test_configured_private_path_is_created_and_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            auth_file = Path(directory) / "private" / "secrets.json"
            with mock.patch.dict(os.environ, {"GFMT_AUTH_FILE": str(auth_file)}):
                set_cached_value("synthetic", "test-only-value")
                self.assertEqual(get_cached_value("synthetic"), "test-only-value")

            self.assertTrue(auth_file.is_file())


if __name__ == "__main__":
    unittest.main()
