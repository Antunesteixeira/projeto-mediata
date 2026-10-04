#!/usr/bin/env python3
"""Check the trusted certificate served for each hostname without HTTP requests."""

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
import socket
import ssl
import sys
from zoneinfo import ZoneInfo


DEFAULT_HOSTS = ("mediatanordeste.com.br", "www.mediatanordeste.com.br")
STATUS_CODES = {"healthy": 0, "warning": 1, "critical": 2}


class UsageError(ValueError):
    """An invalid command line that should produce the same JSON error format."""


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def parse_args(argv=None):
    parser = JSONArgumentParser(description=__doc__)
    parser.add_argument("--host", action="append", help="Hostname to verify; repeat for multiple names.")
    parser.add_argument("--connect", help="Connect to this IP while preserving the hostname and SNI.")
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--expected-certificate", type=Path, help="Compare the served leaf with the first certificate in this PEM file.")
    parser.add_argument("--warning-days", type=float, default=30)
    parser.add_argument("--critical-days", type=float, default=7)
    parser.add_argument("--timeout", type=float, default=10, help="TCP/TLS socket timeout in seconds (default: 10).")
    args = parser.parse_args(argv)
    args.host = [host.strip() for host in args.host] if args.host else list(DEFAULT_HOSTS)
    if any(not host for host in args.host):
        parser.error("--host must not be empty")
    if args.connect is not None:
        try:
            ipaddress.ip_address(args.connect)
        except ValueError:
            parser.error("--connect must be an IPv4 or IPv6 address")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if not all(math.isfinite(value) for value in (args.warning_days, args.critical_days, args.timeout)):
        parser.error("thresholds and timeout must be finite numbers")
    if not 0 <= args.critical_days <= args.warning_days:
        parser.error("thresholds must satisfy 0 <= --critical-days <= --warning-days")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    return args


def expected_fingerprint(path):
    """Hash the first PEM certificate, also accepting a fullchain PEM bundle."""
    pem = Path(path).read_text(encoding="ascii")
    certificate = re.search(
        r"-----BEGIN CERTIFICATE-----\s*.*?\s*-----END CERTIFICATE-----", pem, re.DOTALL
    )
    if certificate is None:
        raise ValueError("Expected PEM file has no CERTIFICATE block")
    der = ssl.PEM_cert_to_DER_cert(certificate.group())
    if not der:
        raise ValueError("Expected PEM certificate has no DER data")
    return hashlib.sha256(der).hexdigest()


def _utc(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _date_from_certificate(value):
    return datetime.fromtimestamp(ssl.cert_time_to_seconds(value), tz=timezone.utc)


def _sao_paulo(value):
    return value.astimezone(ZoneInfo("America/Sao_Paulo")).isoformat()


def check_host(host, connect=None, port=443, expected=None, warning_days=30,
               critical_days=7, timeout=10, now=None):
    """Verify trust/hostname first, then validity and optional leaf identity."""
    result = {
        "host": host,
        "connect_address": connect or host,
        "port": port,
        "status": "critical",
        "exit_code": 2,
        "not_after_utc": None,
        "not_after_sao_paulo": None,
        "days_remaining": None,
        "served_sha256": None,
        "expected_sha256": expected,
        "certificate_matches": None,
    }
    try:
        checked_at = _utc(now or datetime.now(timezone.utc))
        # The default context validates the chain, certificate dates and hostname.
        # The connect address changes routing only; host remains the verified SNI.
        context = ssl.create_default_context()
        with socket.create_connection((connect or host, port), timeout=timeout) as connection:
            with context.wrap_socket(connection, server_hostname=host) as tls:
                certificate = tls.getpeercert()
                der = tls.getpeercert(binary_form=True)
                if not der or not certificate:
                    raise ValueError("Server did not provide a verified certificate")
                result["served_sha256"] = hashlib.sha256(der).hexdigest()
                result["certificate_matches"] = (
                    result["served_sha256"] == expected if expected is not None else None
                )
                if "notAfter" not in certificate:
                    raise ValueError("Verified certificate has no expiration date")
                not_after = _date_from_certificate(certificate["notAfter"])
                result["not_after_utc"] = not_after.isoformat()
                result["not_after_sao_paulo"] = _sao_paulo(not_after)
                result["days_remaining"] = (not_after - checked_at).total_seconds() / 86400
                if "notBefore" in certificate:
                    not_before = _date_from_certificate(certificate["notBefore"])
                    result["not_before_utc"] = not_before.isoformat()
                    if checked_at < not_before:
                        raise ValueError("Certificate is not yet valid")
                if not_after <= checked_at:
                    raise ValueError("Certificate has expired")
                if result["certificate_matches"] is False:
                    raise ValueError("Served certificate SHA256 does not match the expected PEM leaf")

                days = result["days_remaining"]
                status = "critical" if days < critical_days else "warning" if days < warning_days else "healthy"
                result["status"] = status
                result["exit_code"] = STATUS_CODES[status]
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        if isinstance(error, ssl.SSLCertVerificationError):
            result["verification_error_code"] = getattr(error, "verify_code", None)
    return result


def main(argv=None):
    try:
        args = parse_args(argv)
        checked_at = datetime.now(timezone.utc)
        expected = expected_fingerprint(args.expected_certificate) if args.expected_certificate else None
        results = [
            check_host(host, connect=args.connect, port=args.port, expected=expected,
                       warning_days=args.warning_days, critical_days=args.critical_days,
                       timeout=args.timeout, now=checked_at)
            for host in args.host
        ]
        code = max(result["exit_code"] for result in results)
        report = {
            "checked_at_utc": checked_at.isoformat(),
            "checked_at_sao_paulo": _sao_paulo(checked_at),
            "warning_days": args.warning_days,
            "critical_days": args.critical_days,
            "overall_status": next(status for status, value in STATUS_CODES.items() if value == code),
            "exit_code": code,
            "hosts": results,
        }
    except Exception as error:
        code = 2
        report = {
            "overall_status": "critical",
            "exit_code": code,
            "hosts": [],
            "error": f"{type(error).__name__}: {error}",
        }
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
