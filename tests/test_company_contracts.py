"""Company wire scope and bounded shapes; adapters prove actual authority."""
from pathlib import Path
import sys
import unittest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate import ROOT, schemas, validator


class CompanyContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        documents, cls.registry = schemas()
        cls.schema = documents["https://nddev.ai/schemas/nddev-device-sync/v2/company.schema.json"]

    def valid(self, name, value):
        return validator(self.schema, self.registry, name).is_valid(value)

    def test_commands_cannot_claim_company_or_replace_immutable_deadline(self):
        operation = "01900000-0000-7000-8000-000000000001"
        value = {"operation_id": operation, "email": "member@example.invalid", "role": "user"}
        self.assertTrue(self.valid("CompanyInvitationRequest", value))
        for extra in ["tenant_id", "company_id", "issuer_user_id", "expires_at_ms", "invitation_token"]:
            self.assertFalse(self.valid("CompanyInvitationRequest", value | {extra: "injected"}))
        for invalid in [operation.replace("-7000-", "-4000-"), operation[:-1] + "A", operation + "\n"]:
            self.assertFalse(self.valid("CommandId", invalid))

    def test_removal_and_role_change_are_exclusive_and_revision_checked(self):
        value = {"operation_id": "01900000-0000-7000-8000-000000000001", "expected_revision": 1, "action": "remove", "role": None}
        self.assertTrue(self.valid("CompanyMemberChangeRequest", value))
        self.assertTrue(self.valid("CompanyMemberChangeRequest", value | {"action": "set_role", "role": "admin"}))
        for changed in [{"role": "user"}, {"action": "set_role"}, {"expected_revision": 0}, {"expected_revision": 9007199254740992}]:
            self.assertFalse(self.valid("CompanyMemberChangeRequest", value | changed))
        del value["role"]
        self.assertFalse(self.valid("CompanyMemberChangeRequest", value))

    def test_pages_and_metadata_are_bounded_and_exclude_invitation_secrets(self):
        member = {"user_id": "user-1", "email": None, "role": "user", "active": True, "revision": 1}
        self.assertTrue(self.valid("CompanyMemberPage", {"members": [member] * 50, "next_cursor": None}))
        self.assertFalse(self.valid("CompanyMemberPage", {"members": [member] * 51, "next_cursor": None}))
        invite = {"invitation_id": "A" * 43, "issuer_user_id": "admin-1", "recipient_email": "member@example.invalid", "role": "user", "expires_at_ms": 604801000, "status": "pending", "delivery": "unknown"}
        self.assertTrue(self.valid("CompanyInvitation", invite))
        for extra in ["token", "verifier", "session_token", "vault_key", "recipient_binding"]:
            self.assertFalse(self.valid("CompanyInvitation", invite | {extra: "sensitive"}))

    def test_all_company_routes_require_session_and_device_proof(self):
        api = yaml.safe_load((ROOT / "openapi/control-plane-v2.yaml").read_text())
        routes = {path: operations for path, operations in api["paths"].items() if path.startswith("/v2/company")}
        self.assertEqual(sum(len(operations) for operations in routes.values()), 6)
        for operations in routes.values():
            for operation in operations.values():
                self.assertEqual(operation["security"], [{"ownerSession": [], "deviceSignature": []}, {"browserSession": [], "deviceSignature": []}])
                refs = {item.get("$ref") for item in operation["parameters"]}
                for header in ["SignatureInput", "Signature", "ContentDigest"]:
                    self.assertIn("#/components/parameters/" + header, refs)
