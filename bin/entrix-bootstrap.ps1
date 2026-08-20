param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $EntrixArgs
)

$ErrorActionPreference = "Stop"

function Fail([string] $Message) {
    [Console]::Error.WriteLine("entrix bootstrap: $Message")
    exit 1
}

function Get-Sha256([string] $Path) {
    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-ExpectedSha256([string] $Path) {
    $line = (Get-Content -Path $Path -Raw).Trim()
    if ([string]::IsNullOrWhiteSpace($line)) {
        return ""
    }
    return ($line -split "\s+")[0].ToLowerInvariant()
}

function Test-Cache([string] $BinaryPath, [string] $ChecksumPath) {
    if (-not (Test-Path -LiteralPath $BinaryPath -PathType Leaf)) {
        return $false
    }
    if (-not (Test-Path -LiteralPath $ChecksumPath -PathType Leaf)) {
        return $false
    }
    try {
        $expected = Get-ExpectedSha256 $ChecksumPath
        if ($expected.Length -ne 64) {
            return $false
        }
        return (Get-Sha256 $BinaryPath) -eq $expected
    } catch {
        return $false
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginRoot = $env:CLAUDE_PLUGIN_ROOT
if ([string]::IsNullOrWhiteSpace($pluginRoot)) {
    $pluginRoot = Split-Path -Parent $scriptDir
}

$directBinary = $env:ENTRIX_BINARY_PATH
if (-not [string]::IsNullOrWhiteSpace($directBinary)) {
    if (-not (Test-Path -LiteralPath $directBinary -PathType Leaf)) {
        Fail "ENTRIX_BINARY_PATH is not a file: $directBinary"
    }
    & $directBinary @EntrixArgs
    exit $LASTEXITCODE
}

$version = $env:ENTRIX_BINARY_VERSION
if ([string]::IsNullOrWhiteSpace($version)) {
    $manifestPath = Join-Path $pluginRoot ".claude-plugin\plugin.json"
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        try {
            $version = (Get-Content -Path $manifestPath -Raw | ConvertFrom-Json).version
        } catch {
            Fail "cannot read plugin version from $manifestPath"
        }
    }
}
if ([string]::IsNullOrWhiteSpace($version)) {
    Fail "cannot determine plugin binary version"
}

# RuntimeInformation.ProcessArchitecture selects the host binary target.
$architecture = [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture
if ($architecture -eq [System.Runtime.InteropServices.Architecture]::X64) {
    # Architecture::X64 is the supported Windows target.
    $target = "windows-amd64"
} else {
    Fail "unsupported release architecture: $architecture"
}

$asset = "entrix-$version-$target.exe"
$localAppData = $env:LOCALAPPDATA
if ([string]::IsNullOrWhiteSpace($localAppData)) {
    $localAppData = $env:TEMP
}
if ([string]::IsNullOrWhiteSpace($localAppData)) {
    Fail "cannot determine a cache directory"
}
$cacheDir = Join-Path $localAppData "entrix\bin\$version\$target"
$cachedBinary = Join-Path $cacheDir $asset
$cachedChecksum = "$cachedBinary.sha256"
New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null

$lockDir = Join-Path $cacheDir ".lock"
$lockAcquired = $false
for ($attempt = 0; $attempt -lt 120; $attempt++) {
    try {
        New-Item -ItemType Directory -Path $lockDir -ErrorAction Stop | Out-Null
        $lockAcquired = $true
        break
    } catch {
        if (Test-Cache $cachedBinary $cachedChecksum) {
            & $cachedBinary @EntrixArgs
            exit $LASTEXITCODE
        }
        Start-Sleep -Milliseconds 50
    }
}
if (-not $lockAcquired) {
    Fail "timed out waiting for cache lock"
}

try {
    if (Test-Cache $cachedBinary $cachedChecksum) {
        Remove-Item -LiteralPath $lockDir -Force -ErrorAction SilentlyContinue
        $lockAcquired = $false
        & $cachedBinary @EntrixArgs
        exit $LASTEXITCODE
    }

    $repository = $env:ENTRIX_RELEASE_REPOSITORY
    if ([string]::IsNullOrWhiteSpace($repository)) {
        $repository = "duxvfeng/entrix"
    }
    $baseUrl = $env:ENTRIX_RELEASE_BASE_URL
    if ([string]::IsNullOrWhiteSpace($baseUrl)) {
        $baseUrl = "https://github.com/$repository/releases/download/v$version"
    }
    $baseUrl = $baseUrl.TrimEnd("/")
    $downloadDir = Join-Path $cacheDir (".download-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $downloadDir -Force | Out-Null
    $binaryTemp = Join-Path $downloadDir $asset
    $checksumTemp = "$binaryTemp.sha256"

    try {
        [Console]::Error.WriteLine("downloading $asset for $target")
        Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/$asset" -OutFile $binaryTemp
        Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/$asset.sha256" -OutFile $checksumTemp
        $expected = Get-ExpectedSha256 $checksumTemp
        if ($expected.Length -ne 64) {
            Fail "invalid SHA-256 file for $asset"
        }
        if ((Get-Sha256 $binaryTemp) -ne $expected) {
            Fail "SHA-256 verification failed for $asset"
        }
        Move-Item -LiteralPath $binaryTemp -Destination $cachedBinary -Force
        Move-Item -LiteralPath $checksumTemp -Destination $cachedChecksum -Force
    } finally {
        if (Test-Path -LiteralPath $downloadDir) {
            Remove-Item -LiteralPath $downloadDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
} catch {
    Fail $_.Exception.Message
} finally {
    if ($lockAcquired -and (Test-Path -LiteralPath $lockDir)) {
        Remove-Item -LiteralPath $lockDir -Force -ErrorAction SilentlyContinue
    }
}

& $cachedBinary @EntrixArgs
exit $LASTEXITCODE
