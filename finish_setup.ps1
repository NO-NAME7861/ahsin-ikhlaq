param(
    [ValidateRange(1, 180)] [int]$TargetMinutes = 22,
    [switch]$NoRun
)
$ErrorActionPreference = 'Stop'
$Repo = 'NO-NAME7861/universe-explorer'
$Account = 'ahsininfo [at] gmail.com'
$ProjectId = 'aue-20261111'
$Gcloud = Join-Path $env:LOCALAPPDATA 'Temp\opencode\gcloud-portable\google-cloud-sdk\bin\gcloud.cmd'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

if (-not (Test-Path $Gcloud)) { throw "Portable Google Cloud SDK missing: $Gcloud" }
$env:PATH = (Split-Path $Gcloud) + ';' + $env:PATH

Write-Host '== 1/5 Checking authorized account =='
$accounts = @(gcloud auth list --format='value(account)' --quiet 2>&1)
if (($accounts | ForEach-Object { $_.Trim() }) -notcontains $Account) {
    throw "Google authorization pending. Authorize $Account first, then rerun this script."
}
gcloud config set account $Account --quiet | Out-Null

Write-Host '== 2/5 Creating/selecting Google Cloud project =='
gcloud projects describe $ProjectId --quiet 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Google Cloud project $ProjectId missing or inaccessible."
}
gcloud config set project $ProjectId --quiet | Out-Null

Write-Host '== 3/5 Enabling YouTube Data API and Drive API =='
gcloud services enable youtube.googleapis.com drive.googleapis.com --project=$ProjectId --quiet
if ($LASTEXITCODE -ne 0) { throw 'API enable failed' }

Write-Host '== 4/5 Authorizing YouTube/Drive upload credentials =='
$scopes = @(
  'openid',
  'https://www.googleapis.com/auth/userinfo.email',
  'https://www.googleapis.com/auth/cloud-platform',
  'https://www.googleapis.com/auth/youtube',
  'https://www.googleapis.com/auth/youtube.upload',
  'https://www.googleapis.com/auth/drive.file'
) -join ','
gcloud auth application-default login $Account --launch-browser --scopes=$scopes --quiet
$adc = Join-Path $env:APPDATA 'gcloud\application_default_credentials.json'
if (-not (Test-Path $adc)) { throw "ADC file missing: $adc" }
Copy-Item -LiteralPath $adc -Destination (Join-Path $ProjectDir 'token.json') -Force
[Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path '.\token.json'))) | gh secret set YOUTUBE_TOKEN_JSON -R $Repo

Write-Host '== 5/5 OpenRouter secret and test run =='
$secure = Read-Host 'Paste OpenRouter API key (input hidden), or press Ctrl+C to stop' -AsSecureString
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
Write-Host "Done. Google Cloud project: $ProjectId | Repository: $Repo"
