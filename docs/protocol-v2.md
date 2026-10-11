# Control-plane v2

`openapi/control-plane-v2.yaml` and `contracts/v2/control-plane.schema.json`
define the versioned wire boundary. Schemas do not advertise runtime availability;
that is owned by adapters, authentication discovery and platform qualification.
Published source locks keep their original meaning.

## Identity and enrollment

Email OTP, GitHub and passkeys issue the same opaque, expiring owner session.
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

## Authenticated client observability

The public control plane requires both the owner session and the enrolled device
signature for events, native traces, status and incident actions. Ingest/admin
credentials stay behind this boundary. Requests cannot choose a collector or
claim another tenant/user/device; the server supplies authenticated ownership.

Event batches are at most 32 records / 64 KiB, using the closed event schema.
The server namespaces producer instance IDs by owner and device. Replays retain
identical bytes and sequence with a fresh signature; collector deduplication is
finite (one hour). A receipt records admission and the export mode, not durable
or searchable delivery. Disabled mode stops new export and is visible to clients.

Native traces use OTLP protobuf ExportTraceServiceRequest at the explicit signed
`/v2/observability/traces` endpoint. A batch contains at most 32 actual spans /
64 KiB. The SDK projects only module/scope and canonical HTTP attributes, valid
trace/span IDs, timing, kind and redacted status. Events, links, tracestate,
exception prose and arbitrary resource/scope metadata are excluded. Timestamps
are admitted within 24 hours, with at most five minutes of future skew. The
server attaches authenticated ownership and forwards to its operator-owned
collector. Trace retries may duplicate spans; no durable/exactly-once guarantee.

The client owns one bounded batch per signal, finite backoff and 30-minute
retention. Cancellation/expiry/opt-out must account for undelivered records.
Telemetry transport and its native credential reads stay outside both export
feeds while retaining local diagnostics. Backgrounding pauses network export;
resuming rechecks operator policy. Sign-out closes the account-specific feeds.
Incident actions preserve operation_id/body across uncertain retries and use
revision checks; list pages remain bounded and expose their generation time.

## Passkey lifecycle

Authenticated owners can list bounded public credential fingerprints and creation
times. A valid session that is too old for a credential-management action receives
`403 recent_authentication_required`; this does not revoke ordinary session/vault
authorization. The owner can use any supported sign-in method to reverify. Removing a passkey requires a session authenticated within five minutes,
rechecked in the same transaction as deletion. Its issued sessions are revoked
atomically. Legacy passkey sessions without credential linkage are revoked on a
credential removal because their issuing credential cannot be proven. The
response states whether the current session was revoked and whether passkey sign-in remains available; no fallible follow-up
read may turn a committed removal into an apparent failed mutation. Device and
vault keys remain separate and unchanged. A deleted credential cannot finish an
outstanding authentication exchange or create another session.

## Browser adapter

The Flutter web client uses the same operation, encryption, revision and device
proof contracts as native clients. `web` identifies a browser installation;
it does not advertise native tool execution.

`GET /v2/browser` discovers the configured same-origin adapter. Application
requests select it with the single header `X-NDS-Client: browser`. The server
rejects a concurrent Authorization header, foreign/ambiguous Origin and cross-site
fetch metadata. Mutations require the exact configured public origin. The custom
header and absence of CORS prevent cross-origin simple-request CSRF; device
signatures remain separately required for signed operations.

Email verification and GitHub/passkey exchange return `BrowserSessionIssued`
and set `__Host-nds-session` with Secure, HttpOnly, SameSite=Strict, Path=/ and no
Domain. The cookie lifetime cannot exceed the issued session. Native requests
retain their existing `SessionIssued` bearer response. Successful sign-out or
known invalid authentication clears the browser cookie. API/identity/vault
responses are never cached by the application service worker.

Offline access is a protected local observation under ADR 0007, bounded by the
existing session expiry; it is not a request authorization credential. Reconnect
revalidates the session/device before sending pending operations. Local sign-out
invalidates offline access even when remote revocation cannot yet complete.
