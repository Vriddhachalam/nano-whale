$ErrorActionPreference = "Stop"
$BinName = "nano-whale.exe"
$InstallDir = "$env:USERPROFILE\.local\bin"
$InstallPath = Join-Path $InstallDir $BinName

if (Test-Path $InstallPath) {
    Write-Host "Removing $InstallPath..."
    Remove-Item -Path $InstallPath -Force
    Write-Host "nano-whale has been successfully uninstalled."
} else {
    Write-Host "nano-whale is not installed in $InstallDir."
}
