from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DeploymentAssetTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_runtime_versions_are_explicit_and_verified(self):
        versions = self.read("deploy/runtime-versions.conf")
        self.assertIn("NODE_VERSION=24.18.0", versions)
        self.assertIn("PYTHON_VERSION=3.12", versions)
        self.assertIn("NPM_VERSION=11.16.0", versions)
        build_script = self.read("deploy/scripts/build-release.sh")
        self.assertIn('"$(npm --version)" != "${NPM_VERSION}"', build_script)

    def test_bootstrap_does_not_expose_the_application(self):
        config = self.read("deploy/nginx/gongxing-bootstrap.conf")
        self.assertIn("test.novocaine.me", config)
        self.assertIn("/.well-known/acme-challenge/", config)
        self.assertNotIn("proxy_pass", config)
        self.assertNotIn("frontend/dist", config)
        self.assertRegex(config, r"return (?:404|503)")

    def test_final_nginx_security_contract(self):
        config = self.read("deploy/nginx/gongxing-test.conf")
        headers = self.read(
            "deploy/nginx/snippets/gongxing-security-headers.conf"
        )
        required = [
            "auth_basic_user_file /etc/nginx/gongxing.htpasswd",
            "client_max_body_size 52m",
            "gzip_vary on",
            "ssl_reject_handshake on",
            "location = /api",
            "location /api/",
            "location = /data",
            "location /data/",
            "try_files $uri $uri/ /index.html",
        ]
        for value in required:
            self.assertIn(value, config)
        for value in (
            "X-Robots-Tag",
            "X-Content-Type-Options",
            "Referrer-Policy",
            "X-Frame-Options",
            "Permissions-Policy",
        ):
            self.assertIn(value, headers)
        log_format = re.search(
            r"log_format gongxing_safe(?P<body>.*?);",
            config,
            re.DOTALL,
        )
        self.assertIsNotNone(log_format)
        self.assertIsNone(
            re.search(r"\$(request|request_uri)\b", log_format.group("body"))
        )

    def test_proxy_headers_are_overwritten(self):
        config = self.read("deploy/nginx/snippets/gongxing-proxy.conf")
        required = [
            "X-Forwarded-For $remote_addr",
            "X-Real-IP $remote_addr",
            "X-Forwarded-Proto $scheme",
            "X-Forwarded-Host $host",
            'Forwarded ""',
            'Authorization ""',
        ]
        for value in required:
            self.assertIn(value, config)
        self.assertNotIn("$proxy_add_x_forwarded_for", config)

    def test_high_risk_scripts_share_one_lock_and_hold_gate(self):
        for name in ("backup.sh", "deploy-release.sh", "restore-drill.sh"):
            script = self.read(f"deploy/scripts/{name}")
            self.assertIn('source "${SCRIPT_DIR}/common.sh"', script)
            self.assertIn("acquire_ops_lock", script)
            self.assertIn("assert_no_recovery_holds", script)
        common = self.read("deploy/scripts/common.sh")
        self.assertIn("/run/lock/gongxing-ops.lock", common)
        self.assertIn(".recover-*.hold", common)

    def test_health_check_never_restarts_the_service(self):
        script = self.read("deploy/scripts/health-check.sh")
        self.assertIn("ops_lock_is_held", script)
        self.assertNotRegex(script, r"systemctl\s+(?:restart|start)")

    def test_backup_snapshot_requires_checkpoint_and_integrity(self):
        helper = self.read("deploy/scripts/backup_snapshot.py")
        self.assertIn("wal_checkpoint(TRUNCATE)", helper)
        self.assertIn("source.backup(destination)", helper)
        self.assertIn("PRAGMA integrity_check", helper)
        self.assertIn("public_pdf_filename", helper)
        backup = self.read("deploy/scripts/backup.sh")
        self.assertIn("trap cleanup", backup)
        self.assertIn("RESTIC_PRUNE_ENABLED", backup)
        self.assertIn("maintenance mode remains enabled", backup)

    def test_service_is_single_worker_and_loopback_only(self):
        unit = self.read("deploy/systemd/gongxing.service")
        self.assertIn("--host 127.0.0.1", unit)
        self.assertIn("--workers 1", unit)
        self.assertIn("--forwarded-allow-ips 127.0.0.1", unit)

    def test_deploy_validates_new_release_and_can_rollback_first_release(self):
        script = self.read("deploy/scripts/deploy-release.sh")
        self.assertIn("verified restic snapshot ID", script)
        self.assertIn('systemctl start "${GONGXING_SERVICE}"', script)
        self.assertIn("http://127.0.0.1:8000/api/health", script)
        self.assertIn('rm -f -- "${current_link}"', script)
        self.assertIn("maintenance mode remains enabled", script)

    def test_spaces_lifecycle_is_valid_and_bounded(self):
        lifecycle = json.loads(self.read("deploy/spaces/lifecycle.json"))
        rules = {rule["ID"]: rule for rule in lifecycle["Rules"]}
        self.assertEqual(
            rules["expire-noncurrent-versions-after-30-days"][
                "NoncurrentVersionExpiration"
            ]["NoncurrentDays"],
            30,
        )
        self.assertEqual(
            rules["abort-incomplete-multipart-after-1-day"][
                "AbortIncompleteMultipartUpload"
            ]["DaysAfterInitiation"],
            1,
        )
        self.assertTrue(
            rules["remove-expired-delete-markers"]["Expiration"][
                "ExpiredObjectDeleteMarker"
            ]
        )

    def test_ci_has_read_only_permissions_and_no_deployment(self):
        workflow = self.read(".github/workflows/ci.yml")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("pull_request_target", workflow)
        self.assertNotIn("deployments: write", workflow)
        self.assertNotIn("id-token: write", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn('test "$(npm --version)"', workflow)
        self.assertIn(r"(^|/)\.env$", workflow)
        self.assertIn(r"\.pdf$", workflow)
        action_refs = re.findall(r"uses:\s+[^@\s]+@([0-9a-f]+)", workflow)
        self.assertTrue(action_refs)
        self.assertTrue(all(len(reference) == 40 for reference in action_refs))


if __name__ == "__main__":
    unittest.main()
