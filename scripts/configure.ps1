$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$envPath = Join-Path $projectRoot '.env'
if (Test-Path -LiteralPath $envPath) { throw '.env already exists; preserve or edit it explicitly.' }
function New-Secret {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToHexString($bytes).ToLowerInvariant()
}
$adminPassword = New-Secret
$settings = @(
    "POSTGRES_PASSWORD=$(New-Secret)",
    "ADMIN_PASSWORD=$adminPassword",
    "INGEST_KEY=$(New-Secret)",
    "CHECKPOINT_SIGNING_KEY=$(New-Secret)",
    'ALLOWED_ORIGINS=http://localhost:3000',
    'COOKIE_SECURE=false',
    'RETENTION_DAYS=30'
)
[IO.File]::WriteAllLines($envPath, $settings)
Write-Host 'Created .env. Read ADMIN_PASSWORD locally to sign in as admin. Do not commit .env.'
