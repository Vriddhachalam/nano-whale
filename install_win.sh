$u="https://github.com/Vriddhachalam/nano-whale/releases/latest/download/nano-whale-windows-x64.zip";
$d="$env:LOCALAPPDATA\nano-whale";
$z="$env:TEMP\nw.zip";
iwr $u -OutFile $z -UseBasicParsing;if(Test-Path $d){rm -r $d -Force};
mkdir $d -Force|Out-Null;Expand-Archive $z $d -Force;
rm $z;
$p=[Environment]::GetEnvironmentVariable("Path","User");
if($p -notlike "*$d*"){[Environment]::SetEnvironmentVariable("Path","$p;$d","User");
$env:Path="$env:Path;$d"};Write-Host "Installed. Run: myapp"