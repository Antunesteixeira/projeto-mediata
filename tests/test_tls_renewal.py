"""Exercise the real renewal shell with isolated, offline command doubles."""

import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "renew-tls.sh"
STAGING_URL = "https://acme-staging-v02.api.letsencrypt.org/directory"


class TLSRenewalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mediata-tls-renewal-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.bin_directory = self.directory / "bin"
        self.bin_directory.mkdir()
        self.project = self.directory / "project"
        self.certificate = self.project / "certbot/conf/live/test-certificate/fullchain.pem"
        self.certificate.parent.mkdir(parents=True)
        self.certificate.write_text("offline certificate fixture\n", encoding="ascii")
        self.renewal_config = self.project / "certbot/conf/renewal/test-certificate.conf"
        self.renewal_config.parent.mkdir(parents=True)
        self.renewal_config.write_text("[renewalparams]\nauthenticator = webroot\n", encoding="ascii")
        self.check_script = self.directory / "check-tls.py"
        self.check_script.write_text("# The PATH python3 double handles this file.\n", encoding="ascii")
        self.call_log = self.directory / "commands.log"
        self.call_log.write_text("", encoding="ascii")
        self.check_count = self.directory / "check-count"
        self.check_count.write_text("0\n", encoding="ascii")
        self.lock_file = self.directory / "renew.lock"
        self.env_file = self.directory / "tls.env"
        configuration = {
            "TLS_PROJECT_DIR": str(self.project),
            "TLS_CERT_NAME": "test-certificate",
            "TLS_CERTBOT_CONTAINER": "certbot_test",
            "TLS_NGINX_CONTAINER": "nginx_test",
            "TLS_DOMAINS": "mediatanordeste.com.br www.mediatanordeste.com.br",
            "TLS_CHECK_SCRIPT": str(self.check_script),
            "TLS_LOCK_FILE": str(self.lock_file),
        }
        self.env_file.write_text(
            "".join(f"{key}={shlex.quote(value)}\n" for key, value in configuration.items()),
            encoding="ascii",
        )
        self.environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("TLS_", "MOCK_"))
        }
        self.environment.update({
            "PATH": str(self.bin_directory) + os.pathsep + os.defpath,
            "TLS_ENV_FILE": str(self.env_file),
            "TLS_PROJECT_DIR": str(self.project),
            "MOCK_CALL_LOG": str(self.call_log),
            "MOCK_CHECK_COUNT": str(self.check_count),
            "MOCK_CHECK_STATUSES": "0",
            "MOCK_NGINX_TEST_EXIT": "0",
            "MOCK_CERTBOT_EXIT": "0",
            "MOCK_WEBROOT_GOOD": "1",
        })
        self.install_command_doubles()

    def write_command(self, name, body):
        # /bin/sh avoids the mocked python3 and any dependency on the host PATH.
        common = """#!/bin/sh
set -eu
printf '%s' "${0##*/}" >> "$MOCK_CALL_LOG"
for argument in "$@"; do
    printf '\\t%s' "$argument" >> "$MOCK_CALL_LOG"
done
printf '\\n' >> "$MOCK_CALL_LOG"
"""
        path = self.bin_directory / name
        path.write_text(common + body, encoding="ascii")
        path.chmod(0o755)

    def install_command_doubles(self):
        self.write_command("docker", """
if [ "$1" = inspect ]; then
    printf 'true\\n'
    exit 0
fi
if [ "$1" = exec ] && [ "$3" = certbot ]; then
    exit "$MOCK_CERTBOT_EXIT"
fi
if [ "$1" = exec ] && [ "$3" = nginx ]; then
    if [ "$4" = -t ]; then
        exit "$MOCK_NGINX_TEST_EXIT"
    fi
    if [ "$4" = -s ] && [ "$5" = reload ]; then
        exit 0
    fi
fi
printf 'Unexpected docker invocation\\n' >&2
exit 97
""")
        self.write_command("curl", """
for argument in "$@"; do
    url=$argument
done
if [ "$MOCK_WEBROOT_GOOD" = 1 ]; then
    printf '%s' "${url##*/}"
else
    printf 'incorrect-webroot-response'
fi
""")
        self.write_command("python3", """
count=$(cat "$MOCK_CHECK_COUNT")
count=$((count + 1))
printf '%s\\n' "$count" > "$MOCK_CHECK_COUNT"
index=0
code=0
for candidate in $MOCK_CHECK_STATUSES; do
    index=$((index + 1))
    if [ "$index" -gt "$count" ]; then
        break
    fi
    code=$candidate
done
case "$code" in
    0) status=healthy ;;
    1) status=warning ;;
    2) status=critical ;;
    *) printf 'Unsupported mock status\\n' >&2; exit 97 ;;
esac
printf '{"overall_status":"%s","exit_code":%s,"hosts":[]}\\n' "$status" "$code"
exit "$code"
""")
        self.write_command("sleep", "exit 0\n")
        self.write_command("flock", "exit 0\n")

    def run_renewal(self, *arguments, **environment):
        task_environment = self.environment.copy()
        task_environment.update(environment)
        return subprocess.run(
            ["/bin/bash", str(SCRIPT_PATH), *arguments],
            cwd=self.directory,
            env=task_environment,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def calls(self, command=None):
        calls = [line.split("\t") for line in self.call_log.read_text(encoding="ascii").splitlines()]
        return calls if command is None else [call for call in calls if call[0] == command]

    def certbot_calls(self):
        return [call for call in self.calls("docker") if len(call) > 3 and call[3] == "certbot"]

    def reload_calls(self):
        return [call for call in self.calls("docker") if call[3:] == ["nginx", "-s", "reload"]]

    def assert_succeeded(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_failed(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_invalid_nginx_preflight_prevents_certbot_and_reload(self):
        result = self.run_renewal(MOCK_NGINX_TEST_EXIT="1")
        self.assert_failed(result)
        self.assertFalse(self.certbot_calls())
        self.assertFalse(self.reload_calls())
        self.assertFalse(self.calls("curl"))
        self.assertFalse(self.calls("python3"))

    def test_incorrect_webroot_prevents_certbot_and_reload(self):
        result = self.run_renewal(MOCK_WEBROOT_GOOD="0")
        self.assert_failed(result)
        self.assertFalse(self.certbot_calls())
        self.assertFalse(self.reload_calls())
        self.assertEqual(len(self.calls("curl")), 1)
        self.assertFalse(self.calls("python3"))
        challenge_directory = self.project / "certbot/www/.well-known/acme-challenge"
        self.assertEqual(list(challenge_directory.iterdir()), [])

    def test_certbot_failure_remains_an_error_when_served_certificate_is_healthy(self):
        result = self.run_renewal(MOCK_CERTBOT_EXIT="3", MOCK_CHECK_STATUSES="0")
        self.assert_failed(result)
        self.assertEqual(len(self.certbot_calls()), 1)
        self.assertEqual(len(self.reload_calls()), 1)
        self.assertEqual(len(self.calls("python3")), 1)
        self.assertIn('"overall_status":"healthy"', result.stdout)
        self.assertNotIn("SUCCESS:", result.stdout)

    def test_reload_polls_until_the_updated_certificate_is_served(self):
        result = self.run_renewal(MOCK_CHECK_STATUSES="2 0")
        self.assert_succeeded(result)
        self.assertEqual(len(self.reload_calls()), 1)
        self.assertEqual(len(self.calls("python3")), 2)
        self.assertEqual(self.check_count.read_text(encoding="ascii").strip(), "2")
        self.assertEqual(self.calls("sleep"), [["sleep", "2"]])
        commands = self.calls()
        self.assertLess(commands.index(self.reload_calls()[0]), commands.index(self.calls("python3")[0]))
        self.assertIn("SUCCESS:", result.stdout)

    def test_permanent_certificate_mismatch_fails_after_twelve_checks(self):
        result = self.run_renewal(MOCK_CHECK_STATUSES="2")
        self.assert_failed(result)
        self.assertEqual(len(self.calls("python3")), 12)
        self.assertEqual(self.check_count.read_text(encoding="ascii").strip(), "12")
        self.assertEqual(self.calls("sleep"), [["sleep", "2"]] * 11)
        self.assertNotIn("SUCCESS:", result.stdout)

    def test_dry_run_uses_staging_without_forcing_renewal(self):
        result = self.run_renewal("--dry-run")
        self.assert_succeeded(result)
        self.assertEqual(len(self.certbot_calls()), 1)
        arguments = self.certbot_calls()[0]
        self.assertIn("renew", arguments)
        self.assertIn("--dry-run", arguments)
        self.assertIn("--server", arguments)
        self.assertEqual(arguments[arguments.index("--server") + 1], STAGING_URL)
        self.assertNotIn("--force-renewal", arguments)

    def test_check_mode_only_checks_tls_without_mutating_project_or_reloading(self):
        files_before = {
            path.relative_to(self.project): path.read_bytes()
            for path in self.project.rglob("*") if path.is_file()
        }
        result = self.run_renewal("--check")
        self.assert_succeeded(result)
        self.assertEqual(len(self.calls("python3")), 1)
        self.assertFalse(self.calls("docker"))
        self.assertFalse(self.calls("curl"))
        self.assertFalse(self.calls("flock"))
        self.assertFalse(self.calls("sleep"))
        self.assertFalse(self.lock_file.exists())
        files_after = {
            path.relative_to(self.project): path.read_bytes()
            for path in self.project.rglob("*") if path.is_file()
        }
        self.assertEqual(files_after, files_before)
        self.assertFalse((self.project / "certbot/www").exists())

    def test_healthy_renewal_returns_success_and_checks_the_expected_leaf(self):
        result = self.run_renewal()
        self.assert_succeeded(result)
        self.assertEqual(len(self.certbot_calls()), 1)
        self.assertEqual(len(self.reload_calls()), 1)
        self.assertEqual(len(self.calls("python3")), 1)
        self.assertEqual(len(self.calls("flock")), 1)
        self.assertFalse(self.calls("sleep"))
        self.assertNotIn("--force-renewal", self.certbot_calls()[0])
        self.assertNotIn("--dry-run", self.certbot_calls()[0])
        check = self.calls("python3")[0]
        self.assertEqual(check[1], str(self.check_script))
        self.assertEqual(check[check.index("--expected-certificate") + 1], str(self.certificate))
        self.assertEqual(check[check.index("--connect") + 1], "127.0.0.1")
        hosts = [check[index + 1] for index, argument in enumerate(check) if argument == "--host"]
        self.assertEqual(hosts, ["mediatanordeste.com.br", "www.mediatanordeste.com.br"])
        self.assertIn("SUCCESS:", result.stdout)

    def test_check_propagates_each_status_while_renewal_accepts_warning(self):
        for status in (0, 1, 2):
            with self.subTest(mode="--check", status=status):
                self.call_log.write_text("", encoding="ascii")
                self.check_count.write_text("0\n", encoding="ascii")
                result = self.run_renewal("--check", MOCK_CHECK_STATUSES=str(status))
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                self.assertEqual(len(self.calls("python3")), 1)
                self.assertFalse(self.calls("docker"))
                self.assertFalse(self.calls("flock"))
        self.call_log.write_text("", encoding="ascii")
        self.check_count.write_text("0\n", encoding="ascii")
        result = self.run_renewal(MOCK_CHECK_STATUSES="1")
        self.assert_succeeded(result)
        self.assertEqual(len(self.calls("python3")), 1)
        self.assertFalse(self.calls("sleep"))
        self.assertIn("WARNING:", result.stdout)
        self.assertIn("SUCCESS:", result.stdout)


if __name__ == "__main__":
    unittest.main()
