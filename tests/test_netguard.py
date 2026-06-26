"""SSRF guard — the webhook trigger must refuse internal/metadata targets.

All cases use literal IPs or names that resolve locally, so the tests need no
network: getaddrinfo on a literal IP just parses it.
"""

import pytest

from vigil.netguard import assert_public_url, UnsafeURLError


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata (link-local)
    "http://127.0.0.1:8000/internal",            # loopback
    "http://localhost/admin",                    # loopback via name
    "http://10.0.0.5/",                          # RFC1918
    "http://192.168.1.1/",                       # RFC1918
    "http://172.16.0.1/",                        # RFC1918
    "http://[::1]/",                             # IPv6 loopback
    "http://0.0.0.0/",                           # unspecified
    "https://[::ffff:127.0.0.1]/",              # IPv4-mapped loopback
    "ftp://example.com/",                        # disallowed scheme
    "file:///etc/passwd",                        # disallowed scheme
    "",                                          # empty
])
def test_rejects_internal_and_bad_schemes(url):
    with pytest.raises(UnsafeURLError):
        assert_public_url(url)


@pytest.mark.parametrize("url", [
    "http://93.184.216.34/",   # literal public IP
    "https://8.8.8.8/",
    "https://1.1.1.1/hook",
])
def test_allows_public(url):
    assert_public_url(url)  # must not raise
