"""Structural/route boundaries only; actual NDS crypto/SQL/capture is consumer-owned."""
import base64
from pathlib import Path
import sys
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate import ROOT, schemas, validator

BASE = "https://nddev.ai/schemas/nddev-device-sync/v2/"


class ScreenContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        documents, cls.registry = schemas()
        cls.schema = documents[BASE + "screen.schema.json"]
        cls.common = documents[BASE + "control-plane.schema.json"]

    def valid(self, name, value):
        return validator(self.schema, self.registry, name).is_valid(value)

    def binding(self):
        return {"device_id": "device-1", "endpoint_public_key": "A" * 43,
                "instance_id": "01900000-0000-7000-8000-000000000001", "revision": 1}

    def claim(self):
        return {"endpoint_public_key": "A" * 43, "instance_id": self.binding()["instance_id"],
                "base_revision": 0, "nonce": "screen_nonce_0001", "expires_at_ms": 60000,
                "signature": "A" * 86}

    def request(self):
        return {"target_device_id": "device-2", "viewer_revision": 1, "host_revision": 2,
                "display": 0, "max_fps": 30, "output_height": 1080,
                "expires_at_ms": 3999, "idempotency_key": "view-request-1"}

    def view(self):
        return {"view_id": "view-1", "viewer_device_id": "device-1", "host_device_id": "device-2",
                "viewer_endpoint": "A" * 43, "host_endpoint": "Q" * 42 + "A",
                "viewer_revision": 1, "host_revision": 2, "display": 0, "max_fps": 30,
                "output_height": 1080, "admitted_at_ms": 1000, "expires_at_ms": 3000,
                "state": "requested"}

    def test_targets_are_bounded_minimal_and_explicitly_registered(self):
        target = {"device_id":"device-1","display_name":"Owned device","platform":"linux","registered":False}
        page = {"user_id":"user-1","targets":[target]}
        self.assertTrue(self.valid("ScreenTargetList", page))
        self.assertTrue(self.valid("ScreenTargetList", page | {"targets":[]}))
        for field in target:
            self.assertFalse(self.valid("ScreenTarget", {key:value for key,value in target.items() if key != field}))
        for extra in ["public_key", "created_at", "user_id", "vault_key", "online"]:
            self.assertFalse(self.valid("ScreenTarget", target | {extra:"not-discovery-data"}))
        for platform in ["unknown", ""]:
            self.assertFalse(self.valid("ScreenTarget", target | {"platform":platform}))
        targets = [target | {"device_id":f"device-{i}"} for i in range(33)]
        self.assertTrue(self.valid("ScreenTargetList", page | {"targets":targets[:32]}))
        self.assertFalse(self.valid("ScreenTargetList", page | {"targets":targets}))
        self.assertFalse(self.valid("ScreenTargetList", page | {"targets":[target,target]}))
        self.assertFalse(self.valid("ScreenTargetList", {"targets":[]}))

    def test_closed_models_require_original_fields_and_reject_unowned_data(self):
        cases = {"ScreenBinding": self.binding(), "ScreenBindRequest": self.claim(),
                 "ScreenViewRequest": self.request(), "ScreenView": self.view(),
                 "ScreenReadyRequest": {"native_grant": "AA"}}
        for name, original in cases.items():
            self.assertTrue(self.valid(name, original), name)
            for field in original:
                altered = original.copy()
                del altered[field]
                self.assertFalse(self.valid(name, altered), (name, field))
            for field in ["user_id", "tenant_id", "viewer_session", "device_private_key", "frames",
                          "locator", "displays", "source_ready", "local_opt_in"]:
                self.assertFalse(self.valid(name, original | {field: "injected"}), (name, field))

    def test_binding_primitives_uuid_revision_and_context_bounds(self):
        claim = self.claim()
        for field, values in {
            "endpoint_public_key": ["A" * 42, "A" * 42 + "B", "A" * 43 + "="],
            "signature": ["A" * 85, "A" * 85 + "B", "A" * 86 + "="],
            "instance_id": ["00000000-0000-0000-0000-000000000000", "not-a-uuid",
                            "01900000-0000-7000-8000-00000000000A", "01900000000070008000000000000001"],
            "nonce": ["A" * 15, "A" * 129, "screen_nonce_0001\n", "bad nonce", "bad=nonce"],
            "base_revision": [-1, 9007199254740991, 1.5, True],
            "expires_at_ms": [0, -1, 60001, 9007199254740992, True, "60000"],
        }.items():
            for value in values:
                self.assertFalse(self.valid("ScreenBindRequest", claim | {field: value}), (field, value))
        self.assertTrue(self.valid("ScreenBindRequest", claim | {"base_revision": 9007199254740990}))
        self.assertFalse(self.valid("ScreenBinding", self.binding() | {"revision": 0}))

    def test_profile_bounds_do_not_assume_contiguous_display_indices(self):
        request = self.request()
        for field, values in {"max_fps": [0, 61, True, 1.5], "output_height": [0, 15, 1081],
                              "display": [-1, 4294967296], "viewer_revision": [0],
                              "host_revision": [0], "idempotency_key": ["", "x" * 257]}.items():
            for value in values:
                self.assertFalse(self.valid("ScreenViewRequest", request | {field: value}), (field, value))
        self.assertTrue(self.valid("ScreenViewRequest", request | {"display": 2147483648}))
        self.assertTrue(self.valid("ScreenViewRequest", request | {"display": 4294967295}))
        self.assertFalse(self.valid("ScreenView", self.view() | {"view_id": "x" * 65}))
        self.assertFalse(self.valid("ScreenView", self.view() | {"expires_at_ms": 3999}))
        self.assertFalse(self.valid("ScreenView", self.view() | {"state": "watching"}))

    def test_grant_encoding_is_canonical_and_bounded_before_decode(self):
        encode = lambda body: base64.urlsafe_b64encode(body).decode().rstrip("=")
        for length in [1, 2, 3, 8191, 8192]:
            self.assertTrue(self.valid("NativeGrant", encode(bytes([255]) * length)), length)
        self.assertFalse(self.valid("NativeGrant", encode(bytes(8193))))
        for value in ["", "A", "AB", "AAB", "AA=", "+A", "/A", "AA\n", "AA "]:
            self.assertFalse(self.valid("NativeGrant", value), value)
        self.assertTrue(self.schema["$defs"]["NativeGrant"]["x-sensitive"])
        self.assertEqual(self.schema["$defs"]["NativeGrant"]["x-max-decoded-bytes"], 8192)

    def test_required_null_distinguishes_absence_and_ready_artifact(self):
        for name, field in [("ScreenBindingResponse", "binding"), ("ScreenIncoming", "view")]:
            self.assertTrue(self.valid(name, {field: None}))
            self.assertFalse(self.valid(name, {}))
            self.assertFalse(self.valid(name, {field: []}))
        response = {"view": self.view(), "native_grant": None}
        self.assertTrue(self.valid("ScreenViewResponse", response))
        self.assertFalse(self.valid("ScreenViewResponse", {"view": self.view()}))
        self.assertFalse(self.valid("ScreenViewResponse", response | {"native_grant": "AA"}))
        ready = self.view() | {"state": "ready"}
        self.assertTrue(self.valid("ScreenViewResponse", {"view": ready, "native_grant": "AA"}))
        self.assertFalse(self.valid("ScreenViewResponse", {"view": ready, "native_grant": None}))
        self.assertTrue(self.valid("ScreenViewResponse", {"view": self.view() | {"state": "ended"}, "native_grant": None}))

    def test_common_primitives_errors_and_auth_scheme_are_reused(self):
        api = yaml.safe_load((ROOT / "openapi/control-plane-v2.yaml").read_text())
        methods = {"/v2/rds/targets/{user_id}": "get", "/v2/rds/bindings/{device_id}": "get", "/v2/rds/bindings": "post",
                   "/v2/rds/views": "post", "/v2/rds/views/incoming": "get",
                   "/v2/rds/views/{view_id}": "get", "/v2/rds/views/{view_id}/ready": "post",
                   "/v2/rds/views/{view_id}/end": "post"}
        self.assertEqual({p for p in api["paths"] if p.startswith("/v2/rds/")}, set(methods))
        for path, method in methods.items():
            op = api["paths"][path][method]
            self.assertEqual(op["security"], [{"ownerSession": [], "deviceSignature": []},
                                            {"browserSession": [], "deviceSignature": []}])
            refs = {p.get("$ref") for p in op["parameters"]}
            self.assertTrue({"#/components/parameters/SignatureInput", "#/components/parameters/Signature",
                             "#/components/parameters/ContentDigest"} <= refs)
        end = api["paths"]["/v2/rds/views/{view_id}/end"]["post"]
        self.assertNotIn("requestBody", end)
        self.assertNotIn("content", end["responses"]["204"])
        self.assertIn("another same-owner device is not a participant", end["description"])
        self.assertEqual(self.schema["$defs"]["Error"]["$ref"], BASE + "control-plane.schema.json#/$defs/Error")
        self.assertTrue(self.valid("Error", {"error": "authorization_denied"}))
        self.assertFalse(self.valid("Error", {"error": "screen_authentication_success"}))
        self.assertEqual(self.schema["x-codegen-languages"], ["rust"])


if __name__ == "__main__":
    unittest.main()
