# Structural schema tests only; Core/adapters verify decoded original rows,
# sparse membership, AEAD, receipts and stage/cursor transactions separately.
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from validate import schemas, validator
BASE = 'https://nddev.ai/schemas/nddev-device-sync/'

class SyncLifecycle(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.docs, cls.registry = schemas()
        cls.new = cls.docs[BASE + 'v3/sync.schema.json']
        cls.old = cls.docs[BASE + 'v2/control-plane.schema.json']

    def operation(self):
        return {'schema_version': 3, 'operation_id': 'v3:2:id', 'device_id': 'device', 'entity_type': 'repository_state', 'entity_id': 'github:repo:1', 'base_revision': 0, 'idempotency_key': 'v3:2:key', 'basis_seq': 2, 'lifecycle': {'resolved_through_seq': 2}, 'payload': {'algorithm': 'aes-256-gcm', 'key_id': 'key', 'nonce': 'A' * 16, 'ciphertext': 'A' * 22}}

    def valid(self, doc, name, value):
        return validator(doc, self.registry, name).is_valid(value)

    def test_new_version_and_required_single_lifecycle(self):
        value = self.operation()
        self.assertTrue(self.valid(self.new, 'SyncOperationV3', value))
        self.assertFalse(self.valid(self.old, 'SyncOperation', value))
        for field in ['basis_seq', 'lifecycle']:
            missing = copy.deepcopy(value)
            del missing[field]
            self.assertFalse(self.valid(self.new, 'SyncOperationV3', missing))
        for version in [1, 2, 4]:
            bad = value | {'schema_version': version}
            self.assertFalse(self.valid(self.new, 'SyncOperationV3', bad))

    def test_old_operation_has_no_new_kind_or_header(self):
        old = self.operation()
        old['schema_version'] = 2
        old['entity_type'] = 'vault_record'
        old['operation_id'] = 'v3:999:legacy'
        old['idempotency_key'] = 'legacy'
        del old['basis_seq']
        del old['lifecycle']
        self.assertTrue(self.valid(self.old, 'SyncOperation', old))
        self.assertFalse(self.valid(self.new, 'SyncOperationV3', old))
        old['entity_type'] = 'repository_state'
        self.assertFalse(self.valid(self.old, 'SyncOperation', old))

    def test_closed_lifecycle_and_safe_counter_limits(self):
        value = self.operation()
        value['lifecycle']['inner_override'] = 2
        self.assertFalse(self.valid(self.new, 'SyncOperationV3', value))
        for number in [-1, 9007199254740992, 1.25]:
            value = self.operation()
            value['basis_seq'] = number
            self.assertFalse(self.valid(self.new, 'SyncOperationV3', value))

    def test_raw_row_preserves_transport_bytes_and_sparse_cursor(self):
        raw = ' { "schema_version" : 2, "operation_id":"legacy" }\n'
        row = {'server_seq': 2, 'operation_body': raw, 'result_status': 409, 'result_body': '{"outcome":"conflict"}'}
        base = {'schema_version': 3, 'base_seq': 8, 'total_members': 1, 'entries': [row], 'next_member_seq': 2, 'has_more': False}
        self.assertTrue(self.valid(self.new, 'SyncBasePage', base))
        self.assertEqual(base['entries'][0]['operation_body'], raw)
        self.assertFalse(self.valid(self.old, 'SyncPage', base))

    def test_expired_is_explicit_unknown_and_never_a_result(self):
        expired = {'schema_version': 3, 'error': 'basis_expired', 'floor_seq': 8, 'head_seq': 8}
        self.assertTrue(self.valid(self.new, 'SyncExpired', expired))
        self.assertFalse(self.valid(self.old, 'SyncApplied', expired))

    def test_original_raw_request_and_result_caps_do_not_expand_storage(self):
        props = self.new['$defs']['SyncRow']['properties']
        self.assertEqual(props['operation_body']['maxLength'], 24576)
        self.assertEqual(props['operation_body']['x-max-utf8-bytes'], 24576)
        self.assertEqual(props['result_body']['maxLength'], 2048)
        self.assertEqual(props['result_body']['x-max-utf8-bytes'], 2048)
        row = {'server_seq': 1, 'operation_body': 'x' * 24576, 'result_status': 201, 'result_body': 'x' * 2048}
        self.assertTrue(self.valid(self.new, 'SyncRow', row))
        self.assertFalse(self.valid(self.new, 'SyncRow', row | {'operation_body': row['operation_body'] + 'x'}))
        self.assertFalse(self.valid(self.new, 'SyncRow', row | {'result_body': row['result_body'] + 'x'}))
        self.assertFalse(self.valid(self.new, 'SyncRow', row | {'result_body': 'x' * 24576}))
        # JSON Schema length is character-based. Canonical UTF-8 byte checks
        # are exercised in Core/wire fixtures, before decoding or stage writes.
