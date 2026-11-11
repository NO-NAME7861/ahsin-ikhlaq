param(
    [int]$TargetMinutes = 22
)
$ErrorActionPreference = 'Stop'
$Repo = 'NO-NAME7861/universe-explorer'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

Write-Host '== Ahsin Akhlaq Universe Explorer setup =='

# 1) Find or validate client_secret.json (never committed; .gitignore protects it)
if (-not (Test-Path '.\client_secret.json')) {
    $Downloads = Join-Path $env:USERPROFILE 'Downloads'
    $candidate = Get-ChildItem -LiteralPath $Downloads -Filter 'client_secret*.json' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $candidate) {
        throw "client_secret.json folder mein nahi hai. Chrome > Google Cloud Console > Credentials > OAuth client ID > Download JSON karke yahan laayein, phir script dobara chalayein."
    }
    Copy-Item -LiteralPath $candidate.FullName -Destination '.\client_secret.json'
    Write-Host "Copied: $($candidate.Name)"
}

# 2) Create token.json. Browser khulega; ahsininfo [at] gmail.com se Sign in + Allow zaroori hai.
python get_token.py
if (-not (Test-Path '.\token.json')) { throw 'token.json nahi bana - browser authorization complete nahi hui.' }

# 3) Set GitHub Actions secrets/variables for the NEW channel.
$encoded = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path '.\token.json')))
$encoded | gh secret set YOUTUBE_TOKEN_JSON -R $Repo
Write-Host 'YOUTUBE_TOKEN_JSON set.'

Write-Host 'Now paste/type your OpenRouter API key when prompted (input hidden):'
gh secret set OPENROUTER_API_KEY -R $Repo

if ($TargetMinutes -ne 22) {
    gh variable set TARGET_MINUTES --body "$TargetMinutes" -R $Repo
    Write-Host "TARGET_MINUTES set to $TargetMinutes"
}

Write-Host ''
Write-Host 'Setup complete.'
Write-Host "Private test run: gh workflow run 'Daily Universe Explorer Upload' -R $Repo -f privacy=private"
Write-Host "Logs:             gh run list -R $Repo --limit 1"
