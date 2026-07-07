"""TLS context for HTTPS from the Decky-bundled Python.

Decky Loader ships its own Python whose ssl module doesn't know SteamOS's
CA bundle location, so default urllib verification fails with
CERTIFICATE_VERIFY_FAILED. Load the system bundle explicitly.
"""

import os
import ssl

_CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",  # SteamOS / Arch
    "/etc/ssl/cert.pem",
    "/etc/pki/tls/certs/ca-bundle.crt",
)


def ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    for path in _CA_BUNDLES:
        if os.path.exists(path):
            try:
                ctx.load_verify_locations(path)
                break
            except ssl.SSLError:
                continue
    return ctx
