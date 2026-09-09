# Build with an existing, prepared native Windows Python environment.
# No installation, signing, registry changes, or cleanup is performed here.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$Iscc
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function ConvertTo-NativeArgument([string]$Value) {
    # Windows CRT quoting: backslashes before a quote and at the closing quote
    # must be doubled. Quote every argument, including the empty string.
    $Quoted = [regex]::Replace($Value, '(\\*)"', {
        param($Match)
        $Match.Groups[1].Value + $Match.Groups[1].Value + '\"'
    })
    $Quoted = [regex]::Replace($Quoted, '(\\+)$', '$1$1')
    return '"' + $Quoted + '"'
}

function Invoke-NativeBuildStep {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$LogStem,
        [int]$TimeoutSeconds
    )
    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $FilePath
    $StartInfo.Arguments = ($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
    $StartInfo.UseShellExecute = $false
    $StartInfo.CreateNoWindow = $true
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $StartInfo
    try {
        if (!$Process.Start()) { throw "Could not start $FilePath" }
        # Drain both pipes concurrently while explicitly waiting for the actual
        # process; PowerShell's native invocation status is not used.
        $StdoutTask = $Process.StandardOutput.ReadToEndAsync()
        $StderrTask = $Process.StandardError.ReadToEndAsync()
        if (!$Process.WaitForExit($TimeoutSeconds * 1000)) {
            $Process.Kill()
            "Timed out after $TimeoutSeconds seconds: $FilePath" |
                Set-Content -LiteralPath "$LogStem.timeout.txt" -Encoding UTF8
            throw "Build step timed out; see $LogStem.timeout.txt. Check for remaining child processes."
        }
        if (![System.Threading.Tasks.Task]::WaitAll(
            [System.Threading.Tasks.Task[]]@($StdoutTask, $StderrTask), 5000)) {
            throw "Build output pipes did not close: $FilePath"
        }
        $Stdout = $StdoutTask.Result
        $Stderr = $StderrTask.Result
        [IO.File]::WriteAllText("$LogStem.stdout.log", $Stdout)
        [IO.File]::WriteAllText("$LogStem.stderr.log", $Stderr)
        if ($Process.ExitCode -ne 0) {
            throw "Build step exited $($Process.ExitCode); see $LogStem.stderr.log and .stdout.log"
        }
        return $Stdout
    }
    finally {
        $Process.Dispose()
    }
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Build Chemvas on native Windows, not WSL or another host OS.'
}
$Python = (Resolve-Path -LiteralPath $Python).Path
$Iscc = (Resolve-Path -LiteralPath $Iscc).Path
if (!(Test-Path -LiteralPath $Python -PathType Leaf) -or
    !(Test-Path -LiteralPath $Iscc -PathType Leaf)) {
    throw '-Python and -Iscc must identify existing executable files.'
}
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$AppDir = Join-Path $RepoRoot 'app'
$Spec = Join-Path $RepoRoot 'packaging/chemvas.spec'
$InstallerScript = Join-Path $PSScriptRoot 'chemvas.iss'
if (!(Test-Path -LiteralPath $InstallerScript -PathType Leaf)) {
    throw "Installer script is missing: $InstallerScript"
}

# A new generation is always used. Existing builds and installers are never
# removed or overwritten, including when a subprocess fails.
$Generation = 'windows-' + [Guid]::NewGuid().ToString('N')
$WorkDir = Join-Path $RepoRoot "build/$Generation"
$DistDir = Join-Path $RepoRoot "dist/$Generation"
$InstallerDir = Join-Path $DistDir 'installer'
New-Item -ItemType Directory -Path $WorkDir | Out-Null
New-Item -ItemType Directory -Path $DistDir | Out-Null
New-Item -ItemType Directory -Path $InstallerDir | Out-Null
$Probe = @'
import json, platform, struct, sys
if sys.platform != 'win32' or struct.calcsize('P') != 8 or platform.machine().lower() not in ('amd64', 'x86_64'):
    raise SystemExit('A native Windows x64 Python is required.')
if sys.version_info < (3, 12):
    raise SystemExit('Python 3.12 or newer is required.')
import PyInstaller, PIL, rdkit
from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
if PyInstaller.__version__ != '6.22.2':
    raise SystemExit('Use PyInstaller 6.22.2 from requirements-build.txt.')
sys.path.insert(0, sys.argv[1])
import chemvas
print(json.dumps(dict(version=chemvas.__version__, source=chemvas.__file__, python=sys.executable, python_version=platform.python_version(), pyinstaller=PyInstaller.__version__, pyqt=PYQT_VERSION_STR, qt=QT_VERSION_STR, pillow=PIL.__version__, rdkit=rdkit.__version__)))
'@
$ProbePath = Join-Path $WorkDir 'environment-probe.py'
[IO.File]::WriteAllText($ProbePath, $Probe)
$ProbeResult = Invoke-NativeBuildStep -FilePath $Python -Arguments @('-I', '-B', $ProbePath, $AppDir) `
    -LogStem (Join-Path $WorkDir 'environment') -TimeoutSeconds 60
$EnvironmentInfo = $ProbeResult | ConvertFrom-Json
$Version = $EnvironmentInfo.version
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw 'Windows bundles require a numeric major.minor.patch source version.'
}

Invoke-NativeBuildStep -FilePath $Python `
    -Arguments @('-I', '-B', '-m', 'PyInstaller', '--workpath', $WorkDir, '--distpath', $DistDir, $Spec) `
    -LogStem (Join-Path $WorkDir 'pyinstaller') -TimeoutSeconds 1800 | Out-Null
$BundleDir = Join-Path $DistDir 'chemvas'
$GuiExe = Join-Path $BundleDir 'chemvas.exe'
$CliExe = Join-Path $BundleDir 'chemvas-cli.exe'
if (!(Test-Path -LiteralPath $GuiExe -PathType Leaf) -or
    !(Test-Path -LiteralPath $CliExe -PathType Leaf)) {
    throw 'The bundle must contain both chemvas.exe and chemvas-cli.exe.'
}
$ReportedVersion = Invoke-NativeBuildStep -FilePath $CliExe -Arguments @('--version') `
    -LogStem (Join-Path $WorkDir 'version') -TimeoutSeconds 60
if ($ReportedVersion.Trim() -ne "chemvas $Version") {
    throw 'The bundled console executable did not report the source version.'
}
Invoke-NativeBuildStep -FilePath $Iscc `
    -Arguments @("/DAppVersion=$Version", "/DBundleDir=$BundleDir", "/DOutputDir=$InstallerDir", $InstallerScript) `
    -LogStem (Join-Path $WorkDir 'installer') -TimeoutSeconds 600 | Out-Null
$Installer = Join-Path $InstallerDir "Chemvas-$Version-windows-x64-setup.exe"
if (!(Test-Path -LiteralPath $Installer -PathType Leaf)) {
    throw "Expected installer was not produced: $Installer"
}
$Hashes = @{}
foreach ($Artifact in @($Spec, $InstallerScript, $GuiExe, $CliExe, $Installer)) {
    $Hashes[$Artifact] = (Get-FileHash -LiteralPath $Artifact -Algorithm SHA256).Hash.ToLowerInvariant()
}
$Receipt = [ordered]@{
    environment = $EnvironmentInfo
    bundle = $BundleDir
    installer = $Installer
    process_logs = $WorkDir
    sha256 = $Hashes
    limitations = @('Unsigned local build; not an installation or GUI acceptance test.',
        'Dependency notices are included as available; redistribution licensing requires review.')
}
$ReceiptPath = Join-Path $DistDir 'build-receipt.json'
$Receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ReceiptPath -Encoding UTF8
Write-Output "Bundle: $BundleDir"
Write-Output "Installer: $Installer"
Write-Output "Receipt: $ReceiptPath"
