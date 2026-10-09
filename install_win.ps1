$ErrorActionPreference = "Stop"
$Repo = "Vriddhachalam/nano-whale"
$BinName = "nano-whale.exe"
$AssetName = "nano-whale-windows-x86_64.exe"

Write-Host "Fetching latest release for $AssetName..."
$ReleaseUrl = "https://api.github.com/repos/$Repo/releases/latest"
$Release = Invoke-RestMethod -Uri $ReleaseUrl

$Asset = $Release.assets | Where-Object { $_.name -eq $AssetName }
if (-not $Asset) {
    Write-Error "Could not find a release asset for Windows ($AssetName). Make sure a release exists in the repository."
    exit 1
}

$DownloadUrl = $Asset.browser_download_url
Write-Host "Downloading $DownloadUrl..."

$InstallDir = "$env:USERPROFILE\.local\bin"
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
}

$InstallPath = Join-Path $InstallDir $BinName
Invoke-WebRequest -Uri $DownloadUrl -OutFile $InstallPath

Write-Host "Installation complete! $InstallPath has been created."

$UserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($UserPath -notmatch [regex]::Escape($InstallDir)) {
    Write-Host "Adding $InstallDir to your PATH..."
    $NewPath = "$InstallDir;$UserPath"
    [Environment]::SetEnvironmentVariable("PATH", $NewPath, "User")
    $env:PATH = "$InstallDir;$env:PATH"
    Write-Host "PATH updated. Please restart your terminal for it to take full effect."
}

Write-Host "Run 'nano-whale' to start."
