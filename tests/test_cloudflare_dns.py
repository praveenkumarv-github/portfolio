import unittest

from scripts.cloudflare_dns import CloudflareAPIError, upsert_dns_record


class CloudflareDNSTests(unittest.TestCase):
    def test_upsert_creates_normalized_unproxied_record(self):
        calls = []

        def request(method, path, token, payload):
            calls.append((method, path, token, payload))
            return [] if method == "GET" else {"id": "new-record"}

        action = upsert_dns_record(
            zone_id="zone-id",
            token="token",
            record_type="CNAME",
            name="_validation.example.com.",
            content="target.acm-validations.aws.",
            proxied=False,
            request_function=request,
        )

        self.assertEqual(action, "created")
        self.assertEqual(calls[-1][0], "POST")
        self.assertEqual(
            calls[-1][3],
            {
                "type": "CNAME",
                "name": "_validation.example.com",
                "content": "target.acm-validations.aws",
                "ttl": 1,
                "proxied": False,
            },
        )

    def test_upsert_updates_existing_proxied_record(self):
        calls = []

        def request(method, path, token, payload):
            calls.append((method, path, token, payload))
            return [{"id": "existing-record"}] if method == "GET" else {"id": "existing-record"}

        action = upsert_dns_record(
            zone_id="zone-id",
            token="token",
            record_type="CNAME",
            name="finance.example.com",
            content="gateway.execute-api.example.com",
            proxied=True,
            request_function=request,
        )

        self.assertEqual(action, "updated")
        self.assertEqual(calls[-1][0], "PUT")
        self.assertTrue(calls[-1][1].endswith("/dns_records/existing-record"))
        self.assertIs(calls[-1][3]["proxied"], True)

    def test_upsert_propagates_safe_cloudflare_error(self):
        def request(method, path, token, payload):
            raise CloudflareAPIError("Cloudflare API returned HTTP 403")

        with self.assertRaisesRegex(CloudflareAPIError, "HTTP 403"):
            upsert_dns_record(
                zone_id="zone-id",
                token="secret-token",
                record_type="CNAME",
                name="finance.example.com",
                content="gateway.example.com",
                proxied=True,
                request_function=request,
            )