targetScope = 'resourceGroup'
param prefix string
param location string = resourceGroup().location
param environmentId string
param identityId string
param migrationIdentityId string
param registryServer string
param vaultUri string
param imageTag string
param oidcIssuer string
param oidcAudience string
param oidcJwksUrl string
param authorizedSubjects array
param enableWeb bool = false

var image = '${registryServer}/llm-harness:${imageTag}'
var assigned = { '${identityId}': {} }
var registry = [{ server: registryServer, identity: identityId }]
var secrets = [
  { name: 'migration-url', keyVaultUrl: '${vaultUri}secrets/migration-url', identity: migrationIdentityId }
  { name: 'app-db-password', keyVaultUrl: '${vaultUri}secrets/app-db-password', identity: migrationIdentityId }
]
resource migration 'Microsoft.App/jobs@2025-01-01' = {
  name: '${prefix}-migrate'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${migrationIdentityId}': {} } }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 600
      replicaRetryLimit: 0
      manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
      registries: [{ server: registryServer, identity: migrationIdentityId }]
      secrets: secrets
    }
    template: {
      containers: [{
        name: 'migrate'
        image: image
        command: ['/bin/sh', '-c']
        args: ['python -m app.storage.bootstrap_database && python -m alembic upgrade head && python -m app.storage.bootstrap_database --grant']
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: [
          { name: 'DATABASE_URL', secretRef: 'migration-url' }
          { name: 'APP_DATABASE_PASSWORD', secretRef: 'app-db-password' }
          { name: 'APP_ENV', value: 'production' }
        ]
      }]
    }
  }
}
resource web 'Microsoft.App/containerApps@2025-01-01' = if (enableWeb) {
  name: '${prefix}-web'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: assigned }
  properties: {
    managedEnvironmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: true, targetPort: 8000, allowInsecure: false, transport: 'auto' }
      registries: registry
      secrets: [{ name: 'database-url', keyVaultUrl: '${vaultUri}secrets/database-url', identity: identityId }]
    }
    template: {
      containers: [{
        name: 'web'
        image: image
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: [
          { name: 'DATABASE_URL', secretRef: 'database-url' }
          { name: 'APP_ENV', value: 'production' }
          { name: 'AUTH_MODE', value: 'oidc' }
          { name: 'PROJECT_ID', value: 'prototype' }
          { name: 'OIDC_ISSUER', value: oidcIssuer }
          { name: 'OIDC_AUDIENCE', value: oidcAudience }
          { name: 'OIDC_JWKS_URL', value: oidcJwksUrl }
          { name: 'AUTHORIZED_SUBJECTS', value: string(authorizedSubjects) }
          { name: 'LLM_PROVIDER', value: 'demo' }
        ]
        probes: [
          { type: 'Liveness', httpGet: { path: '/health', port: 8000 }, periodSeconds: 30 }
          { type: 'Readiness', httpGet: { path: '/ready', port: 8000 }, periodSeconds: 10 }
          { type: 'Startup', httpGet: { path: '/health', port: 8000 }, periodSeconds: 5, failureThreshold: 30 }
        ]
      }]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}
output url string = enableWeb ? 'https://${web!.properties.configuration.ingress.fqdn}' : ''
