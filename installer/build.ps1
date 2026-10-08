# Crea l'installer di Kittenbound: dist\Kittenbound_Setup.exe
# Uso (dalla cartella del progetto):  powershell -ExecutionPolicy Bypass -File installer\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$gold = Select-String -Path game\settings.py -Pattern '^START_GOLD\s*=\s*(\d+)'
if ($gold.Matches[0].Groups[1].Value -ne "0") { throw "START_GOLD non e' 0 in game\settings.py: rimettilo a 0 prima di creare l'installer." }
$biome = Select-String -Path game\settings.py -Pattern '^DEV_START_BIOME\s*=\s*(\d+)'
if ($biome -and $biome.Matches[0].Groups[1].Value -ne "1") { throw "DEV_START_BIOME non e' 1 in game\settings.py: rimettilo a 1 prima di creare l'installer." }

# 1) gioco impacchettato (Python e pygame inclusi, non serve installare niente)
& .venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name Kittenbound `
    --icon installer\kittenbound.ico `
    --add-data "assets;assets" `
    --distpath dist --workpath build main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fallito" }

# 2) installer
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 non trovato (winget install JRSoftware.InnoSetup)" }
& $iscc /Q installer\kittenbound.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup fallito" }
Write-Host "Fatto: dist\Kittenbound_Setup.exe"
