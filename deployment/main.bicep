targetScope = 'resourceGroup'

@minLength(3)
@maxLength(12)
param prefix string
param location string = resourceGroup().location
@secure()
param administratorPassword string
@secure()
param appDatabasePassword string
param databaseSku string = 'Standard_B1ms'
param databaseTier string = 'Burstable'
param databaseStorageGB int = 32
param logRetentionDays int = 30

var suffix = uniqueString(resourceGroup().id, prefix)
var pgName = '${prefix}-pg-${suffix}'
var vaultName = take('${prefix}-kv-${suffix}', 24)

resource network 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: '${prefix}-vnet'
  location: location
  properties: {
    addressSpace: { addressPrefixes: ['10.73.0.0/16'] }
    subnets: [
      {
        name: 'apps'
        properties: {
          addressPrefix: '10.73.0.0/23'
          delegations: [{ name: 'apps', properties: { serviceName: 'Microsoft.App/environments' } }]
        }
      }
      {
        name: 'postgres'
        properties: {
          addressPrefix: '10.73.2.0/24'
          delegations: [{ name: 'postgres', properties: { serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers' } }]
        }
      }
    ]
  }
}
resource dns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: '${prefix}.postgres.database.azure.com'
  location: 'global'
}
resource dnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dns
  name: '${prefix}-link'
  location: 'global'
  properties: { registrationEnabled: false, virtualNetwork: { id: network.id } }
}
resource database 'Microsoft.DBforPostgreSQL/flexibleServers@2025-08-01' = {
  name: pgName
  location: location
  sku: { name: databaseSku, tier: databaseTier }
  properties: {
    version: '16'
    administratorLogin: 'harness_admin'
    administratorLoginPassword: administratorPassword
    storage: { storageSizeGB: databaseStorageGB }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: {
      delegatedSubnetResourceId: '${network.id}/subnets/postgres'
      privateDnsZoneArmResourceId: dns.id
      publicNetworkAccess: 'Disabled'
    }
  }
  dependsOn: [dnsLink]
}
resource appDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2025-08-01' = {
  parent: database
  name: 'llm_harness'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}
resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: '${prefix}${suffix}'
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-app-identity'
  location: location
}
resource migrationIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-migration-identity'
  location: location
}
resource pullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, 'pull')
  scope: registry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}
resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: vaultName
  location: location
  properties: {
    tenantId: tenant().tenantId
    sku: { name: 'standard', family: 'A' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: true
    publicNetworkAccess: 'Enabled'
  }
}
resource secretRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, identity.id, 'secrets')
  scope: appUrl
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}
resource migrationPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, migrationIdentity.id, 'pull')
  scope: registry
  properties: {
    principalId: migrationIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}
resource migrationSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, migrationIdentity.id, 'secrets')
  scope: vault
  properties: {
    principalId: migrationIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}
resource appUrl 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'database-url'
  properties: {
    value: 'postgresql+psycopg://llm_harness_app:${uriComponent(appDatabasePassword)}@${database.properties.fullyQualifiedDomainName}:5432/llm_harness?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt'
  }
  dependsOn: [appDatabase]
}
resource migrationUrl 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'migration-url'
  properties: {
    value: 'postgresql+psycopg://harness_admin:${uriComponent(administratorPassword)}@${database.properties.fullyQualifiedDomainName}:5432/llm_harness?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt'
  }
}
resource appPassword 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'app-db-password'
  properties: { value: appDatabasePassword }
}
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: logRetentionDays
    workspaceCapping: { dailyQuotaGb: json('0.1') }
  }
}
resource environment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: '${prefix}-environment'
  location: location
  properties: {
    vnetConfiguration: { infrastructureSubnetId: '${network.id}/subnets/apps' }
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

output registryName string = registry.name
output registryServer string = registry.properties.loginServer
output identityId string = identity.id
output migrationIdentityId string = migrationIdentity.id
output environmentId string = environment.id
output vaultUri string = vault.properties.vaultUri
output databaseHost string = database.properties.fullyQualifiedDomainName
