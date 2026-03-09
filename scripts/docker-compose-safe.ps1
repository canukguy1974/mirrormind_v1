param(
  [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
  [string[]]$ComposeArgs = @("up", "-d", "--build"),
  [string]$ComposeFile = "docker/docker-compose.yml",
  [string]$EnvFile = ".env"
)

$safeConfigDir = Join-Path $env:USERPROFILE ".docker-tmp-mirrormind"
$safeConfigPath = Join-Path $safeConfigDir "config.json"

if (!(Test-Path $safeConfigDir)) {
  New-Item -ItemType Directory -Force -Path $safeConfigDir | Out-Null
}

if (!(Test-Path $safeConfigPath)) {
  '{"auths":{}}' | Set-Content -Path $safeConfigPath
}

Write-Host "Using Docker config: $safeConfigDir"
docker --config "$safeConfigDir" compose -f $ComposeFile --env-file $EnvFile @ComposeArgs
