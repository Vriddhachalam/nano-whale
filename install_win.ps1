$downloadUrl = "https://github.com/Karthikeyan-070204/nano-whale/releases/latest/download/nano-whale-Windows.zip"
$zipPath = "$env:TEMP\nano-whale.zip"
$installDir = "C:\Program Files\nano-whale"

Write-Host "Downloading Nano Whale for Windows..."
Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath

if (!(Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir | Out-Null
}

Write-Host "Extracting..."
Expand-Archive -Path $zipPath -DestinationPath $installDir -Force

$exePath = "C:\Program Files\nano-whale"
$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$pathArray = $machinePath -split ';'

if ($pathArray -notcontains $exePath) {
    Write-Host "Adding to PATH..."
    [System.Environment]::SetEnvironmentVariable(
        "Path",
        "$machinePath;$exePath",
        [System.EnvironmentVariableTarget]::Machine
    )
}

Remove-Item $zipPath -Force

Write-Host "----------------------------------------"
Write-Host "Nano Whale installed successfully!"
Write-Host "Please close and reopen your terminal to use the 'nano-whale' command."
Write-Host "----------------------------------------"
