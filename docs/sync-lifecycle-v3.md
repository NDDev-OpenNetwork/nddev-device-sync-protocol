# Sync history lifecycle

This contract defines source compatibility, not runtime availability or permission
to prune. The
existing v2 source schema, exact persisted request bodies and receipt status/body
remain unchanged. Generated DTOs describe wire shapes; Core owns version/basis,
qualified identity, lifecycle and retention/install decisions. Adapters own
current authorization, signatures, nonce, original-row storage, AEAD and commits.

## Reader before emission

First qualify readers for Operation2/3, legacy Record1/2, new Record3, Snapshot1
and Repository Snapshot2. An unsupported version/kind fails before any inbox
cursor, stage or active-state mutation. Keep emitting v2 existing kinds during
this reader rollout; do not emit RepositoryState. V2 IDs that resemble `v3:`
remain explicit legacy IDs. Merely receiving capabilities is not rollout proof.

Only after the owning cohort gates pass may the operator select new operation
version3. Freeze missing/new v2 admission before enabling version3 emission or
retention. Retained v2 originals still replay on the original v2 route with exact
body and a fresh signed nonce. A missing frozen v2 original returns existing
v2 `410 {"error":"cursor_expired"}`: upgraded clients preserve it as an Unknown
outcome and never turn it into a new operation. No v2 error enum is extended.
This activation requires one coordinated reader/emitter/storage boundary; the
contract does not perform it or advertise an automatic upgrade.

## Server writers before retention

Reader rollout is necessary but does not exclude an old server writer. The
existing V2 Server store has no F/B admission check. After a receipt is retired,
an old process can treat the original missing request as new with a fresh nonce,
creating a new log result (at least a new Conflict when revision has advanced).
A proof about the new Core path does not constrain that old SQL path.

Before V3 emission or the first receipt retirement, prove that no old writer can
commit across activation, including in-flight transactions, restarted replicas
and application-image rollback. For the existing Compose deployment this means
qualifying the reviewed NDS_IMAGE digest of nddev-sync-server, stopping/draining
all old instances and their runtime database sessions before activation, and
excluding their restart, routing and database-write access afterward. The
operator must account for every writer using that database; the Compose template
and one healthy new instance are not evidence that all other writers are gone.
Rollback to an older writer must remain excluded once retention is activated.
Source validation alone does not establish that deployment boundary.

The Server adapter owns the database-enforced writer-contract barrier and the
runtime/migrator privilege boundary. The old SQL path that omits a trusted
writer assertion must fail closed; a permissive column/session default cannot
silently authorize it. Do not infer a trusted writer version from client JSON
schema_version, basis, lifecycle, operation ID or headers. Any assertion needs a
server/SQL and privilege/deployment trust boundary. Activation serialization,
old prepared statements, already-running transactions and rollback behavior
require acceptance through the actual adapter. This wire contract grants no
database privileges and does not replace that acceptance.

Current authorization and fresh nonce checks still precede retained replay.
An authorized old known receipt may return its unchanged original status/body;
it needs no new entity/log effect. Semantic refusal may commit the consumed
nonce and authorization clock floor while leaving history unchanged. An actual transaction-aborting storage
fault rolls back the transaction, including that attempted nonce consumption.
Do not turn every error into an assumed nonce rollback. An admitted commit whose
caller loses the response retains its existing Unknown-to-caller semantics; an
ambiguous commit result is not evidence of rollback.

The owning gate must exercise an actual old Server binary/SQL path after the
activation boundary and receipt retirement. A fresh-nonce retry of a missing
retired original must be unable to commit a new operation, receipt, revision or
sequence, including after restart/rollback and attempts to forge writer-version
body fields. Also test an in-flight old transaction spanning activation, retained
exact old replay, semantic refusal versus storage-fault nonce behavior, and a
qualified new writer's forward progress under unchanged quotas. Do not enable
retirement merely because every observed test client or one new server is current.

## One canonical declaration

A new v3 request has mandatory `schema_version:3`, `basis_seq:B` and
`lifecycle:{resolved_through_seq:R}` with `R<=B`. Both operation and idempotency
IDs are immutably qualified `v3:B:suffix` within their existing length bounds.
Core checks the exact decimal prefix and the surrounding operation target. New
requests require `floor<=B<=head`. There is no admission time or expiring UUID
registry. Current owner/session/device/signature and fresh nonce checks precede
retained lookup; exact raw-body replay precedes new basis/capacity checks. A
missing old-basis request returns `410 basis_expired`, never a new Applied or
Conflict, and never an automatic replacement UUID.

Core's `VersionedOperation::aad` owns the sole tuple encoding. The deployed V2
ten-element JSON tuple is unchanged. The V3 tuple is ordered as tag, version3,
origin, tenant, owner, writer device, entity kind/id, full operation ID, base
revision, key ID, full idempotency key, B and the canonical lifecycle object.
Encryption follows metadata binding. AAD is not a device signature substitute.
Record3 rejects an inner resolution watermark. An Operation3 VaultRecord reader
requires Record3; Record1/2 remain readable only with their original Operation2
and AAD. Never rewrap retained ciphertext or treat an unverified legacy marker
or cursor as resolution authority. A new current-format VaultRecord edit may
preserve the same entity's already-Applied legacy decision after authenticating
its original payload and validating the actual stored revision and nonzero
commit sequence. Its carried R must be strictly below that legacy sequence,
which must be covered by the new basis. Core accepts this only before encryption
of a new operation; retained/dispatched originals remain immutable. Operation3
keeps the sole lifecycle declaration; Record3 has no inner marker.
Repository Snapshot2 requires Operation3 and has no basis or lifecycle field.

The first transition from a legacy Applied head may carry a historical global
watermark that is not itself a conflict sequence. Under capacity pressure,
Core permits that bounded carry below the actual previous legacy commit while
still requiring every covered retained conflict in the witness set. That carried
range cannot cover conflicts at or after the previous commit. An empty covered set cannot
invent a new decision; it only preserves the already-Applied legacy one. Once
the previous head is current-format, every increased declaration again requires
the exact meaningful observed-conflict rule. Current authorization, revision CAS,
original-row preservation and the atomic retention/capacity plan are unchanged.

Only an actual Applied result committed with its full original row grants R
authority. Later Applied writes carry a nondecreasing R. Before publication,
Core validates every retained Applied progression, including the suffix above
the selected base cut, using the same applied_projection transition guard as
readers. Admission::New answers missing-request basis eligibility; it does not
replace the actual revision/lifecycle transition check. A failed CAS/Conflict
has no resolution authority. This is an authenticated explicit owner resolution
intent; it is not evidence that the server decrypted or a person read payloads.
Producer adapters verify supported AEAD payloads and complete observed choices.

## Finite retention and full owner

A frozen base at H contains each latest full Applied as of H and all unresolved
full alternatives above that entity's committed R. Keep the entire contiguous
suffix above H. Return original request bytes and original receipt status/body;
no separate payload store or reconstruction from hashes is sufficient. Original
request/result UTF-8 byte limits remain 24KiB/2KiB, inherited from existing
storage. Core validate_original_lengths checks actual decoded bytes before
parsing/staging and in metadata planning. A JSON Schema maxLength or an encoded
string length is not a decoded-byte count; no encoding profile changes here.
Adapters must validate the original generated operation/receipt and status, then
measure the actual encoded page. A pair of valid JSON originals at both byte
caps fits one page: with maximum-width metadata, the conservative escaped JSON
page bound is 53477 bytes, below 61440. Raw SyncRow string shape alone is not
original-JSON or payload validation. Sparse base member positions are not the
inbox cursor. Pages are at most100 rows and
60KiB actually encoded, within the existing64KiB transport bound. Exact UTF-8
bodies are carried in JSON strings; adapters count bytes after decoding and
verify their generated operation/result model, sequence and supported payload.

One-wave tail is a target, not a guarantee. Apart from the bounded legacy carry
defined above, the meaningful full-owner resolver
requires a nonempty validated known-conflict witness and exactly
R=max(previous committed R, witnessed conflict sequences), with a strict raise
and complete coverage of the unresolved target alternatives through R. Empty
or overstated witness cannot grant this escape. The explicit escape may plan a resolver and the resulting keep-set under the SAME row/byte/entity caps,
then commit actual Applied, safe retirement, counters and frozen publication
atomically with `base=floor=head=S`. Every uncovered alternative remains. No
intermediate logical quota increase is allowed. Failure, CASConflict, bad proof,
space shortfall or stale guards publish nothing. The maintenance refusal itself
has no new log sequence; a prior ordinary Conflict still replays its original409.
The old base token expires in that same commit. This escape retains zero suffix
at that point and expires old retry horizons honestly. Real PG physical/MVCC/WAL
workspace and concurrency still need qualification. Mandatory data that cannot
fit remains blocked. History cleanup never frees the4096 entity-identity limit.

## Client install

A staged complete old H may install only as partial and only when its contiguous
tail covers the maximum locally known committed sequence, including direct ACKs
that did not advance inbox cursor. One existing storage-owner transaction checks
original scope/key/LocalUseFence, cursor/local revision, stage completeness and
space. Preserve exact outbox bytes, dispatched/Unknown/predecessor families and
all uncovered full local alternatives. Omission from a snapshot does not settle
pending work. Installation leaves `caught_up=false`; normal delta/freshness
checks establish later progress. Stage admission survives caller cancellation
until the real storage transaction completes. No empty reseed or automatic
unsent requalification is introduced by this boundary.
