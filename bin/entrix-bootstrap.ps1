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

function Test-Manifest([string] $ManifestPath, [string] $ExpectedVersion, [string] $ExpectedTarget, [string] $ExpectedAsset, [string] $ExpectedSha256) {
    $verifier = Join-Path $pluginRoot "bin\verify-release-manifest.mjs"
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($null -ne $node -and (Test-Path -LiteralPath $verifier -PathType Leaf)) {
        & $node.Source $verifier $ManifestPath $ExpectedVersion $ExpectedTarget $ExpectedAsset $ExpectedSha256 *> $null
        return $LASTEXITCODE -eq 0
    }
    try {
        $manifest = Get-Content -Path $ManifestPath -Raw | ConvertFrom-Json
        $asset = @($manifest.assets) | Where-Object { $_.filename -eq $ExpectedAsset } | Select-Object -First 1
        return $null -ne $asset -and
            $manifest.version -eq $ExpectedVersion -and
            $asset.version -eq $ExpectedVersion -and
            $asset.target -eq $ExpectedTarget -and
            $asset.sha256 -eq $ExpectedSha256
    } catch {
        return $false
    }
}

function Test-Cache([string] $BinaryPath, [string] $ChecksumPath, [string] $ChecksumSignaturePath, [string] $ManifestPath, [string] $ManifestSignaturePath) {
    if (-not (Test-Path -LiteralPath $BinaryPath -PathType Leaf)) {
        return $false
    }
    if (-not (Test-Path -LiteralPath $ChecksumPath -PathType Leaf)) {
        return $false
    }
    if (-not (Test-Signature $ChecksumPath $ChecksumSignaturePath) -or
        -not (Test-Signature $ManifestPath $ManifestSignaturePath)) {
        return $false
    }
    try {
        $expected = Get-ExpectedSha256 $ChecksumPath
        if ($expected.Length -ne 64) {
            return $false
        }
        return (Test-Manifest $ManifestPath $version $target $asset $expected) -and
            ((Get-Sha256 $BinaryPath) -eq $expected)
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

$publicKey = Join-Path $pluginRoot "security\release-public-key.pem"
if (-not (Test-Path -LiteralPath $publicKey -PathType Leaf)) {
    Fail "release public key is missing: $publicKey"
}

function Test-Signature([string] $FilePath, [string] $SignaturePath) {
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $SignaturePath -PathType Leaf)) {
        return $false
    }
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    $verifier = Join-Path $pluginRoot "bin\verify-release-signature.mjs"
    if ($null -ne $node -and (Test-Path -LiteralPath $verifier -PathType Leaf)) {
        & $node.Source $verifier $publicKey $FilePath $SignaturePath *> $null
        return $LASTEXITCODE -eq 0
    }
    $openssl = Get-Command openssl.exe -ErrorAction SilentlyContinue
    if ($null -ne $openssl) {
        & $openssl.Source dgst -sha256 -verify $publicKey -signature $SignaturePath $FilePath *> $null
        return $LASTEXITCODE -eq 0
    }
    return $false
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
$cachedChecksumSignature = "$cachedChecksum.sig"
$cachedManifest = Join-Path $cacheDir "release-manifest.json"
$cachedManifestSignature = "$cachedManifest.sig"
New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null

$lockDir = Join-Path $cacheDir ".lock"
$lockAcquired = $false
for ($attempt = 0; $attempt -lt 120; $attempt++) {
    try {
        New-Item -ItemType Directory -Path $lockDir -ErrorAction Stop | Out-Null
        $lockAcquired = $true
        break
    } catch {
        if (Test-Cache $cachedBinary $cachedChecksum $cachedChecksumSignature $cachedManifest $cachedManifestSignature) {
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
    if (Test-Cache $cachedBinary $cachedChecksum $cachedChecksumSignature $cachedManifest $cachedManifestSignature) {
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
    $checksumSignatureTemp = "$checksumTemp.sig"
    $manifestTemp = Join-Path $downloadDir "release-manifest.json"
    $manifestSignatureTemp = "$manifestTemp.sig"

    try {
        [Console]::Error.WriteLine("downloading $asset for $target")
        $downloadTimeout = 120
        if (-not [string]::IsNullOrWhiteSpace($env:ENTRIX_DOWNLOAD_TIMEOUT_SECONDS)) {
            $downloadTimeout = 0
            if (-not [int]::TryParse($env:ENTRIX_DOWNLOAD_TIMEOUT_SECONDS, [ref] $downloadTimeout) -or $downloadTimeout -le 0) {
                Fail "ENTRIX_DOWNLOAD_TIMEOUT_SECONDS must be a positive integer"
            }
        }
        Invoke-WebRequest -UseBasicParsing -TimeoutSec $downloadTimeout -Uri "$baseUrl/$asset" -OutFile $binaryTemp
        Invoke-WebRequest -UseBasicParsing -TimeoutSec $downloadTimeout -Uri "$baseUrl/$asset.sha256" -OutFile $checksumTemp
        Invoke-WebRequest -UseBasicParsing -TimeoutSec $downloadTimeout -Uri "$baseUrl/$asset.sha256.sig" -OutFile $checksumSignatureTemp
        Invoke-WebRequest -UseBasicParsing -TimeoutSec $downloadTimeout -Uri "$baseUrl/release-manifest.json" -OutFile $manifestTemp
        Invoke-WebRequest -UseBasicParsing -TimeoutSec $downloadTimeout -Uri "$baseUrl/release-manifest.json.sig" -OutFile $manifestSignatureTemp
        if (-not (Test-Signature $manifestTemp $manifestSignatureTemp)) {
            Fail "release manifest signature verification failed"
        }
        if (-not (Test-Signature $checksumTemp $checksumSignatureTemp)) {
            Fail "checksum signature verification failed"
        }
        $expected = Get-ExpectedSha256 $checksumTemp
        if ($expected.Length -ne 64) {
            Fail "invalid SHA-256 file for $asset"
        }
        if (-not (Test-Manifest $manifestTemp $version $target $asset $expected)) {
            Fail "release manifest asset mismatch"
        }
        if ((Get-Sha256 $binaryTemp) -ne $expected) {
            Fail "SHA-256 verification failed for $asset"
        }
        Move-Item -LiteralPath $binaryTemp -Destination $cachedBinary -Force
        Move-Item -LiteralPath $checksumTemp -Destination $cachedChecksum -Force
        Move-Item -LiteralPath $checksumSignatureTemp -Destination $cachedChecksumSignature -Force
        Move-Item -LiteralPath $manifestTemp -Destination $cachedManifest -Force
        Move-Item -LiteralPath $manifestSignatureTemp -Destination $cachedManifestSignature -Force
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
