# Deployment, operation, recovery and cost inputs

## Topology and status

The package provides a proposed small Azure topology: one non-root container serving
built React assets and FastAPI, Azure Container Apps, a private PostgreSQL 16 Flexible
Server, Basic ACR with admin credentials disabled, Key Vault secret references,
separate runtime/migration managed identities, and a controlled migration job.

The Docker build and Bicep compilation are local checks. They do not prove resource
availability, RBAC propagation, DNS, private network routing, shared OIDC/browser login,
or live provider connectivity. Nothing was provisioned, pushed, or deployed to Azure.
Subscription/region/approved hosting constraints remain external inputs.

Official sources consulted during generation:

- [Container Apps scaling](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
- [Container Apps API 2025-01-01](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-01-01/containerapps)
- [PostgreSQL Flexible Server API 2025-08-01](https://learn.microsoft.com/en-us/azure/templates/microsoft.dbforpostgresql/2025-08-01/flexibleservers)
- [Private PostgreSQL networking](https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private)
- [Managed identity image pulls](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull)
- [Container Apps secret management](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
- [Container Apps jobs](https://learn.microsoft.com/en-us/azure/container-apps/jobs)

API versions are pinned in source. Compilation verifies the resource schema, while
the intended Azure subscription must still accept those resources and settings.

## Prepare deployment parameters privately

Use Azure CLI/Bicep with access to the approved subscription and an existing approved
resource group. The operator requires deployment, role-assignment, ACR build, Key
Vault, Container Apps, networking, and PostgreSQL permissions. Register the relevant
resource providers through the subscription administrator as needed.

Copy `deployment/parameters.example.json` and
`deployment/application.parameters.example.json` **outside the repository**. Add
secure `administratorPassword` and `appDatabasePassword` parameters only to the
private infrastructure file. Supply reviewed OIDC issuer/audience/JWKS and authorized
subject values in the private application file. Prefix and location must match both.
Keep passwords private; do not pass them as command-line literals or paste into chat.

Confirm regional PostgreSQL SKU availability and Container Apps capacity/quotas:

```powershell
az postgres flexible-server list-skus --location APPROVED_REGION --subscription APPROVED_SUBSCRIPTION
az deployment group what-if --subscription APPROVED_SUBSCRIPTION --resource-group APPROVED_GROUP --template-file deployment/main.bicep --parameters '@C:\private\p3-infrastructure.parameters.json'
```

After review and explicit authorization to incur resource charges, the operator can run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\deployment\Deploy-P3.ps1' `
  -SubscriptionId 'APPROVED_SUBSCRIPTION' -ResourceGroup 'APPROVED_GROUP' `
  -InfrastructureParametersPath 'C:\private\p3-infrastructure.parameters.json' `
  -ApplicationParametersPath 'C:\private\p3-application.parameters.json' `
  -ImageTag 'REVIEWED_COMMIT_OR_UNIQUE_RELEASE_TAG'
```

The script compiles, deploys infrastructure, builds the image in ACR, deploys a manual
migration job, waits for its success, then deploys the web revision. It stops on a failed
stage. The image tag must be immutable by operating convention; record the resulting
image digest in the release log. A repeated tag should not replace an approved release.
Role propagation can delay job/image/secret access; diagnose that stage and retry
deliberately rather than bypassing authentication or adding public database firewall rules.

## Database privileges and migration order

`app.storage.bootstrap_database` runs only in the explicit migration job. It creates
the runtime login, applies the secret password, and grants database/schema usage.
Alembic runs with the migration login, then a final grant phase enables runtime DML
and sequence use. The runtime does not own schema objects or receive DELETE/DDL grants.
The runtime identity can retrieve only its database-url secret; the separate migration
identity retrieves deployment database credentials. Both identities can pull the image.

The database is delegated into its private subnet and has public access disabled.
Container Apps uses a separate subnet and linked private DNS. The connection requires
TLS. Key Vault uses its public HTTPS endpoint with RBAC; public network reachability
is not anonymous secret access. If approved policy requires a Key Vault private endpoint,
add that network configuration and validate managed secret resolution before deployment.
Do not expose model credentials in browser environment variables. Live provider secrets
and trusted profile configuration must be added to server-managed configuration by
Pranjal/operator; the initial template intentionally starts with the explicit demo provider.

The web app runs one worker, minReplicas=1/maxReplicas=1, single active revision.
Database claims still protect against maintenance/rollout overlap. In-process work is
not durable merely because replicas are limited. Pranjal must implement the heartbeat
and recovery policy around the delivered lease operations. Never use scale-to-zero
while his in-process coordinator owns work.

## Operational signals

- `/health`: liveness, no database/model calls.
- `/ready`: verifies database connectivity, the expected Alembic head, and shared auth
  configuration; returns 503 on failure. It does not prove live OIDC/provider connectivity.
- Default HTTP access logs are disabled in supplied startup commands. Application
  operation logs include generated request IDs, route templates/stages, status and
  elapsed time. Raw query strings, prompts, responses, rationale, credentials, tokens,
  provider exception bodies and SQL parameters are excluded by default.
- Model responses render as React text. No generated HTML execution is introduced.
- Provider calls have a bounded timeout. Missing usage stays null. Target/evaluation
  metrics are separate additions; historical durations are not retroactively renamed.

## Backup, restore and rollback

Local byte-safe PowerShell backup and fresh-database restore commands are in
`PROTOTYPE3_LOCAL_SETUP.md`. Test restoration separately; keep backups access-controlled
and out of Git/packages. JSON evidence transfer is useful for selective interchange;
it does not replace a PostgreSQL disaster-recovery backup.

Azure defaults request seven-day server backup retention and no geo-redundant backup.
The final recovery point/time objectives, backup retention, export destination, encryption
and restore drill schedule require sponsor/operator agreement. Use Flexible Server's
point-in-time restore into a **new server**, verify evidence/schema/auth access, then
change the application secret to the restored destination during a controlled cutover.
Never test recovery by overwriting the only authoritative server.

Before upgrades: back up, record image digest and Alembic revision, inspect migration
compatibility, pause new acceptance if necessary, and let live claims finish or expire
under the documented coordinator policy. P3 migration is forward-only. For application
rollback, redeploy a previous schema-compatible image; for incompatible database
rollback, restore the verified backup/new server and replay only audited evidence.
Container Apps secret changes require a new revision/restart to become effective.

## Cost assumptions, not a quote

The approximately $100/month goal is **not verified**. Official pricing pages consulted
do not provide a subscription-specific regional quote in this environment. Validate:
[Container Apps pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/),
[PostgreSQL pricing](https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/),
and the [Azure calculator](https://azure.microsoft.com/en-us/pricing/calculator/).

| Component | Calculation input |
|---|---|
| Web/API | One replica, 0.5 vCPU/1 GiB, 730 hours/month. Separate active/idle seconds and request volume; apply eligible free grants only after checking the subscription. |
| Migration jobs/builds | Bounded deployment frequency, job vCPU/GiB seconds, ACR task build minutes. |
| PostgreSQL | One regional Standard_B1ms Burstable server, 730 hours, 32 GiB storage; verify availability/performance and billed storage/backup rates. |
| Registry | Basic ACR base charge, image storage and build operations. |
| Logging | 30-day retention, configured 0.1 GiB/day ingestion cap; verify plan minimums, cap behavior and billable retained/queried data. |
| Networking | VNet integration, private DNS zones/queries, regional/Internet egress, optional private endpoints/VPN, and any environment/network plan charges. |
| Secrets/identity | Key Vault operations; separate runtime/migration identities and RBAC. |
| Backup/recovery | Backup storage beyond allowance, retained dumps, restore drills, additional recovery servers while testing. |
| Model usage | Target + assistant + judge + preview calls, input/output tokens, failures/retries; bounded live-test budget separately approved. |

Compute monthly total as the sum of those regional unit prices times measured units,
including uptime, taxes/offer terms as applicable. Do not present a made-up regional
price or assume the infrastructure alone includes LLM usage. Revisit database SKU,
log volume and uptime only after measuring the agreed workload and recovery needs.
