import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ContainerDefinitionTest(unittest.TestCase):
    def test_dockerfile_has_reproducible_non_root_runtime_contract(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("FROM python:3.12.15-slim-bookworm", dockerfile)
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn("/api/v1/health", dockerfile)
        self.assertIn('CMD ["python", "-B", "main.py", "--no-browser"]', dockerfile)
        self.assertIn("GFMT_DATABASE_PATH=/data/find_hub.db", dockerfile)
        self.assertIn("/state/auth/secrets.json", dockerfile)
        self.assertNotIn("COPY . .", dockerfile)
        self.assertNotIn("secrets.json ./", dockerfile)

    def test_dockerfile_copies_every_runtime_package(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        runtime_paths = (
            "Auth",
            "FMDNCrypto",
            "KeyBackup",
            "MapApp",
            "NovaApi",
            "ProtoDecoders",
            "SpotApi",
            "migrations",
            "scripts",
        )

        for path in runtime_paths:
            with self.subTest(path=path):
                self.assertIn(f"COPY {path} ./{path}", dockerfile)

    def test_dockerignore_excludes_private_and_generated_state(self):
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        required_rules = {
            "Auth/secrets.json",
            "**/__pycache__/",
            "**/*.py[cod]",
            "**/*.db",
            "**/*.db-wal",
            "**/*.db-shm",
            "**/*.sqlite3",
            "**/.venv/",
        }

        self.assertTrue(required_rules.issubset(set(dockerignore)))

    def test_compose_defines_isolated_demo_real_and_test_services(self):
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

        self.assertIn("  app:\n", compose)
        self.assertIn("  app-real:\n", compose)
        self.assertIn("  tests:\n", compose)
        self.assertIn("image: ${GFMT_IMAGE:-googlefindmytools-map:local}", compose)
        self.assertIn('127.0.0.1:${GFMT_DEMO_PORT:-8765}:8765', compose)
        self.assertIn('127.0.0.1:${GFMT_REAL_PORT:-8766}:8765', compose)
        self.assertIn("- gfmt-real-auth:/state/auth", compose)
        self.assertIn("network_mode: none", compose)
        self.assertIn('GFMT_ALLOW_NON_LOOPBACK: "false"', compose)
        self.assertIn("no-new-privileges:true", compose)
        self.assertIn("cap_drop:\n    - ALL", compose)
        self.assertNotIn("Auth/secrets.json:", compose)


if __name__ == "__main__":
    unittest.main()
