import copy
from pathlib import Path
import sys
import unittest

import yaml
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate import ROOT, schemas, validate_api, validator

BASE = "https://nddev.ai/schemas/nddev-device-sync/"


class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents, cls.registry = schemas()
        cls.v2 = cls.documents[BASE + "v2/control-plane.schema.json"]

    def valid(self, definition, value):
        return validator(self.v2, self.registry, definition).is_valid(value)

    def operation(self):
        return {"schema_version": 2, "operation_id": "operation-1", "device_id": "device-1",
                "entity_type": "module_state", "entity_id": "module-1", "base_revision": 0,
                "idempotency_key": "operation-1", "payload": {"algorithm":"aes-256-gcm", "key_id":"key-1", "nonce":"A"*16, "ciphertext":"A"*22}}

    def test_operation_requires_version_and_rejects_unknown_or_unowned_fields(self):
        original = self.operation()
        self.assertTrue(self.valid("SyncOperation", original))
        for field in original:
            altered = original.copy()
            del altered[field]
            self.assertFalse(self.valid("SyncOperation", altered), field)
        for field, value in [("schema_version", 1), ("schema_version", 3),
                             ("tenant_id", "tenant-1"), ("user_id", "user-1")]:
            self.assertFalse(self.valid("SyncOperation", original | {field: value}), field)

    def test_identifier_grammar_and_lengths(self):
        for value in ["a", "Aa09-_.:", "x" * 128]:
            self.assertTrue(self.valid("Identifier", value))
        for value in ["", " ", "a/b", "a b", "é", "a\n", "x" * 129]:
            self.assertFalse(self.valid("Identifier", value))
        self.assertTrue(self.valid("LongIdentifier", "x" * 256))
        self.assertFalse(self.valid("LongIdentifier", "x" * 257))

    def test_wire_counters_preserve_exact_integer_bounds(self):
        for value in [0, 1, 9007199254740991]:
            self.assertTrue(self.valid("Revision", value))
        for value in [-1, 9007199254740992, 1.5, True, "1"]:
            self.assertFalse(self.valid("Revision", value))

    def test_auth_fields_reject_empty_invalid_and_secret_leaking_extras(self):
        email = {"email": "owner@example.invalid"}
        self.assertTrue(self.valid("EmailChallengeRequest", email))
        for value in ["", "not-an-address", "x" * 255 + "@example.invalid"]:
            self.assertFalse(self.valid("EmailChallengeRequest", {"email": value}))
        proof = {"challenge_id": "challenge-1", "code": "12345678"}
        self.assertTrue(self.valid("EmailVerifyRequest", proof))
        for code in ["1234567", "123456789", "abcdefgh", "1234 678", 12345678]:
            self.assertFalse(self.valid("EmailVerifyRequest", proof | {"code": code}))
        response = {"challenge_id": "challenge-1", "expires_in_seconds": 300,
                    "resend_after_seconds": 30}
        self.assertTrue(self.valid("EmailChallenge", response))
        self.assertFalse(self.valid("EmailChallenge", response | {"account_exists": True}))
        self.assertFalse(self.valid("EmailChallenge", response | {"code": "12345678"}))

    def test_shared_session_has_bounded_token_and_real_timestamp_validation(self):
        session = {"user_id": "user-1", "tenant_id": "tenant-1", "auth_method": "email_otp",
                   "expires_at": "2026-01-01T00:00:00Z"}
        for method in ["email_otp", "github"]:
            self.assertTrue(self.valid("SessionIssued", {"session": session | {"auth_method": method},
                                                        "session_token": "A" * 43}))
        self.assertFalse(self.valid("Session", session | {"auth_method": "password"}))
        self.assertFalse(self.valid("Session", session | {"expires_at": "not-a-date"}))
        for token in ["", "A" * 129, "A" * 42 + "="]:
            self.assertFalse(self.valid("SessionIssued", {"session": session, "session_token": token}))
        start = {"flow_id": "flow-1", "authorization_url": "https://github.com/login/oauth/authorize",
                 "exchange_token": "A" * 43, "expires_in_seconds": 300, "poll_after_seconds": 2, "verification_code": "12345678"}
        self.assertTrue(self.valid("GithubStart", start))
        self.assertFalse(self.valid("GithubStart", start | {"authorization_url": "not a URI"}))
        approval = {"flow_id": "flow-1", "csrf_token": "A" * 43, "decision": "approve"}
        self.assertTrue(self.valid("GithubApprovalForm", approval))
        self.assertTrue(self.valid("GithubApprovalForm", approval | {"decision": "deny"}))
        self.assertFalse(self.valid("GithubApprovalForm", approval | {"decision": "implicit"}))
        self.assertFalse(self.valid("GithubApprovalForm", {"flow_id": "flow-1", "decision": "approve"}))

    def test_enrollment_requires_bounded_key_proof_and_supported_platform(self):
        request = {"platform": "linux", "display_name": "Temporary device", "public_key": "A" * 43}
        for platform in ["linux", "macos", "windows", "ios", "android"]:
            self.assertTrue(self.valid("EnrollmentRequest", request | {"platform": platform}))
        self.assertFalse(self.valid("EnrollmentRequest", request | {"platform": "unknown"}))
        for key in ["", "A" * 42, "A" * 44, "A" * 42 + "B"]:
            self.assertFalse(self.valid("EnrollmentRequest", request | {"public_key": key}))
        proof = {"challenge_id": "challenge-1", "signature": "A" * 86}
        self.assertTrue(self.valid("EnrollmentProof", proof))
        self.assertFalse(self.valid("EnrollmentProof", {"challenge_id": "challenge-1"}))
        self.assertFalse(self.valid("EnrollmentProof", proof | {"signature": "A" * 85 + "B"}))

    def test_sync_outcomes_and_pages_have_explicit_bounds(self):
        applied = {"outcome": "applied", "operation_id": "operation-1", "server_seq": 1, "revision": 1}
        conflict = {"outcome": "conflict", "operation_id": "operation-1", "server_seq": 1,
                    "base_revision": 0, "current_revision": 1, "resolution_state": "unresolved"}
        for result in [applied, conflict]:
            self.assertTrue(self.valid("SyncResult", result))
            page = {"entries": [{"operation": self.operation(), "result": result}],
                    "next_after_seq": 1, "has_more": False}
            self.assertTrue(self.valid("SyncPage", page))
            self.assertFalse(self.valid("SyncPage", page | {"entries": page["entries"] * 101}))
        self.assertFalse(self.valid("SyncResult", applied | {"revision": 0}))
        self.assertFalse(self.valid("SyncResult", conflict | {"resolution_state": "silently_overwritten"}))

    def test_baseline_shapes_match_current_server_and_include_overload_errors(self):
        samples = {
            "health-response": {"status": "ok", "service": "nddev-device-sync-server", "version": "test",
                                "channel": "alpha", "standards_release": "test", "source_commit": "unknown",
                                "module_count": 0, "telemetry_enabled": True, "database_configured": False},
            "ready-response": {"status": "degraded", "database": "not_configured"},
            "source-response": {"source_url": "https://example.invalid/source", "license": "AGPL-3.0-only"},
            "error-response": {"error": "server_busy"},
        }
        for name, sample in samples.items():
            v = validator(self.documents[BASE + "v1/" + name + ".schema.json"], self.registry)
            v.validate(sample)
            self.assertFalse(v.is_valid(sample | {"private_key": "forbidden"}))

    def test_openapi_is_semantically_valid_and_planned_routes_are_not_capabilities(self):
        for filename in ["control-plane.yaml", "control-plane-v2.yaml"]:
            path = ROOT / "openapi" / filename
            api = yaml.safe_load(path.read_text())
            validate_api(api, path)
            expected = "planned" if "v2" in filename else "implemented"
            for item in api["paths"].values():
                for method, operation in item.items():
                    if method in {"get", "post", "delete"}:
                        self.assertEqual(operation["x-implementation-status"], expected)
            invalid = copy.deepcopy(api)
            invalid.pop("info")
            with self.assertRaises(OpenAPIValidationError):
                validate_api(invalid, path)
        self.assertEqual(set(yaml.safe_load((ROOT / "openapi/control-plane.yaml").read_text())["paths"]),
                         {"/v1/health", "/v1/ready", "/source"})

    def test_missing_or_remote_refs_fail_instead_of_being_silently_ignored(self):
        path = ROOT / "openapi/control-plane.yaml"
        original = yaml.safe_load(path.read_text())
        for reference in ["../contracts/v1/missing.schema.json", "https://example.invalid/schema", "#/missing", "../.git/config", "../README.md"]:
            api = copy.deepcopy(original)
            api["paths"]["/v1/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] = {"$ref": reference}
            with self.assertRaises((ValueError, KeyError)):
                validate_api(api, path)

    def test_telemetry_has_closed_typed_context_and_bounded_batches(self):
        event = {"timestamp": "2026-01-01T00:00:00Z", "severity": "info", "service.name": "nddev-device-sync-server",
                 "service.version": "test", "release.channel": "alpha", "release.version": "test", "standards.release": "test",
                 "deployment.environment": "self-hosted", "source.repository": "NDDev-OpenNetwork/nddev-device-sync-server",
                 "source.commit": "unknown", "module": "process", "event.name": "server.shutdown.started"}
        v = validator(self.documents[BASE + "v2/telemetry-event.schema.json"], self.registry)
        v.validate(event)
        v.validate(event | {"max_connections": 4096, "deadline_seconds": 20})
        for field, value in [("max_connections", 4097), ("event.name", "x" * 129),
                             ("message", "unbounded dump"), ("attributes", {}),
                             ("email", "owner@example.invalid"), ("route", "/v2/auth/github/callback?code=forbidden"),
                             ("trace_id", "0" * 32), ("duration_ms", -1), ("status", 600)]:
            self.assertFalse(v.is_valid(event | {field: value}), field)
        batch = validator(self.documents[BASE + "v2/telemetry-batch.schema.json"], self.registry)
        batch.validate([event] * 100)
        self.assertFalse(batch.is_valid([]))
        self.assertFalse(batch.is_valid([event] * 101))

    def test_actual_identity_context_and_producer_pair_are_closed_and_bounded(self):
        event = {"timestamp": "2026-01-01T00:00:00Z", "severity": "info", "service.name": "nddev-device-sync-server",
                 "service.version": "test", "release.channel": "alpha", "release.version": "test", "standards.release": "test",
                 "deployment.environment": "self-hosted", "source.repository": "NDDev-OpenNetwork/nddev-device-sync-server",
                 "source.commit": "unknown", "module": "process", "event.name": "identity.initialized",
                 "producer.instance_id": "00000000-0000-4000-8000-000000000001", "producer.sequence": 1,
                 "email_available": True, "github_available": False, "outcome": "ready"}
        v = validator(self.documents[BASE + "v2/telemetry-event.schema.json"], self.registry)
        v.validate(event)
        v.validate(event | {"auth_method": "email_otp", "available": True, "credentials_verified": False,
                            "retry_count": 4294967295, "backoff_seconds": 300, "dropped_count": 17,
                            "challenge_invalidated": True, "mailbox_delivery": "unverified",
                            "outcome": "provider_accepted"})
        for field in ["device.id","user.id","tenant.id"]:
            for value in ["A"*43,"00000000-0000-4000-8000-000000000001","x"*128]:
                self.assertTrue(v.is_valid(event|{field:value}),field)
            for value in ["","x"*129,"account/name","account\n","owner@example.invalid","é",None,1]:
                self.assertFalse(v.is_valid(event|{field:value}),(field,value))
        for scope in ["io","process","http"]:
            self.assertTrue(v.is_valid(event|{"scope":scope,"reason":"operator"}))
        for field,value in [("scope","everything"),("device.name","private display name"),("public_key","A"*43),("token","forbidden")]:
            self.assertFalse(v.is_valid(event|{field:value}),field)
        for name in ["producer.instance_id", "producer.sequence"]:
            incomplete = event.copy()
            incomplete.pop(name)
            self.assertFalse(v.is_valid(incomplete))
        for name, value in [("producer.instance_id", "not-a-uuid"), ("producer.sequence", 0),
                            ("producer.sequence", 9007199254740992), ("retry_count", 4294967296),
                            ("backoff_seconds", 301), ("available", "true"),
                            ("mailbox_delivery", "delivered"), ("email", "owner@example.invalid"),
                            ("csrf_token", "forbidden"), ("message", "forbidden")]:
            self.assertFalse(v.is_valid(event | {name: value}), name)

    def test_observability_actions_sources_and_export_state_are_bounded(self):
        schema=self.documents[BASE+"v2/observability.schema.json"]
        valid=lambda definition,value:validator(schema,self.registry,definition).is_valid(value)
        operation={"operation_id":"01900000-0000-7000-8000-000000000001","expected_revision":1}
        self.assertTrue(valid("IncidentAction",operation))
        for key,value in [("operation_id","01900000-0000-4000-8000-000000000001"),("expected_revision",0),("expected_revision",9007199254740992),("actor_id","injected")]:
            self.assertFalse(valid("IncidentAction",operation|{key:value}))
        self.assertFalse(valid("SilenceAction",operation|{"until":"not-a-time"}))
        source={"service_name":"server","state":"inactive","gap_observations":0}
        delivery={"state":"disabled","successes":0,"failures":0}
        status={"export_mode":"disabled","queued_events":4096,"queued_bytes":67108864,"delivered_events":0,"expired_events":0,"sources":[source]*16,"logs":delivery,"metrics":delivery,"traces":delivery}
        self.assertTrue(valid("ObservabilityStatus",status))
        for key,value in [("sources",[source]*17),("queued_events",4097),("queued_bytes",67108865),("export_mode","pretend_healthy")]:
            self.assertFalse(valid("ObservabilityStatus",status|{key:value}))
        self.assertFalse(valid("SourceHealth",source|{"gap_observations":-1}))
        self.assertFalse(valid("SignalDelivery",delivery|{"notification_sent":True}))


if __name__ == "__main__":
    unittest.main()
