[CmdletBinding()]
param(
    [string]$PythonCommand = "python",
    [switch]$Clean,
    [switch]$InstallDependencies,
    [string]$OutputDirectory = "dist",
    [switch]$CreateZip
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$repoRootPrefix = $repoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$specPath = Join-Path $repoRoot "packaging\SafeScan.spec"
$outputPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDirectory))
if (-not $outputPath.StartsWith($repoRootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputDirectory must remain inside the repository: $outputPath"
}
$workPath = Join-Path $repoRoot (Join-Path "build\pyinstaller" (Get-Date -Format "yyyyMMdd-HHmmssfff"))

if (-not (Test-Path -LiteralPath $specPath -PathType Leaf)) {
    throw "Packaging spec was not found: $specPath"
}

function Invoke-Python {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & $PythonCommand @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code ${LASTEXITCODE}: $PythonCommand $($Arguments -join ' ')"
    }
}

if ($InstallDependencies) {
    Write-Host "Installing the optional packaging dependencies. This may use the configured package index."
    Invoke-Python @("-m", "pip", "install", "-e", "$repoRoot[package]")
}

Invoke-Python @("-c", "import PyInstaller, PySide6")

$pyInstallerArguments = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--distpath", $outputPath,
    "--workpath", $workPath,
    $specPath
)

if ($Clean -and (Test-Path -LiteralPath $outputPath)) {
    Remove-Item -LiteralPath $outputPath -Recurse -Force
}

Write-Host "Building SafeScan from $specPath"
Invoke-Python $pyInstallerArguments

$exePath = Join-Path $outputPath "SafeScan\SafeScan.exe"
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    throw "PyInstaller completed without producing the expected executable: $exePath"
}

if ($CreateZip) {
    $zipPath = Join-Path $outputPath "SafeScan-windows.zip"
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -Path (Join-Path $outputPath "SafeScan") -DestinationPath $zipPath
    Write-Host "Created $zipPath"
}

Write-Host "SafeScan executable: $exePath"
