# Storage and data-integrity decisions

These decisions implement the supplied Prototype 3 prompt's DDD references. The DDD
PDF and team briefing were not available as source files in this generation workspace;
their page references below come from the implementation prompt, not an independent
review. No SRS IDs or team-completion percentage are invented.

1. **History, DDD pp. 23 and 33:** `GET /history/runs` returns bounded RunSummary
   pages with an opaque keyset cursor over created_at plus ID. It excludes prompt,
   response, rubric evidence, and full configuration. Full details use `GET /runs/{id}`.
   The legacy `GET /runs` bare-array compatibility path remains.
2. **Strict import, DDD p. 23:** schema 4.0 preserves source business identifiers and
   rejects an existing run ID atomically. Evidence is never upserted or overwritten.
   Exact existing test-version definitions may be reused; conflicting versions fail.
   Suite/execution/preview identity collisions fail. Optional copy mode is not included.
3. **Ownership:** Pranjal authors test/suite/execution/model/preview HTTP contracts.
   Omar supplies internal inputs, returns, transactions, domain errors, and integrity.
   The historical p3.1 JSON/API proposal is not a binding contract or version bump.
4. **Approval:** approving a draft creates a new approved immutable version, with
   server attribution. Earlier versions remain unchanged. Historical approval/ownership
   stays unknown where it was never recorded.
5. **Snapshots:** suites pin exact versions and contiguous 1-based positions; repeated
   versions at different positions are allowed. Reservation freezes version/profile
   membership and all pending IDs in one transaction before model requests.
6. **Lifecycle:** claim/checkpoint/finalize are separate committed transactions.
   Expired work is preserved as failed/interrupted, never silently retried. Reruns use
   new IDs, retain original evidence/reviews, and start with no new human reviews.
7. **Scoring:** selected maxima are Decimal/NUMERIC, positive, total 100.00. Historical
   score means awarded criterion points divided by 100. Unknown maxima/ratios stay
   unknown. Zero is valid; incomplete evaluation has no total; no suite/global pass/fail.
8. **Roles and metrics:** assistant, target, judge, and reviewer are separate. Target
   and evaluation timing/usage are captured separately; old latency retains its meaning.
   Configured aliases, endpoint/profile identities, and reported models remain distinct.
9. **Access:** one server-configured shared prototype workspace, authorized subjects,
   server reviewer identity, verified RS256 OIDC in shared mode. Development identity is
   explicit and fails closed outside development. Browser login remains Pranjal's work.
10. **Transfer attribution:** business IDs remain stable. Database surrogate version
    and review IDs are local. Source review ID, reviewer attribution, source, bundle
    hash, and authenticated importer remain separately available in review attribution.
    Imported historical evaluator definitions are readable without being executable.
