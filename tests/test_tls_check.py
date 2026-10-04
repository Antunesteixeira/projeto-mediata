"""Regression tests for the TLS monitor, without network connections."""

import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import socket
import ssl
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check-tls.py"
NOW = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)
HOST = "mediatanordeste.com.br"
# Fingerprinting uses DER bytes; certificate parsing and trust are provided by
# Python's SSL context and are mocked separately in the connection tests.
LEAF_DER = b"\x30\x03\x02\x01\x01"
CHAIN_DER = b"\x30\x03\x02\x01\x02"


def pem_certificate(der):
    encoded = base64.b64encode(der).decode("ascii")
    return "-----BEGIN CERTIFICATE-----\n" + encoded + "\n-----END CERTIFICATE-----\n"


def certificate_time(value):
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return (
        f"{months[value.month - 1]} {value.day:2d} "
        f"{value.hour:02d}:{value.minute:02d}:{value.second:02d} {value.year} GMT"
    )


class TLSCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("mediata_tls_check_tests_module", SCRIPT_PATH)
        cls.tls = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.tls
        spec.loader.exec_module(cls.tls)

    @contextlib.contextmanager
    def connection(self, *, expires=None, begins=None, der=LEAF_DER, connection_error=None, tls_error=None):
        expires = expires if expires is not None else NOW + timedelta(days=90)
        begins = begins if begins is not None else NOW - timedelta(days=30)
        raw_connection = MagicMock(name="raw_connection")
        raw_connection.__enter__.return_value = raw_connection
        peer = MagicMock(name="tls_peer")
        peer.__enter__.return_value = peer
        peer.getpeercert.side_effect = lambda binary_form=False: der if binary_form else {
            "notAfter": certificate_time(expires),
            "notBefore": certificate_time(begins),
        }
        context = MagicMock(name="trusted_ssl_context")
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.wrap_socket.return_value = peer
        if tls_error is not None:
            context.wrap_socket.side_effect = tls_error
        with (
            patch.object(self.tls.socket, "create_connection", autospec=True, return_value=raw_connection) as connect,
            patch.object(self.tls.ssl, "create_default_context", return_value=context) as create_context,
        ):
            if connection_error is not None:
                connect.side_effect = connection_error
            yield raw_connection, peer, context, connect, create_context

    def host_result(self, host=HOST, status="healthy", **kwargs):
        exit_code = {"healthy": 0, "warning": 1, "critical": 2}[status]
        return {
            "host": host,
            "connect_address": kwargs.get("connect") or host,
            "port": kwargs.get("port", 443),
            "status": status,
            "exit_code": exit_code,
            "not_after_utc": (NOW + timedelta(days=90)).isoformat(),
            "not_after_sao_paulo": (NOW + timedelta(days=90)).astimezone(
                timezone(timedelta(hours=-3))
            ).isoformat(),
            "days_remaining": 90,
            "served_sha256": hashlib.sha256(LEAF_DER).hexdigest(),
            "expected_sha256": kwargs.get("expected"),
        }

    def run_main(self, arguments, *, statuses=None):
        output = io.StringIO()
        statuses = iter(statuses or [])

        def result(host, **kwargs):
            return self.host_result(host, next(statuses, "healthy"), **kwargs)

        with patch.object(self.tls, "check_host", side_effect=result) as check:
            with contextlib.redirect_stdout(output):
                exit_code = self.tls.main(arguments)
        return exit_code, json.loads(output.getvalue()), check

    def test_expected_fingerprint_reads_leaf_from_a_certificate_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fullchain.pem"
            path.write_text(
                "Certificate chain\n" + pem_certificate(LEAF_DER) + "\n" + pem_certificate(CHAIN_DER),
                encoding="ascii",
            )
            fingerprint = self.tls.expected_fingerprint(path)
        self.assertEqual(fingerprint, hashlib.sha256(LEAF_DER).hexdigest())
        self.assertNotEqual(fingerprint, hashlib.sha256(CHAIN_DER).hexdigest())
        self.assertEqual(fingerprint, fingerprint.lower())

    def test_expected_fingerprint_rejects_a_file_without_a_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.pem"
            path.write_text("This file contains no PEM certificate.\n", encoding="ascii")
            with self.assertRaises((ValueError, ssl.SSLError)):
                self.tls.expected_fingerprint(path)

    def test_healthy_certificate_reports_fingerprint_and_both_timezones(self):
        expires = NOW + timedelta(days=90)
        with self.connection(expires=expires) as (_, peer, _, _, _):
            result = self.tls.check_host(HOST, now=NOW)
        self.assertEqual(result["host"], HOST)
        self.assertEqual(result["connect_address"], HOST)
        self.assertEqual(result["port"], 443)
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["days_remaining"], 90)
        self.assertEqual(result["not_after_utc"], expires.isoformat())
        self.assertEqual(
            result["not_after_sao_paulo"],
            expires.astimezone(timezone(timedelta(hours=-3))).isoformat(),
        )
        self.assertEqual(result["served_sha256"], hashlib.sha256(LEAF_DER).hexdigest())
        self.assertIsNone(result["expected_sha256"])
        self.assertFalse(result.get("error"))
        self.assertTrue(any(call.kwargs.get("binary_form") is True for call in peer.getpeercert.call_args_list))
        peer.__exit__.assert_called_once()

    def test_connect_address_preserves_hostname_verification_and_default_trust(self):
        with self.connection() as (connection, _, context, connect, create_context):
            result = self.tls.check_host(HOST, connect="192.0.2.10", port=8443, timeout=4, now=NOW)
        create_context.assert_called_once_with()
        connect.assert_called_once_with(("192.0.2.10", 8443), 4)
        context.wrap_socket.assert_called_once_with(connection, server_hostname=HOST)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(result["host"], HOST)
        self.assertEqual(result["connect_address"], "192.0.2.10")
        self.assertEqual(result["port"], 8443)
        connection.__exit__.assert_called_once()

    def test_default_connection_uses_the_host_and_default_timeout(self):
        with self.connection() as (_, _, _, connect, _):
            self.tls.check_host(HOST, now=NOW)
        connect.assert_called_once_with((HOST, 443), 10)

    def test_expiration_thresholds_are_strict_and_expiry_is_critical(self):
        cases = (
            (31, "healthy", 0),
            (30, "healthy", 0),
            (29, "warning", 1),
            (7, "warning", 1),
            (6, "critical", 2),
            (1, "critical", 2),
            (0, "critical", 2),
            (-1, "critical", 2),
        )
        for days, status, exit_code in cases:
            with self.subTest(days=days), self.connection(expires=NOW + timedelta(days=days)):
                result = self.tls.check_host(HOST, now=NOW)
            self.assertEqual(result["days_remaining"], days)
            self.assertEqual(result["status"], status)
            self.assertEqual(result["exit_code"], exit_code)

    def test_custom_expiration_thresholds_are_applied(self):
        for days, status in ((45, "healthy"), (44, "warning"), (10, "warning"), (9, "critical")):
            with self.subTest(days=days), self.connection(expires=NOW + timedelta(days=days)):
                result = self.tls.check_host(HOST, warning_days=45, critical_days=10, now=NOW)
            self.assertEqual(result["status"], status)

    def test_expired_certificate_is_critical_even_when_the_fingerprint_matches(self):
        expected = hashlib.sha256(LEAF_DER).hexdigest()
        with self.connection(expires=NOW - timedelta(days=1)):
            result = self.tls.check_host(HOST, expected=expected, now=NOW)
        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["exit_code"], 2)
        self.assertTrue(result["certificate_matches"])

    def test_certificate_not_yet_valid_is_critical(self):
        with self.connection(begins=NOW + timedelta(seconds=1)):
            result = self.tls.check_host(HOST, now=NOW)
        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["exit_code"], 2)
        self.assertTrue(result.get("error"))

    def test_certificate_becoming_valid_now_is_healthy(self):
        with self.connection(begins=NOW):
            result = self.tls.check_host(HOST, now=NOW)
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["exit_code"], 0)

    def test_matching_expected_certificate_is_healthy(self):
        expected = hashlib.sha256(LEAF_DER).hexdigest()
        with self.connection():
            result = self.tls.check_host(HOST, expected=expected, now=NOW)
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["expected_sha256"], expected)
        self.assertTrue(result["certificate_matches"])

    def test_served_certificate_mismatch_is_critical(self):
        expected = hashlib.sha256(CHAIN_DER).hexdigest()
        with self.connection():
            result = self.tls.check_host(HOST, expected=expected, now=NOW)
        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["expected_sha256"], expected)
        self.assertEqual(result["served_sha256"], hashlib.sha256(LEAF_DER).hexdigest())
        self.assertFalse(result["certificate_matches"])

    def test_hostname_verification_error_becomes_a_critical_result(self):
        error = ssl.SSLCertVerificationError(1, "certificate verify failed: Hostname mismatch")
        with self.connection(tls_error=error) as (connection, peer, _, _, _):
            result = self.tls.check_host(HOST, connect="192.0.2.10", now=NOW)
        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["exit_code"], 2)
        self.assertTrue(result.get("error"))
        self.assertIn("Hostname mismatch", result["error"])
        peer.getpeercert.assert_not_called()
        connection.__exit__.assert_called_once()

    def test_untrusted_certificate_chain_becomes_a_critical_result(self):
        error = ssl.SSLCertVerificationError(1, "certificate verify failed: unable to get local issuer certificate")
        error.verify_code = 20
        with self.connection(tls_error=error) as (connection, peer, context, _, create_context):
            result = self.tls.check_host(HOST, now=NOW)
        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["exit_code"], 2)
        self.assertTrue(result.get("error"))
        create_context.assert_called_once_with()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        peer.getpeercert.assert_not_called()
        connection.__exit__.assert_called_once()

    def test_connection_failures_become_critical_results(self):
        for error in (TimeoutError("TLS connection timed out"), socket.gaierror("Host not found")):
            with self.subTest(error=type(error).__name__), self.connection(connection_error=error):
                result = self.tls.check_host(HOST, now=NOW)
            self.assertEqual(result["status"], "critical")
            self.assertEqual(result["exit_code"], 2)
            self.assertTrue(result.get("error"))

    def test_malformed_certificate_dates_become_a_critical_result(self):
        with self.connection() as (_, peer, _, _, _):
            peer.getpeercert.side_effect = lambda binary_form=False: LEAF_DER if binary_form else {
                "notAfter": "invalid certificate date",
                "notBefore": certificate_time(NOW - timedelta(days=1)),
            }
            result = self.tls.check_host(HOST, now=NOW)
        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["exit_code"], 2)
        self.assertTrue(result.get("error"))

    def test_cli_defaults_check_both_production_domains(self):
        exit_code, result, check = self.run_main([])
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["overall_status"], "healthy")
        self.assertEqual([host["host"] for host in result["hosts"]], [HOST, "www." + HOST])
        self.assertEqual(check.call_count, 2)

    def test_cli_repeated_hosts_and_connection_options_are_forwarded(self):
        exit_code, result, check = self.run_main([
            "--host", "first.example.com", "--host", "second.example.com",
            "--connect", "192.0.2.10", "--port", "8443", "--timeout", "4",
            "--warning-days", "45", "--critical-days", "10",
        ])
        self.assertEqual(exit_code, 0)
        self.assertEqual([host["host"] for host in result["hosts"]], ["first.example.com", "second.example.com"])
        self.assertEqual(check.call_count, 2)
        for call in check.call_args_list:
            self.assertEqual(call.kwargs["connect"], "192.0.2.10")
            self.assertEqual(call.kwargs["port"], 8443)
            self.assertEqual(call.kwargs["timeout"], 4)
            self.assertEqual(call.kwargs["warning_days"], 45)
            self.assertEqual(call.kwargs["critical_days"], 10)

    def test_cli_aggregates_the_highest_severity(self):
        cases = (
            (["healthy", "healthy"], "healthy", 0),
            (["healthy", "warning"], "warning", 1),
            (["warning", "critical"], "critical", 2),
        )
        for statuses, expected_status, expected_exit in cases:
            with self.subTest(statuses=statuses):
                exit_code, result, _ = self.run_main([], statuses=statuses)
            self.assertEqual(exit_code, expected_exit)
            self.assertEqual(result["exit_code"], expected_exit)
            self.assertEqual(result["overall_status"], expected_status)
            self.assertEqual([host["status"] for host in result["hosts"]], statuses)

    def test_cli_outputs_consistent_utc_and_sao_paulo_check_times(self):
        _, result, _ = self.run_main([])
        utc = datetime.fromisoformat(result["checked_at_utc"])
        local = datetime.fromisoformat(result["checked_at_sao_paulo"])
        self.assertEqual(utc.utcoffset(), timedelta(0))
        self.assertEqual(local.utcoffset(), timedelta(hours=-3))
        self.assertEqual(utc, local)

    def test_cli_passes_the_expected_leaf_fingerprint_to_every_host(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fullchain.pem"
            path.write_text(pem_certificate(LEAF_DER) + pem_certificate(CHAIN_DER), encoding="ascii")
            exit_code, _, check = self.run_main(["--expected-certificate", str(path)])
        self.assertEqual(exit_code, 0)
        self.assertEqual(check.call_count, 2)
        for call in check.call_args_list:
            self.assertEqual(call.kwargs["expected"], hashlib.sha256(LEAF_DER).hexdigest())

    def test_cli_invalid_expected_certificate_fails_before_any_network_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "does-not-exist.pem"
            malformed = Path(directory) / "invalid.pem"
            malformed.write_text("No PEM certificate in this file.\n", encoding="ascii")
            for path in (missing, malformed):
                with self.subTest(path=path.name):
                    output = io.StringIO()
                    with (
                        patch.object(self.tls, "check_host") as check,
                        patch.object(self.tls.socket, "create_connection") as connect,
                        contextlib.redirect_stdout(output),
                    ):
                        exit_code = self.tls.main(["--expected-certificate", str(path)])
                    result = json.loads(output.getvalue())
                    self.assertEqual(exit_code, 2)
                    self.assertEqual(result["exit_code"], 2)
                    self.assertEqual(result["overall_status"], "critical")
                    self.assertTrue(result.get("error"))
                    check.assert_not_called()
                    connect.assert_not_called()

    def test_cli_invalid_input_reports_json_without_network_access(self):
        cases = (
            ["--host", " "],
            ["--connect", "not-an-ip"],
            ["--port", "0"],
            ["--port", "65536"],
            ["--timeout", "0"],
            ["--timeout", "nan"],
            ["--warning-days", "inf"],
            ["--warning-days", "5", "--critical-days", "7"],
            ["--critical-days", "-1"],
            ["--unexpected-option"],
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                output = io.StringIO()
                with (
                    patch.object(self.tls, "check_host") as check,
                    patch.object(self.tls.socket, "create_connection") as connect,
                    contextlib.redirect_stdout(output),
                ):
                    exit_code = self.tls.main(arguments)
                result = json.loads(output.getvalue())
                self.assertEqual(exit_code, 2)
                self.assertEqual(result["exit_code"], 2)
                self.assertEqual(result["overall_status"], "critical")
                self.assertTrue(result.get("error"))
                check.assert_not_called()
                connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
