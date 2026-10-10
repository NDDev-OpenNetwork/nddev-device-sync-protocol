use ed25519_dalek::{Signer, SigningKey as NativeKey};
use nddev_device_sync_http_signatures::*;
struct Key(NativeKey);
impl SigningKey for Key {
    fn sign(&self, data: &[u8]) -> HttpSigResult<Vec<u8>> {
        Ok(self.0.sign(data).to_bytes().to_vec())
    }
    fn key_id(&self) -> String {
        "d".repeat(43)
    }
    fn alg(&self) -> AlgorithmName {
        AlgorithmName::Ed25519
    }
}
impl VerifyingKey for Key {
    fn verify(&self, data: &[u8], signature: &[u8]) -> HttpSigResult<()> {
        let signature = ed25519_dalek::Signature::from_slice(signature)
            .map_err(|_| HttpSigError::InvalidSignature("invalid".into()))?;
        self.0
            .verifying_key()
            .verify_strict(data, &signature)
            .map_err(|_| HttpSigError::InvalidSignature("invalid".into()))
    }
    fn key_id(&self) -> String {
        SigningKey::key_id(self)
    }
    fn alg(&self) -> AlgorithmName {
        AlgorithmName::Ed25519
    }
}

#[test]
fn real_ed25519_signature_binds_exact_bytes_method_origin_query_and_device() {
    let key = Key(NativeKey::from_bytes(&[7; 32]));
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs();
    let target = "https://instance.example/v2/sync/operations?after_seq=7";
    let headers = sign(
        "POST",
        target,
        b"{\"operation\":1}",
        &key,
        &"n".repeat(43),
        now,
    )
    .unwrap();
    assert_eq!(device_id(&headers, now).unwrap(), SigningKey::key_id(&key));
    assert_eq!(
        verify("POST", target, b"{\"operation\":1}", &headers, &key, now)
            .unwrap()
            .nonce,
        "n".repeat(43)
    );
    for (method, target, body) in [
        ("GET", target, b"{\"operation\":1}".as_slice()),
        (
            "POST",
            "https://other.example/v2/sync/operations?after_seq=7",
            b"{\"operation\":1}".as_slice(),
        ),
        (
            "POST",
            "https://instance.example/v2/sync/operations?after_seq=8",
            b"{\"operation\":1}".as_slice(),
        ),
        ("POST", target, b"{ \"operation\":1}".as_slice()),
    ] {
        assert!(verify(method, target, body, &headers, &key, now).is_err());
    }
    assert!(
        verify(
            "POST",
            target,
            b"{\"operation\":1}",
            &headers,
            &Key(NativeKey::from_bytes(&[8; 32])),
            now
        )
        .is_err()
    );
    assert!(
        verify(
            "POST",
            target,
            b"{\"operation\":1}",
            &headers,
            &key,
            now + 60
        )
        .is_err()
    );
}

#[test]
fn structured_fields_cannot_smuggle_parameters_duplicates_or_wrong_component_order() {
    let key = Key(NativeKey::from_bytes(&[7; 32]));
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs();
    let valid = sign(
        "GET",
        "https://instance.example/v2/sync/operations",
        b"",
        &key,
        &"n".repeat(43),
        now,
    )
    .unwrap();
    for input in [
        valid.signature_input.clone() + ";unexpected=\"ignored\"",
        valid.signature_input.clone() + ";created=0",
        valid.signature_input.clone() + ", " + &valid.signature_input,
        valid
            .signature_input
            .replace("\"@method\" \"@target-uri\"", "\"@target-uri\" \"@method\""),
        valid.signature_input.replace("ed25519", "hmac-sha256"),
        valid
            .signature_input
            .replace(&format!("created={now}"), "created=-1"),
    ] {
        let headers = Headers {
            signature: valid.signature.clone(),
            signature_input: input,
            content_digest: valid.content_digest.clone(),
        };
        assert!(device_id(&headers, now).is_err());
    }
}
