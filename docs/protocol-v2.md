# Planned control-plane v2

`openapi/control-plane-v2.yaml` and `contracts/v2/control-plane.schema.json`
define the next implementation boundary. Every v2 operation is explicitly
`planned`; no current server route, usable login or sync behavior is claimed.
An implementation adopts a versioned source release and proves its acceptance.

## Identity and enrollment

Email OTP and GitHub both issue the same opaque, expiring owner session.
`/auth/methods` derives availability from usable runtime configuration and
provider readiness; an enabled flag alone is insufficient. Availability is not
proof of mailbox delivery. The operator privately configures the owner email
and stable GitHub subject. Matching emails never implicitly link accounts.
The initiating app may send `Accept-Language: en` or `ru` on email challenge
requests and GitHub start; English is the default. The selected locale is bound
to the email/flow for browser approval copy, while wire keys and error IDs remain
English. Unknown-flow browser failures use an appropriate supported fallback.

Email challenge responses are indistinguishable for permitted and other
addresses. Use eight-digit codes, at most ten-minute challenges, finite attempts
and resend limits. Resend invalidates the old challenge; success consumes it
atomically. Use case/storage limits supplement schema validation.

GitHub start returns an app-held exchange token and browser authorization URL.
The server retains S256 PKCE verifier and state, bound to that flow and its fixed
callback. It verifies the provider identity against the configured stable subject.
The initiating app exchanges its flow/token through the bounded polling endpoint;
only one successful exchange issues a session. Provider success first enters
`AwaitingApproval`, not an exchangeable state. The app and browser display the
same eight-digit `verification_code`, a comparison hint rather than an email OTP
or bearer credential. The browser requires an explicit Approve/Deny POST bound
to its `__Host-nds-approval` cookie and one-use CSRF token; both are flow-bound
and expire with the flow. The cookie is Secure, HttpOnly, SameSite=Strict,
Path=/, with no Domain. Denial is terminal; approval alone enables exchange.
Clear the cookie on either terminal decision. This explicit consent step does
not make email or GitHub login phishing-resistant.

The callback page and URLs never contain an NDS session token, email OTP or PKCE
verifier. The page may contain its comparison code and hidden CSRF token.
Provider callback codes/state
are sensitive query values and must be excluded from logs. Maximum flow lifetime
is ten minutes; the returned polling delay is mandatory.

Device keys are Ed25519, encoded as canonical unpadded base64url. Enrollment
binds the key, metadata, generated device ID and challenge to the authenticated
owner. The device signs the bytes `NDS-ENROLLMENT-V2\0` followed by the decoded
32-byte server challenge. Proof submission requires the same owner session.
Consume the challenge atomically within five minutes. Reject noncanonical
encodings and wrong byte lengths even when the structural schema accepts them.
Device enrollment and email/GitHub login do not reconstruct existing vault keys.

## Signed operations

Use [RFC 9421 HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421)
and [RFC 9530 Content-Digest](https://www.rfc-editor.org/rfc/rfc9530), not bearer
public keys or a custom concatenation of request fields. The `nds` signature
covers `@method`, `@target-uri` and `content-digest`. Include `alg="ed25519"`,
`keyid` equal to the registered device ID, `created`, `expires` and a random
nonce of 16..128 base64url characters. `Content-Digest` uses `sha-256` over the
exact request content, including the empty content of GET requests.

Use the configured public origin to validate the absolute target URI; signed
query parameters, method and content must survive transport unchanged. Accept
at most 60 seconds of future clock skew and a signature lifetime no longer than
300 seconds. Reject expired signatures. Retain consumed `(device_id, nonce)`
entries through signature expiry, within explicit capacity bounds. Retry an
operation with a fresh signature/nonce and the original persisted request bytes.
Check revocation and owner scope before serving even an idempotent replay.

## Idempotency, revisions and limits

The idempotency key is scoped to `(tenant_id, user_id, device_id)`, derived from
authenticated server context. Store the SHA-256 fingerprint of the exact UTF-8
request body alongside its original HTTP status and response. A retry uses the
identical body, not merely an equivalent JSON reserialization. A reused key with
different bytes is `409 idempotency_conflict`. The operation ID is unique within
the same owner/device scope; it cannot be reused to evade idempotency checks.

Validate `schema_version=2` and the owning entity payload schema before commit;
unknown entity types are rejected. Entity update, revision, operation and original
result commit atomically. Conflicts retain both revisions and unresolved state.
Concurrent duplicate requests receive the original status/body. Server sequence
allocation follows committed order; allocating an ordinary database sequence
before commit is insufficient. Cursor reads are scoped to the authenticated owner.

All wire counters are integers in `0..9007199254740991`, preserving exact JSON
representation across supported tools and clients. HTTP bodies are at most
65536 UTF-8 bytes and 32 nesting levels; collection pages contain at most 100
items. The schema is structural: body size, signature verification, monotonicity,
ownership and entity-specific invariants remain executable adapter/use-case gates.

Retention is an explicit deployment policy: cursors older than retained history
return `410 cursor_expired`, requiring explicit fresh-state synchronization.
Idempotency entries must outlive the supported retry horizon; expired operations
must not be silently admitted as new. Define that horizon before implementing
pruning. No backups, recovery copies or hidden last-write-wins behavior is added.
