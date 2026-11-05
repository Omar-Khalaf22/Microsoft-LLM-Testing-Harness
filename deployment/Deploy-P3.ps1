param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$InfrastructureParametersPath,
    [Parameter(Mandatory)][string]$ApplicationParametersPath,
    [Parameter(Mandatory)][string]$ImageTag
)
$ErrorActionPreference = 'Stop'
$P3Root = Split-Path -Parent $PSScriptRoot
# Both parameter files are private, prepared outside the repository. The first
# includes secure database passwords; the second includes reviewed OIDC settings.
$P3Infra = (Resolve-Path -LiteralPath $InfrastructureParametersPath).Path
$P3Application = (Resolve-Path -LiteralPath $ApplicationParametersPath).Path
az account show --subscription $SubscriptionId --query id -o tsv | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Sign in to the approved Azure subscription first.' }
az bicep build --file "$PSScriptRoot\main.bicep" --outfile "$env:TEMP\harness-main.arm.json"
if ($LASTEXITCODE -ne 0) { throw 'Infrastructure compilation failed.' }
az bicep build --file "$PSScriptRoot\app.bicep" --outfile "$env:TEMP\harness-app.arm.json"
if ($LASTEXITCODE -ne 0) { throw 'Application compilation failed.' }
$P3Result = az deployment group create --subscription $SubscriptionId --resource-group $ResourceGroup --name harness-p3-infra --template-file "$PSScriptRoot\main.bicep" --parameters "@$P3Infra" --query properties.outputs -o json
if ($LASTEXITCODE -ne 0) { throw 'Infrastructure deployment failed.' }
$P3Outputs = $P3Result | ConvertFrom-Json
$P3Registry = $P3Outputs.registryName.value
az acr build --subscription $SubscriptionId --registry $P3Registry --image "llm-harness:$ImageTag" $P3Root
if ($LASTEXITCODE -ne 0) { throw 'Image build failed.' }
$P3AppParameters = @(
    "@$P3Application", "environmentId=$($P3Outputs.environmentId.value)",
    "identityId=$($P3Outputs.identityId.value)", "registryServer=$($P3Outputs.registryServer.value)",
    "migrationIdentityId=$($P3Outputs.migrationIdentityId.value)",
    "vaultUri=$($P3Outputs.vaultUri.value)", "imageTag=$ImageTag"
)
az deployment group create --subscription $SubscriptionId --resource-group $ResourceGroup --name harness-p3-job --template-file "$PSScriptRoot\app.bicep" --parameters @P3AppParameters 'enableWeb=false' -o none
if ($LASTEXITCODE -ne 0) { throw 'Migration job deployment failed. Check identity propagation and Key Vault access.' }
$P3Prefix = (Get-Content -LiteralPath $P3Application -Raw | ConvertFrom-Json).parameters.prefix.value
$P3Execution = az containerapp job start --subscription $SubscriptionId --resource-group $ResourceGroup --name "$P3Prefix-migrate" --query name -o tsv
if ($LASTEXITCODE -ne 0) { throw 'Migration job could not start.' }
$P3Status = ''
for ($P3Attempt = 0; $P3Attempt -lt 120; $P3Attempt++) {
    $P3Status = az containerapp job execution show --subscription $SubscriptionId --resource-group $ResourceGroup --name "$P3Prefix-migrate" --job-execution-name $P3Execution --query properties.status -o tsv
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect migration execution.' }
    if ($P3Status -eq 'Succeeded') { break }
    if ($P3Status -eq 'Failed') { throw 'Migration failed. Inspect sanitized job logs before deploying the app.' }
    Start-Sleep -Seconds 5
}
if ($P3Status -ne 'Succeeded') { throw 'Migration did not finish within ten minutes.' }
az deployment group create --subscription $SubscriptionId --resource-group $ResourceGroup --name harness-p3-app --template-file "$PSScriptRoot\app.bicep" --parameters @P3AppParameters 'enableWeb=true' --query properties.outputs.url.value -o tsv
if ($LASTEXITCODE -ne 0) { throw 'Web deployment failed.' }
