"""Compile and round-trip generated consumer DTOs; never claim backend acceptance."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


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
        "AuthMethods": {"email_otp": "available", "github": "unavailable"},
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
        for profile in [*samples, "auth", "devices", "telemetry", "observability", "sync"]:
            rust.append(f"pub mod {profile};")
            languages = ["rust"] if profile in {"telemetry","observability","sync"} else ["rust", "dart"]
            for language in languages:
                path = work / "src" / (profile + (".rs" if language == "rust" else ".dart"))
                command = ["node", "scripts/generate-dtos.mjs", language, profile, str(path)]
                run(command)
                first = path.read_bytes()
                run(command)
                if first != path.read_bytes():
                    raise AssertionError("DTO generation is not deterministic")
            if profile not in {"telemetry","observability","sync"}:
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
        for name,value in observability_samples.items():
            rust.append(f'check::<observability::{name}>(r#"{json.dumps(value)}"#);')
        operation={"schema_version":2,"operation_id":"operation-1","device_id":"device-1","entity_type":"vault_record","entity_id":"record-1","base_revision":0,"idempotency_key":"operation-1","payload":{"algorithm":"aes-256-gcm","key_id":"key-1","nonce":"A"*16,"ciphertext":"A"*22}}
        applied={"outcome":"applied","operation_id":"operation-1","server_seq":1,"revision":1}
        conflict={"outcome":"conflict","operation_id":"operation-1","server_seq":2,"base_revision":0,"current_revision":1,"resolution_state":"unresolved"}
        for result in [applied,conflict]:
            page={"entries":[{"operation":operation,"result":result}],"has_more":False,"next_after_seq":result["server_seq"]}
            rust.append(f'check::<sync::SyncPage>(r#"{json.dumps(page)}"#);')
        invalid=applied|{"current_revision":1}
        rust.append(f'assert!(serde_json::from_str::<sync::Sync>(r#"{json.dumps(invalid)}"#).is_err());')
        rust.append(f'check::<telemetry::TelemetryEvent>(r#"{json.dumps(telemetry)}"#);')
        rust.append('assert!(serde_json::from_str::<auth::EmailVerifyRequest>(r#"{"challenge_id":"challenge-1","code":"12345678","user_id":"injected"}"#).is_err());')
        rust.append('assert!(serde_json::from_str::<devices::DeviceList>(r#"{"devices":[]}"#).is_err());')
        rust.append("}")
        dart.append("bool missingRejected=false; try { devices.DeviceList.fromJson({\"devices\":[]}); } on FormatException { missingRejected=true; } if (!missingRejected) throw StateError(\"required nullable key missing\");")
        dart.append("}")
        (work / "src/main.rs").write_text("\n".join(rust) + "\n")
        (work / "src/main.dart").write_text("\n".join(dart) + "\n")
        (work / "Cargo.toml").write_text('[package]\nname="nds-protocol-codegen-check"\nversion="0.0.0"\nedition="2024"\n[dependencies]\nserde={version="=1.0.229",features=["derive"]}\nserde_json="=1.0.151"\n')
        shutil.copyfile(ROOT / "tests/codegen-rust.lock", work / "Cargo.lock")
        run(["rustup", "run", "1.99.0", "cargo", "run", "--locked", "--quiet"], work)
        run(["rustup", "run", "1.99.0", "cargo", "clippy", "--locked", "--quiet", "--", "-D", "warnings"], work)
        run(["dart", "analyze", "--fatal-infos", "src"], work)
        run(["dart", "run", "src/main.dart"], work)
    print("Generated Rust/Dart DTOs compile, round-trip and regenerate deterministically; Rust rejects unknown input fields.")


if __name__ == "__main__":
    main()
