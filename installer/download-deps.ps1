# download-deps.ps1
# Downloads YTGet's large runtime dependencies (yt-dlp, ffmpeg, ffprobe,
# PhantomJS, Deno, spotDL) into the application folder after install.
# Run by the Windows installer (setup.iss) as a post-install step, and
# safe to re-run manually (e.g. from the "Check for Updates" flow) since
# every step skips work when a valid target file already exists.

param(
    [Parameter(Mandatory = $true)]
    [string]$TargetDir
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # speeds up Invoke-WebRequest a lot

function Write-Status($msg) {
    Write-Host "[YTGet setup] $msg"
}

function Test-ValidExe($path) {
    return (Test-Path $path) -and ((Get-Item $path).Length -gt 0)
}

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
$tmp = Join-Path $env:TEMP "ytget-deps-$(Get-Random)"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

try {
    # ---- yt-dlp ------------------------------------------------------
    $ytDlpPath = Join-Path $TargetDir "yt-dlp.exe"
    if (-not (Test-ValidExe $ytDlpPath)) {
        Write-Status "Downloading yt-dlp..."
        Invoke-WebRequest -Uri "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -OutFile $ytDlpPath
    } else {
        Write-Status "yt-dlp already present, skipping."
    }

    # ---- ffmpeg + ffprobe ---------------------------------------------
    $ffmpegPath  = Join-Path $TargetDir "ffmpeg.exe"
    $ffprobePath = Join-Path $TargetDir "ffprobe.exe"
    if (-not (Test-ValidExe $ffmpegPath) -or -not (Test-ValidExe $ffprobePath)) {
        Write-Status "Downloading ffmpeg (includes ffprobe)..."
        $ffmpegZip = Join-Path $tmp "ffmpeg.zip"
        Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $ffmpegZip
        $ffmpegExtract = Join-Path $tmp "ffmpeg_extract"
        Expand-Archive -Path $ffmpegZip -DestinationPath $ffmpegExtract -Force
        $foundFfmpeg  = Get-ChildItem -Recurse -Path $ffmpegExtract -Filter "ffmpeg.exe"  | Select-Object -First 1
        $foundFfprobe = Get-ChildItem -Recurse -Path $ffmpegExtract -Filter "ffprobe.exe" | Select-Object -First 1
        if ($foundFfmpeg)  { Copy-Item $foundFfmpeg.FullName  $ffmpegPath  -Force }
        if ($foundFfprobe) { Copy-Item $foundFfprobe.FullName $ffprobePath -Force }
    } else {
        Write-Status "ffmpeg/ffprobe already present, skipping."
    }

    # ---- PhantomJS ------------------------------------------------------
    $phantomPath = Join-Path $TargetDir "phantomjs.exe"
    if (-not (Test-ValidExe $phantomPath)) {
        Write-Status "Downloading PhantomJS..."
        $phantomZip = Join-Path $tmp "phantomjs.zip"
        Invoke-WebRequest -Uri "https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-2.1.1-windows.zip" -OutFile $phantomZip
        $phantomExtract = Join-Path $tmp "phantomjs_extract"
        Expand-Archive -Path $phantomZip -DestinationPath $phantomExtract -Force
        $foundPhantom = Get-ChildItem -Recurse -Path $phantomExtract -Filter "phantomjs.exe" | Select-Object -First 1
        if ($foundPhantom) { Copy-Item $foundPhantom.FullName $phantomPath -Force }
    } else {
        Write-Status "PhantomJS already present, skipping."
    }

    # ---- Deno ------------------------------------------------------------
    $denoPath = Join-Path $TargetDir "deno.exe"
    if (-not (Test-ValidExe $denoPath)) {
        Write-Status "Downloading Deno..."
        $denoZip = Join-Path $tmp "deno.zip"
        Invoke-WebRequest -Uri "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip" -OutFile $denoZip
        $denoExtract = Join-Path $tmp "deno_extract"
        Expand-Archive -Path $denoZip -DestinationPath $denoExtract -Force
        $foundDeno = Get-ChildItem -Recurse -Path $denoExtract -Filter "deno.exe" | Select-Object -First 1
        if ($foundDeno) { Copy-Item $foundDeno.FullName $denoPath -Force }
    } else {
        Write-Status "Deno already present, skipping."
    }

    # ---- spotDL ------------------------------------------------------------
    $spotdlPath = Join-Path $TargetDir "spotdl.exe"
    if (-not (Test-ValidExe $spotdlPath)) {
        Write-Status "Downloading spotDL..."
        Invoke-WebRequest -Uri "https://github.com/spotDL/spotify-downloader/releases/download/v4.5.0/spotdl-4.5.0-win32.exe" -OutFile $spotdlPath
    } else {
        Write-Status "spotDL already present, skipping."
    }

    Write-Status "All dependencies are ready."
}
catch {
    Write-Warning "One or more dependencies failed to download: $_"
    Write-Warning "YTGet will still launch — missing tools can be retried later via Help > Check for Updates, or by re-running this script:"
    Write-Warning "  powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -TargetDir `"$TargetDir`""
    # Exit 0 so the installer doesn't report a hard failure over a flaky download;
    # the app already degrades gracefully when a binary is missing (see settings.py).
    exit 0
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
