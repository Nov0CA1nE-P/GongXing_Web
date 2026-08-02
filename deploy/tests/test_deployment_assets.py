from __future__ import annotations

import os
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DeploymentAssetTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def nginx_server_blocks(self, config: str) -> list[str]:
        blocks: list[str] = []
        for match in re.finditer(r"\bserver\s*\{", config):
            depth = 1
            cursor = match.end()
            while cursor < len(config) and depth:
                if config[cursor] == "{":
                    depth += 1
                elif config[cursor] == "}":
                    depth -= 1
                cursor += 1
            self.assertEqual(depth, 0, "unclosed Nginx server block")
            blocks.append(config[match.start():cursor])
        return blocks

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
        blocks = self.nginx_server_blocks(config)
        self.assertEqual(len(blocks), 2)
        for block in blocks:
            self.assertRegex(block, r"(?m)^\s*access_log\s+off;")

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
            "Strict-Transport-Security",
        ):
            self.assertIn(value, headers)
        self.assertIn('"max-age=86400"', headers)
        lowered_headers = headers.lower()
        self.assertNotIn("includesubdomains", lowered_headers)
        self.assertNotIn("preload", lowered_headers)
        log_format = re.search(
            r"log_format gongxing_safe(?P<body>.*?);",
            config,
            re.DOTALL,
        )
        self.assertIsNotNone(log_format)
        self.assertIsNone(
            re.search(r"\$(request|request_uri)\b", log_format.group("body"))
        )
        blocks = self.nginx_server_blocks(config)
        self.assertEqual(len(blocks), 4)
        application_blocks = [
            block
            for block in blocks
            if "listen 443 ssl http2;" in block
            and "server_name test.novocaine.me;" in block
        ]
        self.assertEqual(len(application_blocks), 1)
        self.assertRegex(
            application_blocks[0],
            r"(?m)^\s*access_log\s+\S+\s+gongxing_safe;",
        )
        for block in blocks:
            if block not in application_blocks:
                self.assertRegex(block, r"(?m)^\s*access_log\s+off;")

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

    def test_deployment_behavior_harnesses(self):
        harnesses = {
            "deploy_release_harness.sh": "deploy release behavior tests: ok",
            "release_package_harness.sh": "release package behavior tests: ok",
            "production_config_harness.sh": "production config behavior tests: ok",
            "certbot_hook_harness.sh": "certbot hook behavior tests: ok",
            "offsite_backup_harness.sh": "offsite backup behavior tests: ok",
        }
        for name, success_marker in harnesses.items():
            with self.subTest(harness=name):
                harness = ROOT / "deploy/tests" / name
                if os.name == "nt":
                    drive = harness.drive.rstrip(":").lower()
                    relative = harness.relative_to(harness.anchor).as_posix()
                    command = ["wsl", "bash", f"/mnt/{drive}/{relative}"]
                else:
                    command = ["bash", str(harness)]
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=90,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
                )
                self.assertIn(success_marker, result.stdout)

    def test_release_install_is_offline_and_pre_switch_validated(self):
        build = self.read("deploy/scripts/build-release.sh")
        deploy = self.read("deploy/scripts/deploy-release.sh")
        self.assertIn("--only-binary=:all:", build)
        self.assertIn("--require-hashes", build)
        self.assertIn("--no-index", deploy)
        self.assertIn("release_integrity.py\" verify", deploy)
        validator = deploy.index("validate-production-config.py")
        switch = deploy.index('mv -- "${temporary_release}" "${release_dir}"')
        self.assertLess(validator, switch)

    def test_production_environment_layout_is_exact(self):
        runbook = self.read("docs/deployment-runbook.md")
        validator = self.read("deploy/scripts/validate-production-config.py")
        harness = self.read("deploy/tests/production_config_harness.sh")
        self.assertIn(
            "install -d -o root -g gongxing -m 0750 /etc/gongxing",
            runbook,
        )
        self.assertIn("install -o root -g gongxing -m 0640", runbook)
        self.assertIn("stat.S_IMODE(metadata.st_mode) != 0o640", validator)
        self.assertIn("stat.S_IMODE(parent_metadata.st_mode) != 0o750", validator)
        self.assertIn('env_dir="${test_root}/etc/gongxing"', harness)
        self.assertIn('chmod 0750 "${env_dir}"', harness)
        self.assertIn('chmod 0640 "${path}"', harness)

    def test_offsite_backup_requires_exact_approval_and_remote_repository(self):
        common = self.read("deploy/scripts/common.sh")
        self.assertIn('"${OFFSITE_BACKUP_APPROVED:-}" != "1"', common)
        parser = self.read("deploy/scripts/validate_restic_repository.py")
        self.assertIn("socket.getaddrinfo", parser)
        self.assertIn("ipv4_mapped", parser)
        self.assertIn("address.is_loopback", parser)
        self.assertFalse((ROOT / "deploy/scripts/configure-spaces.sh").exists())
        self.assertFalse((ROOT / "deploy/spaces/lifecycle.json").exists())

    def test_certbot_hook_validates_before_reload(self):
        hook = self.read("deploy/scripts/certbot-reload-nginx.sh")
        self.assertLess(hook.index("nginx -t"), hook.index("systemctl reload"))
        installer = self.read("docs/deployment-runbook.md")
        self.assertIn("install -o root -g root -m 0755", installer)
        verifier = self.read("deploy/scripts/verify-certbot-hook.py")
        self.assertIn("lstat()", verifier)
        self.assertIn("0o022", verifier)

    def test_release_archive_budgets_are_fixed(self):
        verifier = self.read("deploy/scripts/verify_release_archive.py")
        for value in (
            "MAX_ARCHIVE_BYTES = 64 * MIB",
            "MAX_MEMBER_COUNT = 4096",
            "MAX_MEMBER_DECLARED_BYTES = 32 * MIB",
            "MAX_TOTAL_DECLARED_BYTES = 256 * MIB",
            "MAX_COMPRESSION_RATIO = 40",
            "MAX_ACTUAL_WRITTEN_BYTES = 256 * MIB",
        ):
            self.assertIn(value, verifier)
        self.assertNotIn("extractall", verifier)

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
