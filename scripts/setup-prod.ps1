# Cria a estrutura de dados no disco D: e gera o .env com segredos fortes (se nao existir).
# Arquivo em ASCII de proposito (compativel com PowerShell 5.1).
param([string]$DataRoot = "D:/docker-data/clipmaker")

foreach ($d in "videos","cache","logs","redis","caddy/data","caddy/config") {
    New-Item -ItemType Directory -Force -Path (Join-Path $DataRoot $d) | Out-Null
}
Write-Host "Diretorios criados em $DataRoot"

$root = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    function New-SecureHex($bytes) {
        $b = New-Object byte[] $bytes
        $rng.GetBytes($b)
        ($b | ForEach-Object { $_.ToString('x2') }) -join ''
    }
    $example = Get-Content (Join-Path $root ".env.example") -Raw -Encoding UTF8
    $example = $example -replace '(?m)^SECRET_KEY=.*$',        "SECRET_KEY=$(New-SecureHex 32)"
    $example = $example -replace '(?m)^POSTGRES_PASSWORD=.*$', "POSTGRES_PASSWORD=$(New-SecureHex 24)"
    $example = $example -replace '(?m)^REDIS_PASSWORD=.*$',    "REDIS_PASSWORD=$(New-SecureHex 24)"
    [System.IO.File]::WriteAllText($envFile, $example, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host ".env gerado com segredos novos. Preencha GEMINI_API_KEY e DOMAIN."
} else {
    Write-Host ".env ja existe - nao foi sobrescrito."
}
