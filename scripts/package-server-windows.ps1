# Build a single-file .exe (PyInstaller) and a Windows installer (Inno Setup)
# for SVN Server Admin. Run this ON WINDOWS from a PowerShell prompt.
#
# NOTE: the privileged-action helper (system-helper.sh + pkexec) is Linux-only.
# On Windows, actions that would need it (repository creation under a
# restricted directory, firewall rules, etc.) either need a separate
# Windows-specific privilege-elevation path or must be run from an elevated
# prompt -- this script only builds the executable/installer, it does not
# change that behavior.
#
# Prerequisites:
#   - Python 3.10+ on PATH
#   - Inno Setup 6 installed (https://jrsoftware.org/isinfo.php), with
#     ISCC.exe on PATH (or edit $Iscc below)
#
# Usage (from the repo root):
#   .\scripts\package-server-windows.ps1

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$PkgDir  = Join-Path $RootDir "svn_server"
$VenvDir = Join-Path $RootDir ".venv"
$Python  = Join-Path $VenvDir "Scripts\python.exe"
$Iscc    = "ISCC.exe"  # override if not on PATH, e.g. "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

Write-Host "=== SVN Server Admin -- Windows packaging ===" -ForegroundColor Cyan

if (-not (Test-Path $Python)) {
    Write-Host "Creating virtual environment at $VenvDir ..."
    python -m venv $VenvDir
}

Write-Host "Installing dependencies ..."
& $Python -m pip install --upgrade pip -q
& $Python -m pip install "PySide6>=6.7" "keyring>=25.0" pyinstaller -q

Write-Host "Building svn-server-admin.exe with PyInstaller ..."
& $Python -m PyInstaller (Join-Path $PkgDir "pyinstaller\svn-server-admin.spec") --noconfirm `
    --distpath (Join-Path $PkgDir "pyinstaller\dist") `
    --workpath (Join-Path $PkgDir "pyinstaller\build")

if (-not (Get-Command $Iscc -ErrorAction SilentlyContinue)) {
    Write-Error "ISCC.exe (Inno Setup compiler) not found on PATH. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php, or edit `$Iscc in this script."
    exit 1
}

Write-Host "Building installer with Inno Setup ..."
& $Iscc (Join-Path $PkgDir "windows\svn-server-admin.iss")

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "  Standalone exe: $PkgDir\pyinstaller\dist\svn-server-admin.exe"
Write-Host "  Installer     : $PkgDir\windows\Output\SVN-Server-Admin-Setup.exe"
