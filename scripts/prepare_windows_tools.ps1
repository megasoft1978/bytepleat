$ErrorActionPreference = 'Stop'

# Keep native comparators in the runner's temporary workspace. They are CI tools,
# not Arqlet package contents.
$toolRoot = Join-Path $env:RUNNER_TEMP 'arqlet-native-tools'
$lz4Dir = Join-Path $toolRoot 'lz4-1.10.0-win64'
$archive = Join-Path $env:RUNNER_TEMP 'lz4_win64_v1_10_0.zip'
$lz4Url = 'https://github.com/lz4/lz4/releases/download/v1.10.0/lz4_win64_v1_10_0.zip'
$lz4Sha256 = '8cb562a53189dfc8a53ec12469b91f1b51a5075036061a86b55738183bf4ab74'

New-Item -ItemType Directory -Force -Path $toolRoot | Out-Null

# Chocolatey packages zstandard and gzip are known to install on the hosted
# image. Keep these separate so one failure cannot be hidden by another.
foreach ($package in @('zstandard', 'gzip')) {
    & choco install $package --yes --no-progress
    if ($LASTEXITCODE -ne 0) {
        throw "Chocolatey installation failed for $package (exit $LASTEXITCODE)"
    }
}

$maxArchiveBytes = 1000000L
$downloaded = $false
$client = [System.Net.Http.HttpClient]::new()
$client.Timeout = [TimeSpan]::FromSeconds(30)
for ($attempt = 1; $attempt -le 3; $attempt++) {
    try {
        $response = $client.GetAsync($lz4Url, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        $response.EnsureSuccessStatusCode()
        if ($response.Content.Headers.ContentLength -gt $maxArchiveBytes) {
            throw 'LZ4 release archive exceeds the 1 MB limit'
        }
        $inputStream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $outputStream = [System.IO.File]::Create($archive)
        $buffer = [byte[]]::new(65536)
        $totalBytes = 0L
        while (($read = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $totalBytes += $read
            if ($totalBytes -gt $maxArchiveBytes) {
                throw 'LZ4 release archive exceeds the 1 MB limit'
            }
            $outputStream.Write($buffer, 0, $read)
        }
        $outputStream.Dispose()
        $inputStream.Dispose()
        $response.Dispose()
        $downloaded = $true
        break
    }
    catch {
        if ($outputStream) { $outputStream.Dispose(); $outputStream = $null }
        if ($inputStream) { $inputStream.Dispose(); $inputStream = $null }
        if ($response) { $response.Dispose(); $response = $null }
        if ($attempt -eq 3) { throw }
        Start-Sleep -Seconds $attempt
    }
}
$client.Dispose()
if (-not $downloaded) { throw 'Could not download the pinned LZ4 release archive' }
$actualHash = (Get-FileHash -Path $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $lz4Sha256) {
    throw "LZ4 archive SHA-256 mismatch: expected $lz4Sha256, got $actualHash"
}

if (Test-Path $lz4Dir) { Remove-Item -Recurse -Force $lz4Dir }
New-Item -ItemType Directory -Force -Path $lz4Dir | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath $lz4Dir -Force
if (-not (Test-Path (Join-Path $lz4Dir 'lz4.exe') -PathType Leaf)) {
    throw 'Pinned LZ4 archive did not contain its expected root lz4.exe'
}

# Chocolatey shims expose zstd.exe and gzip.exe. Add their directory explicitly
# to the job PATH so Python shutil.which sees them in subsequent steps.
$chocoBin = Join-Path $env:ChocolateyInstall 'bin'
if (-not (Test-Path $chocoBin -PathType Container)) {
    throw "Chocolatey shim directory is missing: $chocoBin"
}
$paths = [System.Collections.Generic.List[string]]::new()
$paths.Add($lz4Dir)
$paths.Add($chocoBin)

# The hosted image carries 7-Zip outside Chocolatey. Put the executable's
# directory on PATH for shell helpers and retain the scripts' ProgramFiles
# fallback as a second discovery route.
$sevenZip = $null
foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    if ($base) {
        $candidate = Join-Path $base '7-Zip'
        if (Test-Path (Join-Path $candidate '7z.exe') -PathType Leaf) {
            $sevenZip = $candidate
            break
        }
    }
}
if (-not $sevenZip) { throw 'The Windows runner image has no 7-Zip installation' }
$paths.Add($sevenZip)

$paths | ForEach-Object { Add-Content -Path $env:GITHUB_PATH -Value $_ }
$env:PATH = (($paths -join [System.IO.Path]::PathSeparator) + [System.IO.Path]::PathSeparator + $env:PATH)

# Fail setup now if Chocolatey did not expose the exact required tools.
foreach ($tool in @('zstd.exe', 'gzip.exe', 'lz4.exe', '7z.exe')) {
    $found = Get-Command $tool -ErrorAction SilentlyContinue
    if (-not $found) { throw "Required native comparator is not on PATH: $tool" }
    Write-Host "$tool => $($found.Source)"
}

Write-Host "LZ4 source: $lz4Url"
Write-Host "LZ4 archive SHA-256: $actualHash"
