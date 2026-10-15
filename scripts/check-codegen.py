"""Compile and round-trip generated consumer DTOs; never claim backend acceptance."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN = tomllib.loads((ROOT / "rust-toolchain.toml").read_text())["toolchain"]["channel"]


def run(args, cwd=ROOT):
    subprocess.run(args, cwd=cwd, check=True, timeout=300)


def main():
    for command in ["node", "rustup", "dart"]:
        if shutil.which(command) is None:
            raise SystemExit(f"Missing generated-code acceptance tool: {command}")
    samples = {
        "health": ("HealthResponse", {"status": "ok", "service": "nddev-device-sync-server",
                   "version": "test", "channel": "alpha", "standards_release": "test", "source_commit": "unknown",
                   "module_count": 0, "telemetry_enabled": True, "database_configured": False}),
        "ready": ("ReadyResponse", {"status": "degraded", "database": "not_configured"}),
        "source": ("SourceResponse", {"source_url": "https://example.invalid/source", "license": "AGPL-3.0-only"}),
    }
    session = {"user_id": "user-1", "tenant_id": "tenant-1", "auth_method": "github", "expires_at": "2026-01-01T00:00:00Z"}
    auth_samples = {
        "AuthMethods": {"email_otp": "available", "github": "unavailable", "passkey": "unavailable"},
        "EmailChallengeRequest": {"email": "owner@example.invalid"},
        "EmailChallenge": {"challenge_id": "challenge-1", "expires_in_seconds": 300, "resend_after_seconds": 30},
        "EmailVerifyRequest": {"challenge_id": "challenge-1", "code": "12345678"},
        "Session": session, "SessionIssued": {"session": session, "session_token": "A" * 43},
        "GithubStart": {"flow_id": "flow-1", "authorization_url": "https://github.com/login/oauth/authorize", "exchange_token": "A" * 43, "expires_in_seconds": 300, "poll_after_seconds": 2, "verification_code": "12345678"},
        "GithubExchangeRequest": {"flow_id": "flow-1", "exchange_token": "A" * 43},
        "GithubPending": {"status": "pending", "retry_after_seconds": 2},
        "GithubApprovalForm": {"flow_id": "flow-1", "csrf_token": "A" * 43, "decision": "approve"},
        "Error": {"error": "authentication_failed"},
    }
    auth_samples["PasskeyStart"] = auth_samples["GithubStart"]
    auth_samples["PasskeyRequest"] = {"registration": False}
    auth_samples["PasskeyStatus"] = {"status": "pending", "retry_after_seconds": 2}
    device = {"device_id":"device-1","platform":"linux","display_name":"Owned acceptance device","public_key":"A"*43,"status":"active","created_at":"2026-01-01T00:00:00Z"}
    device_samples = {
        "EnrollmentRequest": {"platform":"linux","display_name":"Owned acceptance device","public_key":"A"*43},
        "EnrollmentChallenge": {"challenge_id":"challenge-1","device_id":"device-1","challenge":"A"*43,"expires_at":"2026-01-01T00:00:00Z"},
        "EnrollmentProof": {"challenge_id":"challenge-1","signature":"A"*86},
        "Device":device,"DeviceList":{"devices":[device],"next_cursor":None},"Error":{"error":"invalid_request"},
    }
    incident={"incident_id":"incident-1","dedup_key":"server:admission:requests","service_name":"server","kind":"admission","state":"open","revision":1,"occurrences":1,"first_seen":"2026-01-01T00:00:00Z","last_seen":"2026-01-01T00:00:00Z","owner":"operator","severity":"warning"}
    source={"service_name":"server","state":"inactive","gap_observations":0}
    delivery={"state":"unknown","successes":0,"failures":0}
    action={"operation_id":"01900000-0000-7000-8000-000000000001","expected_revision":1}
    observability_samples={
        "Incident":incident,"IncidentPage":{"incidents":[incident],"generated_at":"2026-01-01T00:00:00Z"},
        "IncidentAction":action,"SilenceAction":action|{"until":"2026-01-01T01:00:00Z"},
        "SourceHealth":source,"IngressReceipt":{"accepted":1,"duplicates":0,"export_mode":"enabled"},
        "SignalDelivery":delivery,"ObservabilityStatus":{"export_mode":"enabled","queued_events":0,"queued_bytes":0,"delivered_events":0,"expired_events":0,"sources":[source],"logs":delivery,"metrics":delivery,"traces":delivery},
        "ObservabilityError":{"error":"invalid_request"},
    }
    vault_samples = {"VaultKey": {"key_id": "01900000-0000-7000-8000-000000000001", "key_material": "A" * 64}, "VaultKeyRequest": {"existing_key": None}, "Error": {"error": "vault_key_registration_required"}}
    screen_binding = {"device_id":"device-1","endpoint_public_key":"A"*43,
                      "instance_id":"01900000-0000-7000-8000-000000000001","revision":1}
    screen_view = {"view_id":"view-1","viewer_device_id":"device-1","host_device_id":"device-2",
                   "viewer_endpoint":"A"*43,"host_endpoint":"Q"*42+"A",
                   "viewer_revision":1,"host_revision":2,"display":0,"max_fps":30,
                   "output_height":1080,"admitted_at_ms":1000,"expires_at_ms":3000,"state":"requested"}
    screen_samples = {
        "ScreenBinding":screen_binding,"ScreenBindingResponse":{"binding":None},
        "ScreenBindRequest":{"endpoint_public_key":"A"*43,"instance_id":screen_binding["instance_id"],
                             "base_revision":0,"nonce":"nonce_for_screen_1","expires_at_ms":60000,"signature":"A"*86},
        "ScreenViewRequest":{"target_device_id":"device-2","viewer_revision":1,"host_revision":2,
                             "display":0,"max_fps":30,"output_height":1080,"expires_at_ms":3999,"idempotency_key":"view-request-1"},
        "ScreenView":screen_view,"ScreenIncoming":{"view":None},
        "ScreenViewResponse":{"view":screen_view,"native_grant":None},
        "ScreenReadyRequest":{"native_grant":"AA"},"Error":{"error":"authorization_denied"},
    }
    telemetry = {"timestamp": "2026-01-01T00:00:00Z", "severity": "info", "service.name": "nddev-device-sync-server",
                 "service.version": "test", "release.channel": "alpha", "release.version": "test", "standards.release": "test",
                 "deployment.environment": "self-hosted", "source.repository": "NDDev-OpenNetwork/nddev-device-sync-server",
                 "source.commit": "unknown", "module": "process", "event.name": "server.shutdown.started", "deadline_seconds": 20}
    with tempfile.TemporaryDirectory(prefix="nds-protocol-codegen-") as temporary:
        work = Path(temporary)
        (work / "src").mkdir()
        rust = ["use serde::{Serialize, de::DeserializeOwned};", "use serde_json::Value;",
                "fn check<T: Serialize + DeserializeOwned>(text: &str) { let value: Value = serde_json::from_str(text).unwrap(); let model: T = serde_json::from_value(value.clone()).unwrap(); assert_eq!(serde_json::to_value(model).unwrap(), value); }"]
        dart = ["import 'dart:convert';"]
        for profile in [*samples, "auth", "devices", "telemetry", "observability", "sync", "sync3", "vault", "screen"]:
            rust.append(f"pub mod {profile};")
            languages = ["rust"] if profile in {"telemetry","observability","sync","sync3","vault","screen"} else ["rust", "dart"]
            for language in languages:
                path = work / "src" / (profile + (".rs" if language == "rust" else ".dart"))
                command = ["node", "scripts/generate-dtos.mjs", language, profile, str(path)]
                run(command)
                first = path.read_bytes()
                run(command)
                if first != path.read_bytes():
                    raise AssertionError("DTO generation is not deterministic")
            if profile not in {"telemetry","observability","sync","sync3","vault","screen"}:
                dart.append(f"import '{profile}.dart' as {profile};")
        rust.append("fn main() {")
        dart += [
            "Object? canonical(Object? value) {",
            "  if (value is Map<String, dynamic>) { final keys = value.keys.toList()..sort(); return {for (final key in keys) key: canonical(value[key])}; }",
            "  if (value is List) return value.map(canonical).toList();",
            "  return value;",
            "}",
            "void check(Map<String, dynamic> actual, String original) { if (jsonEncode(canonical(actual)) != jsonEncode(canonical(jsonDecode(original)))) throw StateError('wire round-trip changed data'); }",
            "void main() {",
        ]
        for profile, (name, value) in samples.items():
            encoded = json.dumps(value, separators=(",", ":"))
            rust.append(f'check::<{profile}::{name}>(r#"{encoded}"#);')
            dart.append(f"check({profile}.{name}.fromJson(jsonDecode(r'{encoded}') as Map<String, dynamic>).toJson(), r'{encoded}');")
        for profile, models in [("auth",auth_samples),("devices",device_samples)]:
            for name,value in models.items():
                encoded=json.dumps(value,separators=(",", ":"))
                rust.append(f'check::<{profile}::{name}>(r#"{encoded}"#);')
                dart.append(f"check({profile}.{name}.fromJson(jsonDecode(r'{encoded}') as Map<String, dynamic>).toJson(), r'{encoded}');")
        for name,value in vault_samples.items():
            rust.append(f'check::<vault::{name}>(r#"{json.dumps(value)}"#);')
        for name,value in observability_samples.items():
            rust.append(f'check::<observability::{name}>(r#"{json.dumps(value)}"#);')
        for name,value in screen_samples.items():
            rust.append(f'check::<screen::{name}>(r#"{json.dumps(value)}"#);')
        for name,value in [("ScreenBindingResponse", {"binding":screen_binding}),
                           ("ScreenIncoming", {"view":screen_view}),
                           ("ScreenViewResponse", {"view":screen_view|{"state":"ready"},"native_grant":"AA"})]:
            rust.append(f'check::<screen::{name}>(r#"{json.dumps(value)}"#);')
        for name in ["ScreenBindingResponse", "ScreenIncoming", "ScreenViewResponse"]:
            rust.append(f'assert!(serde_json::from_str::<screen::{name}>(r#"{{}}"#).is_err());')
        rust.append(f'assert!(serde_json::from_str::<screen::ScreenViewResponse>(r#"{json.dumps({"view":screen_view})}"#).is_err());')
        rust.append('assert!(serde_json::from_str::<screen::ScreenReadyRequest>(r#"{"native_grant":"AA","viewer_session":"injected"}"#).is_err());')
        # Sensitive control DTOs must have no public Dart profile or Debug derive.
        rejected = subprocess.run(["node","scripts/generate-dtos.mjs","dart","screen",str(work/"screen.dart")],
                                  cwd=ROOT,capture_output=True,text=True,timeout=30)
        if rejected.returncode == 0 or (work/"screen.dart").exists():
            raise AssertionError("screen control DTOs leaked into a Dart profile")
        if "Debug" in (work/"src/screen.rs").read_text():
            raise AssertionError("sensitive screen DTOs expose Debug")
        operation={"schema_version":2,"operation_id":"operation-1","device_id":"device-1","entity_type":"vault_record","entity_id":"record-1","base_revision":0,"idempotency_key":"operation-1","payload":{"algorithm":"aes-256-gcm","key_id":"key-1","nonce":"A"*16,"ciphertext":"A"*22}}
        applied={"outcome":"applied","operation_id":"operation-1","server_seq":1,"revision":1}
        conflict={"outcome":"conflict","operation_id":"operation-1","server_seq":2,"base_revision":0,"current_revision":1,"resolution_state":"unresolved"}
        for result in [applied,conflict]:
            page={"entries":[{"operation":operation,"result":result}],"has_more":False,"next_after_seq":result["server_seq"]}
            rust.append(f'check::<sync::SyncPage>(r#"{json.dumps(page)}"#);')
        invalid=applied|{"current_revision":1}
        rust.append(f'assert!(serde_json::from_str::<sync::Sync>(r#"{json.dumps(invalid)}"#).is_err());')
        for code in ["server_busy", "sync_capacity_exhausted"]:
            encoded = json.dumps({"error": code})
            for profile in ["auth", "devices", "sync", "vault"]:
                rust.append(f'check::<{profile}::Error>(r#"{encoded}"#);')
            rust.append(f'assert!(serde_json::from_str::<sync::Sync>(r#"{encoded}"#).is_err());')
            rust.append(f'assert!(serde_json::from_str::<sync::SyncPage>(r#"{encoded}"#).is_err());')
        rust.append(f'check::<telemetry::TelemetryEvent>(r#"{json.dumps(telemetry)}"#);')
        rust.append('assert!(serde_json::from_str::<auth::EmailVerifyRequest>(r#"{"challenge_id":"challenge-1","code":"12345678","user_id":"injected"}"#).is_err());')
        rust.append('assert!(serde_json::from_str::<devices::DeviceList>(r#"{"devices":[]}"#).is_err());')
        v3_operation={"schema_version":3,"operation_id":"v3:2:operation-1","device_id":"device-1","entity_type":"repository_state","entity_id":"github:repo:1","base_revision":0,"idempotency_key":"v3:2:operation-1","basis_seq":2,"lifecycle":{"resolved_through_seq":0},"payload":{"algorithm":"aes-256-gcm","key_id":"key-1","nonce":"A"*16,"ciphertext":"A"*22}}
        v3_samples={"SyncOperationV3":v3_operation,"Lifecycle":{"resolved_through_seq":0},"SyncCapabilities":{"schema_version":3,"new_operation_version":2,"read_operation_versions":[2,3],"history_retention":False},"SyncExpired":{"schema_version":3,"error":"basis_expired","floor_seq":3,"head_seq":3},"SyncBasePage":{"schema_version":3,"base_seq":3,"total_members":0,"entries":[],"next_member_seq":0,"has_more":False},"SyncDeltaPage":{"schema_version":3,"floor_seq":3,"head_seq":3,"entries":[],"next_after_seq":3,"has_more":False}}
        for name,value in v3_samples.items():
            rust.append(f'check::<sync3::{name}>(r#"{json.dumps(value)}"#);')
        rust.append(f'assert!(serde_json::from_str::<sync::SyncOperation>(r#"{json.dumps(v3_operation)}"#).is_err());')
        bad=v3_operation|{"extra":"injected"}
        rust.append(f'assert!(serde_json::from_str::<sync3::SyncOperationV3>(r#"{json.dumps(bad)}"#).is_err());')
        missing=dict(v3_operation);del missing["lifecycle"]
        rust.append(f'assert!(serde_json::from_str::<sync3::SyncOperationV3>(r#"{json.dumps(missing)}"#).is_err());')
        rust.append("}")
        dart.append("bool missingRejected=false; try { devices.DeviceList.fromJson({\"devices\":[]}); } on FormatException { missingRejected=true; } if (!missingRejected) throw StateError(\"required nullable key missing\");")
        dart.append("}")
        (work / "src/main.rs").write_text("\n".join(rust) + "\n")
        (work / "src/main.dart").write_text("\n".join(dart) + "\n")
        (work / "Cargo.toml").write_text('[package]\nname="nds-protocol-codegen-check"\nversion="0.0.0"\nedition="2024"\n[dependencies]\nserde={version="=1.0.229",features=["derive"]}\nserde_json="=1.0.151"\n')
        shutil.copyfile(ROOT / "tests/codegen-rust.lock", work / "Cargo.lock")
        run(["rustup", "run", TOOLCHAIN, "cargo", "run", "--locked", "--quiet"], work)
        run(["rustup", "run", TOOLCHAIN, "cargo", "clippy", "--locked", "--quiet", "--", "-D", "warnings"], work)
        run(["dart", "analyze", "--fatal-infos", "src"], work)
        run(["dart", "run", "src/main.dart"], work)
    print("Generated Rust/Dart DTOs compile, round-trip and regenerate deterministically; Rust rejects unknown input fields.")


if __name__ == "__main__":
    main()
