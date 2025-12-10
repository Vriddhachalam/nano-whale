$downloadUrl = "https://github.com/Vriddhachalam/nano-whale/releases/latest/download/nano-whale-windows-x64.zip"
$zipPath = "$env:TEMP\nano-whale.zip"
$installDir = "C:\Program Files\nano-whale"

Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath

if (!(Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir | Out-Null
}

Expand-Archive -Path $zipPath -DestinationPath $installDir -Force

$exePath = "C:\Program Files\nano-whale\windows-x64"
$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")

if ($machinePath -notlike "*$exePath*") {
    [System.Environment]::SetEnvironmentVariable(
        "Path",
        "$machinePath;$exePath",
        [System.EnvironmentVariableTarget]::Machine
    )
}

Remove-Item $zipPath -Force