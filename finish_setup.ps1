param(
    [ValidateRange(1, 180)] [int]$TargetMinutes = 22,
    [switch]$NoRun
)
$ErrorActionPreference = 'Stop'
$Repo = 'NO-NAME7861/universe-explorer'
$Account = 'ahsininfo [at] gmail.com'
$ProjectId = 'aue-20261111'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

Write-Host '== 1/4 Finding custom OAuth client secret =='
if (-not (Test-Path '.\client_secret.json')) {
    $Downloads = Join-Path $env:USERPROFILE 'Downloads'
    $candidate = Get-ChildItem -LiteralPath $Downloads -Filter 'client_secret*.json' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $candidate) {
        throw "client_secret.json missing. Complete OAuth consent screen and Credentials > Create OAuth client ID > Desktop app, then Download JSON."
    }
    Copy-Item -LiteralPath $candidate.FullName -Destination '.\client_secret.json'
    Write-Host "Copied $($candidate.Name)"
}

Write-Host '== 2/4 Creating channel OAuth token =='
python get_token.py
if (-not (Test-Path '.\token.json')) { throw 'token.json not created; browser Allow was not completed.' }

Write-Host '== 3/4 Setting YOUTUBE_TOKEN_JSON secret =='
$encoded = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path '.\token.json')))
$encoded | gh secret set YOUTUBE_TOKEN_JSON -R $Repo

Write-Host '== 4/4 OpenRouter secret and private test run =='
$secure = Read-Host 'OpenRouter API key (input hidden), or Ctrl+C to stop' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    $plain | gh secret set OPENROUTER_API_KEY -R $Repo
    Remove-Variable plain -ErrorAction SilentlyContinue
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if ($TargetMinutes -ne 22) { gh variable set TARGET_MINUTES --body "$TargetMinutes" -R $Repo }

if (-not $NoRun) {
    gh workflow run 'Daily Universe Explorer Upload' -R $Repo -f privacy=private -f target_minutes="$TargetMinutes"
    Start-Sleep -Seconds 5
    gh run list -R $Repo --limit 1
}
Write-Host "Done. Project $ProjectId | Repository $Repo"
