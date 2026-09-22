"""
network_fix.py
Render's outbound network does not support IPv6 (a known platform
limitation as of 2026), and some public APIs this app calls (notably
Overpass, and occasionally Census) resolve their hostname to an IPv6
address first. That produces 'OSError: [Errno 101] Network is
unreachable' even though the API itself is up and reachable over IPv4.

Importing this module patches urllib3 (which requests uses under the
hood) to only attempt IPv4 connections for the lifetime of the process.
Import it before making any requests calls — geocode.py and
data_pipeline.py both import it at the top for this reason.
"""

import socket
import urllib3.util.connection as _urllib3_cn


def _allowed_gai_family():
    return socket.AF_INET


_urllib3_cn.allowed_gai_family = _allowed_gai_family
