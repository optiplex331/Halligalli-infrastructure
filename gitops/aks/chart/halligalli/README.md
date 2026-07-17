# Halligalli Paired Runtime Chart

This Infrastructure-owned chart renders the AKS Deployment Target runtime: two Web
Pods, two single-worker FastAPI Pods, and one ephemeral Redis Pod. It is selected
by the `halligalli` Argo CD Application and deliberately contains no generic
runtime, scheduling, annotation, or secret-injection knobs.

## Fixed Runtime Contract

- Web and API are two-replica RollingUpdate Deployments with `maxUnavailable: 0`,
  `maxSurge: 1`, `minAvailable: 1` PDBs, and soft hostname topology spread.
- Redis is a one-replica `Recreate` Deployment using `emptyDir`; it has no PDB.
- The public Ingress sends `/api/v1` and `/ws/v1` to API, and `/` to Web.
  `/internal/*` remains behind the API ClusterIP service.
- All workloads use dedicated ServiceAccounts with token automount disabled and
  fixed restricted security contexts.
- The Redis credential is generated and applied locally by
  `scripts/apply-redis-auth-secret.sh`; it is never a chart value or rendered
  Secret. Redis receives only a generated ACL file, while API receives only the
  username/password file projection. Default-deny policies restrict Web egress
  to API and cluster DNS, and permit Redis ingress only from API.

## Closed Values

`values.schema.json` rejects every field except the paired Web/API image digests,
Redis image digest, display-only release version, existing Redis Secret name,
and the operation-time ingress host/TLS secret name. Image references are digest-pinned;
the checked-in Web/API values select the deployment-verified `v0.7.2` baseline.
Later selections remain deployment-capable rather than deployment-verified until
an approved AKS Validation Run records new evidence.
