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

Protocol source alpha.15 adds the closed error code `sync_capacity_exhausted`.
Retained operation, byte or entity capacity rejects new writes with `409` and no
`Retry-After`; exact authorized replay still returns its original result. Clients
preserve pending request bytes and stop automatic replica retries until an
explicit manual retry or capacity remedy. Expiring admission pressure remains
`503 server_busy` with bounded retries. Generated consumers must update together
at this source boundary: alpha.14 consumers reject the new enum. The current v2
request does not negotiate a minimum protocol source release; coordinated active
consumer rollout is required before enabling this response.

The current server retains history and idempotency receipts up to its explicit
capacity limits; it does not implement history compaction or fresh-state
checkpoints. A future retention implementation must return `410 cursor_expired`
for a cursor below its retained floor and preserve pending local work during
verified fresh-state synchronization. Idempotency entries must outlive the
supported retry horizon; expired operations must never be silently admitted as
new. Define that horizon and recovery contract before implementing pruning.

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

Client traces use OTLP protobuf ExportTraceServiceRequest at the explicit signed
`/v2/observability/traces` endpoint. A batch contains at most 32 actual spans /
64 KiB. The SDK projects only module/scope and canonical HTTP attributes, valid
trace/span IDs, timing, kind and redacted status. Events, links, tracestate,
exception prose and arbitrary resource/scope metadata are excluded. Timestamps
are admitted within 24 hours, with at most five minutes of future skew. The
server attaches authenticated ownership and forwards to its operator-owned
collector. Trace retries may duplicate spans; no durable/exactly-once guarantee.

For an enabled trace receipt, `duplicates` is zero and `accepted` is the number
of spans accepted by the receiver, from zero through the original batch count.
An OTLP warning with zero rejected spans acknowledges the full batch. A valid
partial-success response settles the entire batch once: accepted spans count as
delivered to the receiver and the remainder as dropped. The sender must not
retry that batch. Receiver text is neither returned nor logged. Malformed
responses, negative counts and counts exceeding the batch are not receipts.
If local settlement fails while the receipt remains known, retry settlement
without retransmitting the batch. A crash before durable settlement retains
the existing delivery uncertainty; this does not establish exactly-once export.
Event receipts retain their full-count requirement: `accepted + duplicates`
must equal the number of submitted events. Disabled mode retains its existing
opt-out behavior; it does not claim delivery.

Alpha.16 clarifies these trace-specific count semantics without adding wire
fields. Earlier NDS senders require a full count and can retry a partial receipt.
Qualify compatible native and browser senders before activating a server that
returns partial counts; a successful source build alone does not meet this gate.

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

## Owned RDS control (source alpha.17)

`contracts/v2/screen.schema.json` adds seven fixed `/v2/rds` operations for the
Core `ScreenStore` boundary. Use the existing owner session AND enrolled-device
HTTP signature for every operation, including reads and end. Browser callers
use the existing exact-origin cookie adapter AND device signature. Consume a
fresh nonce under the same canonical authorization/revocation transaction before
replay or result delivery. No body-supplied owner or device public key authenticates
a caller. All responses remain `Cache-Control: no-store`.

| Method and path | Actor and result |
| --- | --- |
| `GET /v2/rds/bindings/{device_id}` | Current signed device; target must be active and same-owner. Required `binding:null` means no screen binding. |
| `POST /v2/rds/bindings` | Bind the signing device after NDS authority and endpoint PoP; return its canonical current binding. |
| `POST /v2/rds/views` | Signing viewer creates a finite intent for an active same-owner host, using both exact current binding revisions. Authorized exact replay returns 201 with the original immutable fields and current state, including retained Ended. |
| `GET /v2/rds/views/incoming` | Signed host sees at most one participant intent, or required `view:null`. |
| `GET /v2/rds/views/{view_id}` | Signed viewer receives the public projection and required nullable Rust-only native artifact. Only Ready has an artifact. |
| `POST /v2/rds/views/{view_id}/ready` | Signed host stores the exact bounded artifact after current rechecks; Ready says nothing about pixels or presentation. |
| `POST /v2/rds/views/{view_id}/end` | Current owner of the intent AND signed active enrolled viewer/host participant; exact empty request and 204 response. |

GET and end requests have exact empty content, still covered by Content-Digest.
A third same-owner device is not an end participant. End does not require a live
native grant, live original viewer session or matching old binding. While the
intent row is retained, repeated end of an expired/Ended intent succeeds after
current owner/participant checks. After expiry cleanup, an absent or unowned id
returns the same `authorization_denied`; no indefinite end receipt is retained.
Local resources close immediately on known logout/revocation/end even if HTTP fails.

Binding uses a distinct Accounts-owned purpose key, never a legacy native key
store, issuer or allowlist. Generate a non-nil UUID once per endpoint instance;
retries retain it, while a new instance uses a new UUID even with the same key.
The body nonce and `expires_at_ms` equal the actual Signature-Input nonce and
expiry (Unix seconds multiplied by 1000); endpoint proof validity is at most
60 seconds and cannot exceed the current NDS session. Decode canonical PublicKey
and Signature before strict Ed25519 verification; reject noncanonical/weak keys.
Core defines the exact endpoint transcript: `NDS-RDS-ENDPOINT-BINDING-V2\0`,
u16 big-endian origin length + configured ASCII origin, u16 device-id length +
the signing device id, 32 endpoint-key bytes, 16 instance UUID bytes, u64
original base revision, u16 nonce length + exact nonce, u64 expiry milliseconds.
The configured canonical origin comes from server configuration, never the body.

Binding retry is the explicit exception to generic identical-body idempotency:
its fresh nonce/expiry/PoP changes bytes. After BOTH current NDS and endpoint proofs,
exact current UUID/key/original base (`current.revision - 1`) returns the same row
and revision without retiring intents. A different UUID must CAS current revision
and advances it even with the same key. Changed key/base under the same UUID or
a superseded registration's original base is denied (`403 authorization_denied`). Only the current binding row
holds this identity; no historical receipt/instance registry or new counter exists.

Create instead retains the exact original UTF-8 request fingerprint, idempotency
key, unique view id (at most 64 bytes), participants, profile, original admission
and expiry atomically. Recheck current owner/session/device/bindings and the
original requester session even on replay. Lifetime is at most 300000ms, max fps
1..60 and output height 16..1080. The requested expiry is validated first, then
the accepted whole-second boundary is explicitly returned. Public timestamps
use exact JSON-safe Unix milliseconds and survive expired reconstruction. Replaying
an old intent never renews, resurrects or reopens capture. An authorized exact
create replay after early End returns `201` with the same view id, original
profile/admission/expiry and current `ended` state. It is terminal metadata, not
new authority; it allocates no slot or grant and cannot become Ready again.
Participant slots are
bounded to one view; no list, paging, cache or registry API is added. Intent rows
and idempotency receipts share the original expiry as their retention horizon.
Early end frees the participant slot but retains the receipt until that boundary.
Cleanup uses the persisted authorization clock floor in the same transaction.
A storage admission limit rejects only new creates, never retained exact replay,
end or revocation. Occupied participant slots and full admission return
`503 server_busy`; mismatched create/Ready replay or a new/activating request
rejected for closed/expired state returns `409 operation_conflict`. The retained
exact create replay described above remains `201 ended`. Current binding or participant authority loss
returns `403 authorization_denied`. Expiry closes the replay horizon; a new view
requires a fresh request and a new server-created id, never renewal of an expired
request.

Incoming, ready and viewer delivery recheck both active participant devices,
exact current bindings and the original viewer session reference. That reference
is a server-only digest, absent from the public projection. Ready replay retains
the exact original artifact. A native artifact is canonical unpadded base64url of
1..8192 decoded bytes (at most 10923 characters), marked `x-sensitive`. Decode
with that bound and canonical re-encode equality. Keep it in Rust control I/O;
never Dart/Flutter, URLs, logs, synchronization or telemetry. The server stores
opaque bytes, not native permission. RDS verifies the real native signature,
issuer/subject/audience/expiry, unique view id as native tenant, exact host binding
revision, selected display and DesktopView-only scope; no control/other service.

The local host separately requires explicit opt-in, current Accounts LocalUseFence
and actual platform source access before key/capture use. Metadata, restored
Ready or a cached route cannot satisfy these guards. Endpoint public-key bytes
already form the native EndpointId; existing configured native discovery/relay
routing supplies addresses. This contract adds no locator, display inventory,
capability/consent flags, stored private keys, frames, sequence or per-frame receipts.
HTTP signature semantics and the signatures crate version remain unchanged.
Schema/DTO checks do not prove the consuming Server SQL/native I/O, Accounts
protected storage or shared Flutter presentation acceptance.
