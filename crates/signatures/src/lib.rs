//! NDS's bounded RFC9421/RFC9530 profile. The maintained parser/base builder
//! owns structured fields and canonical signature bytes. Adapters own keys,
//! authentication, nonce consumption, the public origin and network I/O.
use base64::{Engine, engine::general_purpose::STANDARD};
pub use httpsig::prelude::{AlgorithmName, HttpSigError, HttpSigResult, SigningKey, VerifyingKey};
use httpsig::prelude::{message_component::*, *};
use sha2::{Digest, Sha256};

#[derive(Debug, thiserror::Error)]
#[error("invalid_message_signature")]
pub struct Error;

pub struct Headers {
    pub signature: String,
    pub signature_input: String,
    pub content_digest: String,
}
pub struct Verified {
    pub device_id: String,
    pub nonce: String,
    pub expires: u64,
}

const COMPONENTS: [&str; 3] = ["@method", "@target-uri", "content-digest"];
fn ids() -> Result<Vec<HttpMessageComponentId>, Error> {
    COMPONENTS
        .iter()
        .map(|value| HttpMessageComponentId::try_from(*value).map_err(|_| Error))
        .collect()
}
fn opaque(value: &str, min: usize) -> bool {
    (min..=128).contains(&value.len())
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"_-".contains(&byte))
}
pub fn content_digest(body: &[u8]) -> String {
    format!("sha-256=:{}:", STANDARD.encode(Sha256::digest(body)))
}
fn base(
    method: &str,
    target: &str,
    digest: &str,
    params: &HttpSignatureParams,
) -> Result<HttpSignatureBase, Error> {
    if !matches!(method, "GET" | "POST")
        || target.len() > 2048
        || target.bytes().any(|byte| byte.is_ascii_control())
    {
        return Err(Error);
    }
    let values = [method.to_owned(), target.to_owned(), digest.to_owned()];
    let components = ids()?
        .iter()
        .zip(values)
        .map(|(id, value)| HttpMessageComponent::try_from((id, &[value][..])).map_err(|_| Error))
        .collect::<Result<Vec<_>, _>>()?;
    HttpSignatureBase::try_new(&components, params).map_err(|_| Error)
}
pub fn sign(
    method: &str,
    target: &str,
    body: &[u8],
    key: &impl SigningKey,
    nonce: &str,
    now: u64,
) -> Result<Headers, Error> {
    if !opaque(&key.key_id(), 43) || !opaque(nonce, 16) || key.alg() != AlgorithmName::Ed25519 {
        return Err(Error);
    }
    let digest = content_digest(body);
    let mut params = HttpSignatureParams {
        covered_components: ids()?,
        ..Default::default()
    };
    params
        .set_created(now)
        .set_expires(now.checked_add(60).ok_or(Error)?)
        .set_nonce(nonce)
        .set_key_info(key);
    let headers = base(method, target, &digest, &params)?
        .build_signature_headers(key, Some("nds"))
        .map_err(|_| Error)?;
    Ok(Headers {
        signature: headers.signature_header_value(),
        signature_input: headers.signature_input_header_value(),
        content_digest: digest,
    })
}

fn parse(headers: &Headers, now: u64) -> Result<HttpSignatureHeaders, Error> {
    if headers.signature.len() > 256
        || headers.signature_input.len() > 1024
        || headers.content_digest.len() > 64
    {
        return Err(Error);
    }
    let mut parsed = HttpSignatureHeaders::try_parse(&headers.signature, &headers.signature_input)
        .map_err(|_| Error)?;
    if parsed.len() != 1 {
        return Err(Error);
    }
    let parsed = parsed.shift_remove("nds").ok_or(Error)?;
    // Require the published canonical profile. This also rejects duplicate SFV
    // dictionary keys, unsupported parameters and alternate ambiguous encodings.
    if parsed.signature_header_value() != headers.signature
        || parsed.signature_input_header_value() != headers.signature_input
    {
        return Err(Error);
    }
    let params = parsed.signature_params();
    let (created, expires, nonce, keyid) = (
        params.created.ok_or(Error)?,
        params.expires.ok_or(Error)?,
        params.nonce.as_deref().ok_or(Error)?,
        params.keyid.as_deref().ok_or(Error)?,
    );
    if params.covered_components != ids()?
        || params.alg.as_deref() != Some("ed25519")
        || params.tag.is_some()
        || !opaque(nonce, 16)
        || !opaque(keyid, 43)
        || created > now.saturating_add(60)
        || expires <= now
        || expires <= created
        || expires - created > 300
    {
        return Err(Error);
    }
    Ok(parsed)
}

/// Untrusted key selector only. Ownership/revocation must be checked before use.
pub fn device_id(headers: &Headers, now: u64) -> Result<String, Error> {
    parse(headers, now)?
        .signature_params()
        .keyid
        .clone()
        .ok_or(Error)
}
pub fn verify(
    method: &str,
    target: &str,
    body: &[u8],
    headers: &Headers,
    key: &impl VerifyingKey,
    now: u64,
) -> Result<Verified, Error> {
    let parsed = parse(headers, now)?;
    let params = parsed.signature_params();
    if params.keyid.as_deref() != Some(key.key_id().as_str())
        || key.alg() != AlgorithmName::Ed25519
        || content_digest(body) != headers.content_digest
    {
        return Err(Error);
    }
    base(method, target, &headers.content_digest, params)?
        .verify_signature_headers(key, &parsed)
        .map_err(|_| Error)?;
    Ok(Verified {
        device_id: key.key_id(),
        nonce: params.nonce.clone().ok_or(Error)?,
        expires: params.expires.ok_or(Error)?,
    })
}
