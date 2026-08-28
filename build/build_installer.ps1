# Build complet de l'installeur PromptuinoUI.
#
# Usage (depuis n'importe quel dossier) :
#   .\build\build_installer.ps1
#
# Prerequis :
#   - Python 3.12+ avec pip
#   - PyInstaller installe (pip install pyinstaller)
#   - Inno Setup 6 installe (winget install JRSoftware.InnoSetup)
#   - build\third_party\arduino-cli.exe present
#
# Resultat : build\output\Promptuino-Setup.exe

$ErrorActionPreference = "Stop"

# Resolution chemins relatifs au repo root (= parent du dossier build)
$buildDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $buildDir
Set-Location $repoRoot

Write-Host "=== Build PromptuinoUI installer ===" -ForegroundColor Cyan
Write-Host "Repo root : $repoRoot"
Write-Host ""

# ─── 1. Verifications prerequis ──────────────────────────────────────────
$arduinoCli = Join-Path $buildDir "third_party\arduino-cli.exe"
if (-not (Test-Path $arduinoCli)) {
    Write-Host "ERREUR : $arduinoCli introuvable." -ForegroundColor Red
    Write-Host "  Copie le binaire arduino-cli.exe dans build\third_party\ avant de continuer."
    exit 1
}
Write-Host "  [OK] arduino-cli.exe present"

# Recherche ISCC (Inno Setup compiler)
$isccCandidates = @(
    "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Host "ERREUR : Inno Setup 6 introuvable." -ForegroundColor Red
    Write-Host "  Installe-le : winget install JRSoftware.InnoSetup"
    exit 1
}
Write-Host "  [OK] Inno Setup ISCC.exe = $iscc"

# Verification PyInstaller
$pyinstaller = (Get-Command pyinstaller -ErrorAction SilentlyContinue)
if (-not $pyinstaller) {
    Write-Host "ERREUR : pyinstaller introuvable dans le PATH." -ForegroundColor Red
    Write-Host "  Installe-le : pip install pyinstaller"
    exit 1
}
Write-Host "  [OK] pyinstaller = $($pyinstaller.Source)"
Write-Host ""

# ─── 2. Nettoyage builds precedents ──────────────────────────────────────
Write-Host "Nettoyage des artefacts precedents..." -ForegroundColor Yellow
if (Test-Path "dist\Promptuino") { Remove-Item -Recurse -Force "dist\Promptuino" }
if (Test-Path "build\promptuinoui") { Remove-Item -Recurse -Force "build\promptuinoui" }
if (Test-Path "build\output") { Remove-Item -Recurse -Force "build\output" }
Write-Host "  [OK] dist et build de travail vides"
Write-Host ""

# ─── 3. Build PyInstaller ────────────────────────────────────────────────
Write-Host "PyInstaller build (peut prendre 1-2 minutes)..." -ForegroundColor Yellow
# Pas de Out-Null : on garde la sortie pyinstaller pour debug si echec.
# $ErrorActionPreference="Stop" arreterait sur les warnings stderr de
# pyinstaller (faux positifs), on le passe en Continue pendant l'appel.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& pyinstaller "build\promptuinoui.spec" --noconfirm 2>&1 | Tee-Object -Variable pyOut | Out-Host
$ErrorActionPreference = $prevEAP
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERREUR : PyInstaller a echoue (code $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "dist\Promptuino\Promptuino.exe")) {
    Write-Host "ERREUR : dist\Promptuino\Promptuino.exe introuvable apres build" -ForegroundColor Red
    exit 1
}
$distSize = (Get-ChildItem "dist\Promptuino" -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ("  [OK] dist\Promptuino : {0:N0} Mo" -f $distSize)
Write-Host ""

# ─── 4. Compile Inno Setup ───────────────────────────────────────────────
Write-Host "Inno Setup compile (peut prendre 1-3 minutes pour la compression LZMA2)..." -ForegroundColor Yellow
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
# /Q = quiet (limite la verbosite). Sans /Q, ISCC log chaque fichier compresse.
& $iscc "build\installer.iss" 2>&1 | Out-Host
$ErrorActionPreference = $prevEAP
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERREUR : ISCC a echoue (code $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}
$setupExe = "build\output\Promptuino-Setup.exe"
if (-not (Test-Path $setupExe)) {
    Write-Host "ERREUR : $setupExe introuvable apres compile" -ForegroundColor Red
    exit 1
}
$setupSize = (Get-Item $setupExe).Length / 1MB
Write-Host ("  [OK] $setupExe : {0:N0} Mo" -f $setupSize)
Write-Host ""

# ─── 5. Summary ──────────────────────────────────────────────────────────
Write-Host "=== Build OK ===" -ForegroundColor Green
$absSetup = (Resolve-Path $setupExe).Path
Write-Host "Installeur : $absSetup"
Write-Host ""
Write-Host "Pense a verifier que ONNX_MODEL_URL est correctement configure"
Write-Host "dans ui\onnx_setup.py (actuellement : valeur de defaut)."
