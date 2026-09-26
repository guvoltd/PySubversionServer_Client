# --- CONFIGURATION (defaults; overridden by backup_tool_config.json if present) ---
# $RepoRoot   = "E:\svn_mcc\REPOS"          # Path to your VisualSVN repositories
# $BackupDir  = "D:\VisualSVN_Backups"      # Where to save the output ZIPs
# $RestoreDir = "D:\VisualSVN_Restore"      # Where repositories get restored to (never restores over $RepoRoot automatically)
# $ConfigFile = Join-Path $PSScriptRoot "backup_tool_config.json"

$RepoRoot   = "/svn"          # Path to your VisualSVN repositories
$BackupDir  = "/home/svn/testSvn"      # Where to save the output ZIPs
$RestoreDir = "/home/svn/repos"      # Where repositories get restored to (never restores over $RepoRoot automatically)
$PSScriptRoot  = "/home/svn"
$ConfigFile = Join-Path $PSScriptRoot "backup_tool_config.json"

# ---------------------

function Load-Config {
    if (Test-Path $ConfigFile) {
        try {
            $cfg = Get-Content -Path $ConfigFile -Raw | ConvertFrom-Json
            if ($cfg.RepoRoot)   { $script:RepoRoot = $cfg.RepoRoot }
            if ($cfg.BackupDir)  { $script:BackupDir = $cfg.BackupDir }
            if ($cfg.RestoreDir) { $script:RestoreDir = $cfg.RestoreDir }
        } catch {
            Write-Warning "Failed to read $ConfigFile, using defaults. Error: $_"
        }
    }
}

function Save-Config {
    $cfg = [ordered]@{
        RepoRoot   = $RepoRoot
        BackupDir  = $BackupDir
        RestoreDir = $RestoreDir
    }
    $cfg | ConvertTo-Json | Set-Content -Path $ConfigFile -Encoding UTF8
}

function Get-RepoList {
    if (-not (Test-Path $RepoRoot)) {
        Write-Warning "Repo root '$RepoRoot' does not exist."
        return @()
    }
    return @(Get-ChildItem -Path $RepoRoot | Where-Object { $_.PSIsContainer } | Select-Object -ExpandProperty Name)
}

function Get-BackupList {
    if (-not (Test-Path $BackupDir)) {
        Write-Warning "Backup dir '$BackupDir' does not exist."
        return @()
    }
    return @(Get-ChildItem -Path $BackupDir -Filter "*_backup.zip" | Select-Object -ExpandProperty Name)
}

function Select-Items {
    param(
        [string[]]$Items,
        [string]$Prompt = "Enter numbers separated by commas, or 'all'"
    )
    if ($Items.Count -eq 0) {
        Write-Host "Nothing to select." -ForegroundColor Yellow
        return @()
    }
    for ($i = 0; $i -lt $Items.Count; $i++) {
        Write-Host "  [$($i + 1)] $($Items[$i])"
    }
    $sel = Read-Host $Prompt
    if ($sel.Trim().ToLower() -eq 'all') { return $Items }

    $indices = $sel -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ - 1 }
    $picked = @()
    foreach ($idx in $indices) {
        if ($idx -ge 0 -and $idx -lt $Items.Count) { $picked += $Items[$idx] }
    }
    return $picked
}

function Backup-OneRepo {
    param([Parameter(Mandatory)][string]$RepoName)

    $RepoPath = Join-Path $RepoRoot $RepoName
    Write-Host "Processing repository: $RepoName..." -ForegroundColor Cyan

    $TempRepoDir = Join-Path $BackupDir "Temp_$RepoName"
    $DumpFile = Join-Path $TempRepoDir "$RepoName.dump"
    $ZipFile = Join-Path $BackupDir "$RepoName`_backup.zip"
    $TempZipFile = Join-Path $BackupDir "$RepoName`_backup.tmp.zip"

    if (Test-Path $TempRepoDir) { Remove-Item -Recurse -Force $TempRepoDir }
    New-Item -ItemType Directory -Path $TempRepoDir | Out-Null

    $success = $false
    try {
        # Task 1: Automate repository dump.
        # Piped through cmd.exe's raw '>' redirect (not Out-File) so binary
        # delta content in the dump is never reinterpreted as text.
        Write-Host "Creating SVN dump..." -ForegroundColor Yellow
        cmd.exe /c "svnadmin dump `"$RepoPath`" --deltas > `"$DumpFile`"" 2>$null
        if ($LASTEXITCODE -ne 0) { throw "svnadmin dump exited with code $LASTEXITCODE" }

        # Task 2: Gather repository-specific and global auth/config files.
        Write-Host "Gathering configuration files..." -ForegroundColor Yellow

        $ConfSrc = Join-Path $RepoPath "conf"
        if (Test-Path $ConfSrc) {
            Copy-Item -Path $ConfSrc -Destination (Join-Path $TempRepoDir "conf") -Recurse -Force
        }
        $HooksSrc = Join-Path $RepoPath "hooks"
        if (Test-Path $HooksSrc) {
            Copy-Item -Path $HooksSrc -Destination (Join-Path $TempRepoDir "hooks") -Recurse -Force
        }

        $GlobalAuthz = Join-Path $RepoRoot "authz"
        $GlobalHtpasswd = Join-Path $RepoRoot "htpasswd"
        $GlobalGroups = Join-Path $RepoRoot "groups.conf"
        if (Test-Path $GlobalAuthz) { Copy-Item $GlobalAuthz -Destination $TempRepoDir }
        if (Test-Path $GlobalHtpasswd) { Copy-Item $GlobalHtpasswd -Destination $TempRepoDir }
        if (Test-Path $GlobalGroups) { Copy-Item $GlobalGroups -Destination $TempRepoDir }

        # Compress to a temp name first, then swap over the previous ZIP only
        # once the new archive is confirmed good -- keeps a valid backup on
        # disk at all times even if this run fails partway.
        Write-Host "Compressing into ZIP archive..." -ForegroundColor Green
        if (Test-Path $TempZipFile) { Remove-Item -Force $TempZipFile }
        Compress-Archive -Path "$TempRepoDir\*" -DestinationPath $TempZipFile -Force
        if (Test-Path $ZipFile) { Remove-Item -Force $ZipFile }
        Move-Item -Path $TempZipFile -Destination $ZipFile -Force

        $success = $true
        Write-Host "Backup complete: $ZipFile" -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to back up $RepoName. Error: $_"
        if (Test-Path $TempZipFile) { Remove-Item -Force $TempZipFile }
    }
    finally {
        if (Test-Path $TempRepoDir) { Remove-Item -Recurse -Force $TempRepoDir }
    }
    return $success
}

# --- Incremental backup: tracks the last-dumped revision per repo in a JSON
# state file (same technique as the standalone svn_incremental_bkup.py
# script) so each run only dumps revisions committed since the last run. ---

function Get-IncrementalStateFile {
    return (Join-Path $BackupDir "incremental_state.json")
}

function Load-IncrementalState {
    $path = Get-IncrementalStateFile
    $state = @{}
    if (Test-Path $path) {
        try {
            $obj = Get-Content -Path $path -Raw | ConvertFrom-Json
            foreach ($prop in $obj.PSObject.Properties) { $state[$prop.Name] = [int]$prop.Value }
        } catch {
            Write-Warning "Failed to read $path, starting with empty incremental state. Error: $_"
        }
    }
    return $state
}

function Save-IncrementalState {
    param([Parameter(Mandatory)][hashtable]$State)
    if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null }
    $State | ConvertTo-Json | Set-Content -Path (Get-IncrementalStateFile) -Encoding UTF8
}

function Get-LastIncrementalRevision {
    param([Parameter(Mandatory)][string]$RepoName)
    $state = Load-IncrementalState
    if ($state.ContainsKey($RepoName)) { return [int]$state[$RepoName] }
    return 0
}

function Set-LastIncrementalRevision {
    param([Parameter(Mandatory)][string]$RepoName, [Parameter(Mandatory)][int]$Revision)
    $state = Load-IncrementalState
    $state[$RepoName] = $Revision
    Save-IncrementalState -State $state
}

function Get-YoungestRevision {
    param([Parameter(Mandatory)][string]$RepoPath)
    $out = & svnlook youngest $RepoPath 2>$null
    if ($LASTEXITCODE -ne 0) { return -1 }
    $rev = ($out | Select-Object -First 1).Trim()
    if ($rev -match '^\d+$') { return [int]$rev }
    return -1
}

function Backup-IncrementalOneRepo {
    param([Parameter(Mandatory)][string]$RepoName)

    $RepoPath = Join-Path $RepoRoot $RepoName
    if (-not (Test-Path $RepoPath)) {
        Write-Error "Repository path not found: $RepoPath"
        return $false
    }

    $lastRev = Get-LastIncrementalRevision -RepoName $RepoName
    $youngest = Get-YoungestRevision -RepoPath $RepoPath
    if ($youngest -eq -1) {
        Write-Error "Could not determine youngest revision for $RepoName (is it a valid SVN repo?)."
        return $false
    }

    if ($youngest -le $lastRev) {
        Write-Host "No new revisions for $RepoName (last backed up: r$lastRev, youngest: r$youngest)." -ForegroundColor DarkYellow
        return $true
    }

    $startRev = $lastRev + 1
    $endRev = $youngest
    Write-Host "Incremental backup for $RepoName : revisions $startRev-$endRev..." -ForegroundColor Cyan

    $repoIncrDir = Join-Path (Join-Path $BackupDir "Incremental") $RepoName
    if (-not (Test-Path $repoIncrDir)) { New-Item -ItemType Directory -Path $repoIncrDir -Force | Out-Null }

    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $chunkFile = Join-Path $repoIncrDir "rev_${startRev}-${endRev}_$timestamp.dump"

    $success = $false
    try {
        # Raw cmd.exe redirect (not Out-File) to keep dump bytes intact -- see Backup-OneRepo.
        cmd.exe /c "svnadmin dump `"$RepoPath`" --incremental -r ${startRev}:${endRev} > `"$chunkFile`"" 2>$null
        if ($LASTEXITCODE -ne 0) { throw "svnadmin dump exited with code $LASTEXITCODE" }
        if (-not (Test-Path $chunkFile) -or (Get-Item $chunkFile).Length -eq 0) { throw "Incremental dump produced an empty file." }

        # Only advance the watermark after a confirmed-good dump, so a failed
        # run is safely retried from the same start revision next time.
        Set-LastIncrementalRevision -RepoName $RepoName -Revision $endRev
        $success = $true
        Write-Host "Incremental backup complete: $chunkFile (r$startRev`:$endRev)" -ForegroundColor Green
    }
    catch {
        Write-Error "Incremental backup failed for $RepoName. Error: $_"
        if (Test-Path $chunkFile) { Remove-Item -Force $chunkFile }
    }
    return $success
}

function Restore-OneRepo {
    param(
        [Parameter(Mandatory)][string]$BackupZipName,
        [Parameter(Mandatory)][string]$TargetPath
    )

    $ZipPath = Join-Path $BackupDir $BackupZipName
    if (-not (Test-Path $ZipPath)) {
        Write-Error "Backup file not found: $ZipPath"
        return $false
    }

    $RepoName = $BackupZipName -replace '_backup\.zip$', ''
    $ExtractDir = Join-Path $BackupDir "Restore_Temp_$RepoName"
    if (Test-Path $ExtractDir) { Remove-Item -Recurse -Force $ExtractDir }
    New-Item -ItemType Directory -Path $ExtractDir | Out-Null

    $success = $false
    $keepGlobalFiles = $false
    try {
        Write-Host "Extracting backup for $RepoName..." -ForegroundColor Yellow
        Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force

        $DumpFile = Join-Path $ExtractDir "$RepoName.dump"
        if (-not (Test-Path $DumpFile)) { throw "Dump file not found inside backup: $DumpFile" }

        if (Test-Path $TargetPath) {
            Write-Warning "Target path '$TargetPath' already exists."
            $confirm = Read-Host "Type 'YES' to delete it and restore fresh, anything else to cancel"
            if ($confirm -ne 'YES') { throw "Restore cancelled by user." }
            Remove-Item -Recurse -Force $TargetPath
        }

        Write-Host "Creating repository at $TargetPath..." -ForegroundColor Yellow
        & svnadmin create $TargetPath
        if ($LASTEXITCODE -ne 0) { throw "svnadmin create exited with code $LASTEXITCODE" }

        Write-Host "Loading dump into repository..." -ForegroundColor Yellow
        cmd.exe /c "type `"$DumpFile`" | svnadmin load `"$TargetPath`""
        if ($LASTEXITCODE -ne 0) { throw "svnadmin load exited with code $LASTEXITCODE" }

        $ConfSrc = Join-Path $ExtractDir "conf"
        if (Test-Path $ConfSrc) {
            Copy-Item -Path "$ConfSrc\*" -Destination (Join-Path $TargetPath "conf") -Recurse -Force
        }
        $HooksSrc = Join-Path $ExtractDir "hooks"
        if (Test-Path $HooksSrc) {
            Copy-Item -Path "$HooksSrc\*" -Destination (Join-Path $TargetPath "hooks") -Recurse -Force
        }

        $globalNames = @('authz', 'htpasswd', 'groups.conf') | Where-Object { Test-Path (Join-Path $ExtractDir $_) }
        if ($globalNames.Count -gt 0) {
            Write-Host "Note: backup also contains server-wide file(s) ($($globalNames -join ','))." -ForegroundColor Yellow
            Write-Host "These affect the whole SVN server, so they are NOT applied automatically." -ForegroundColor Yellow
            Write-Host "Left for manual review in: $ExtractDir" -ForegroundColor Yellow
            $keepGlobalFiles = $true
        }

        $success = $true
        Write-Host "Restore complete: $RepoName -> $TargetPath" -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to restore $RepoName. Error: $_"
    }
    finally {
        if ($keepGlobalFiles) {
            Get-ChildItem -Path $ExtractDir | Where-Object { $_.Name -notin @('authz', 'htpasswd', 'groups.conf') } | Remove-Item -Recurse -Force
        } elseif (Test-Path $ExtractDir) {
            Remove-Item -Recurse -Force $ExtractDir
        }
    }
    return $success
}

function Verify-OneBackup {
    param([Parameter(Mandatory)][string]$BackupZipName)

    $ZipPath = Join-Path $BackupDir $BackupZipName
    if (-not (Test-Path $ZipPath)) {
        Write-Error "Backup file not found: $ZipPath"
        return $false
    }

    $RepoName = $BackupZipName -replace '_backup\.zip$', ''
    $ExtractDir = Join-Path $BackupDir "Verify_Temp_$RepoName"
    $TestRepoPath = Join-Path $BackupDir "Verify_TestRepo_$RepoName"
    if (Test-Path $ExtractDir) { Remove-Item -Recurse -Force $ExtractDir }
    if (Test-Path $TestRepoPath) { Remove-Item -Recurse -Force $TestRepoPath }
    New-Item -ItemType Directory -Path $ExtractDir | Out-Null

    $success = $false
    try {
        Write-Host "Verifying $RepoName..." -ForegroundColor Cyan
        Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force

        $DumpFile = Join-Path $ExtractDir "$RepoName.dump"
        if (-not (Test-Path $DumpFile)) { throw "Dump file missing from archive." }
        if ((Get-Item $DumpFile).Length -eq 0) { throw "Dump file is empty (0 bytes)." }

        & svnadmin create $TestRepoPath
        if ($LASTEXITCODE -ne 0) { throw "svnadmin create exited with code $LASTEXITCODE" }

        cmd.exe /c "type `"$DumpFile`" | svnadmin load `"$TestRepoPath`"" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "svnadmin load reported errors (exit code $LASTEXITCODE) -- backup is not cleanly loadable." }

        Write-Host "VERIFIED OK: $RepoName is structurally valid and loadable." -ForegroundColor Green
        $success = $true
    }
    catch {
        Write-Error "VERIFICATION FAILED for $RepoName. Error: $_"
    }
    finally {
        if (Test-Path $ExtractDir) { Remove-Item -Recurse -Force $ExtractDir }
        if (Test-Path $TestRepoPath) { Remove-Item -Recurse -Force $TestRepoPath }
    }
    return $success
}

function Invoke-FullBackup {
    $repos = Get-RepoList
    if ($repos.Count -eq 0) { Write-Host "No repositories found under $RepoRoot" -ForegroundColor Yellow; return }
    Write-Host "`nStarting full backup of $($repos.Count) repositories...`n" -ForegroundColor Cyan
    $ok = 0; $fail = 0
    foreach ($repo in $repos) {
        if (Backup-OneRepo -RepoName $repo) { $ok++ } else { $fail++ }
    }
    Write-Host "`nFull backup finished. Success: $ok  Failed: $fail" -ForegroundColor Cyan
}

function Invoke-PartialBackup {
    $repos = Get-RepoList
    Write-Host "`nSelect repositories to back up:" -ForegroundColor Cyan
    $picked = Select-Items -Items $repos
    if ($picked.Count -eq 0) { Write-Host "No repositories selected." -ForegroundColor Yellow; return }
    $ok = 0; $fail = 0
    foreach ($repo in $picked) {
        if (Backup-OneRepo -RepoName $repo) { $ok++ } else { $fail++ }
    }
    Write-Host "`nPartial backup finished. Success: $ok  Failed: $fail" -ForegroundColor Cyan
}

function Invoke-IncrementalBackupAll {
    $repos = Get-RepoList
    if ($repos.Count -eq 0) { Write-Host "No repositories found under $RepoRoot" -ForegroundColor Yellow; return }
    Write-Host "`nContinuing incremental backup for $($repos.Count) repositories...`n" -ForegroundColor Cyan
    $updated = 0; $upToDate = 0; $fail = 0
    foreach ($repo in $repos) {
        $before = Get-LastIncrementalRevision -RepoName $repo
        if (Backup-IncrementalOneRepo -RepoName $repo) {
            if ((Get-LastIncrementalRevision -RepoName $repo) -eq $before) { $upToDate++ } else { $updated++ }
        } else { $fail++ }
    }
    Write-Host "`nIncremental backup (all) finished. Updated: $updated  Up-to-date: $upToDate  Failed: $fail" -ForegroundColor Cyan
}

function Invoke-IncrementalBackupPartial {
    $repos = Get-RepoList
    Write-Host "`nSelect repositories to continue incremental backup:" -ForegroundColor Cyan
    $picked = Select-Items -Items $repos
    if ($picked.Count -eq 0) { Write-Host "No repositories selected." -ForegroundColor Yellow; return }
    $updated = 0; $upToDate = 0; $fail = 0
    foreach ($repo in $picked) {
        $before = Get-LastIncrementalRevision -RepoName $repo
        if (Backup-IncrementalOneRepo -RepoName $repo) {
            if ((Get-LastIncrementalRevision -RepoName $repo) -eq $before) { $upToDate++ } else { $updated++ }
        } else { $fail++ }
    }
    Write-Host "`nIncremental backup (selected) finished. Updated: $updated  Up-to-date: $upToDate  Failed: $fail" -ForegroundColor Cyan
}

function Invoke-FullRestore {
    $backups = Get-BackupList
    if ($backups.Count -eq 0) { Write-Host "No backups found in $BackupDir" -ForegroundColor Yellow; return }

    Write-Host "`nThis will restore ALL $($backups.Count) backup(s) into: $RestoreDir" -ForegroundColor Cyan
    $confirm = Read-Host "Type 'YES' to continue"
    if ($confirm -ne 'YES') { Write-Host "Cancelled."; return }
    if (-not (Test-Path $RestoreDir)) { New-Item -ItemType Directory -Path $RestoreDir | Out-Null }

    $ok = 0; $fail = 0
    foreach ($zip in $backups) {
        $repoName = $zip -replace '_backup\.zip$', ''
        $target = Join-Path $RestoreDir $repoName
        if (Restore-OneRepo -BackupZipName $zip -TargetPath $target) { $ok++ } else { $fail++ }
    }
    Write-Host "`nFull restore finished. Success: $ok  Failed: $fail" -ForegroundColor Cyan
}

function Invoke-PartialRestore {
    $backups = Get-BackupList
    Write-Host "`nSelect backups to restore:" -ForegroundColor Cyan
    $picked = Select-Items -Items $backups
    if ($picked.Count -eq 0) { Write-Host "No backups selected." -ForegroundColor Yellow; return }
    if (-not (Test-Path $RestoreDir)) { New-Item -ItemType Directory -Path $RestoreDir | Out-Null }

    $ok = 0; $fail = 0
    foreach ($zip in $picked) {
        $repoName = $zip -replace '_backup\.zip$', ''
        $defaultTarget = Join-Path $RestoreDir $repoName
        $custom = Read-Host "Restore path for $repoName [default: $defaultTarget]"
        $target = if ([string]::IsNullOrWhiteSpace($custom)) { $defaultTarget } else { $custom }
        if (Restore-OneRepo -BackupZipName $zip -TargetPath $target) { $ok++ } else { $fail++ }
    }
    Write-Host "`nPartial restore finished. Success: $ok  Failed: $fail" -ForegroundColor Cyan
}

function Invoke-VerifyBackup {
    $backups = Get-BackupList
    if ($backups.Count -eq 0) { Write-Host "No backups found in $BackupDir" -ForegroundColor Yellow; return }
    Write-Host "`nSelect backups to verify:" -ForegroundColor Cyan
    $picked = Select-Items -Items $backups
    if ($picked.Count -eq 0) { Write-Host "No backups selected." -ForegroundColor Yellow; return }

    $ok = 0; $fail = 0
    foreach ($zip in $picked) {
        if (Verify-OneBackup -BackupZipName $zip) { $ok++ } else { $fail++ }
    }
    Write-Host "`nVerification finished. Passed: $ok  Failed: $fail" -ForegroundColor Cyan
}

function Invoke-PathChange {
    Write-Host "`nCurrent paths:" -ForegroundColor Cyan
    Write-Host "  Repo Root   : $RepoRoot"
    Write-Host "  Backup Dir  : $BackupDir"
    Write-Host "  Restore Dir : $RestoreDir"
    Write-Host ""

    $newRepoRoot = Read-Host "New Repo Root (blank to keep current)"
    $newBackupDir = Read-Host "New Backup Dir (blank to keep current)"
    $newRestoreDir = Read-Host "New Restore Dir (blank to keep current)"

    if (-not [string]::IsNullOrWhiteSpace($newRepoRoot)) {
        if (-not (Test-Path $newRepoRoot)) {
            Write-Warning "Path '$newRepoRoot' does not exist. Repo Root not changed."
        } else {
            $script:RepoRoot = $newRepoRoot
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($newBackupDir)) {
        if (-not (Test-Path $newBackupDir)) {
            $create = Read-Host "Backup Dir '$newBackupDir' does not exist. Create it? (Y/N)"
            if ($create -match '^[Yy]') {
                New-Item -ItemType Directory -Path $newBackupDir -Force | Out-Null
                $script:BackupDir = $newBackupDir
            } else {
                Write-Warning "Backup Dir not changed."
            }
        } else {
            $script:BackupDir = $newBackupDir
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($newRestoreDir)) {
        if (-not (Test-Path $newRestoreDir)) {
            New-Item -ItemType Directory -Path $newRestoreDir -Force | Out-Null
        }
        $script:RestoreDir = $newRestoreDir
    }

    Save-Config
    Write-Host "`nPaths updated and saved to $ConfigFile" -ForegroundColor Green
}

function Show-MenuHeader {
    Write-Host "================================================" -ForegroundColor DarkCyan
    Write-Host " VisualSVN Backup & Restore Tool" -ForegroundColor DarkCyan
    Write-Host "================================================" -ForegroundColor DarkCyan
    Write-Host " Repo Root   : $RepoRoot"
    Write-Host " Backup Dir  : $BackupDir"
    Write-Host " Restore Dir : $RestoreDir"
    Write-Host "------------------------------------------------"
    Write-Host " 1. Full Backup                    (back up all repositories)"
    Write-Host " 2. Partial Backup                 (select repositories)"
    Write-Host " 3. Continue Incremental Backup     (all repositories)"
    Write-Host " 4. Continue Incremental Backup     (select repositories)"
    Write-Host " 5. Full Restore                   (restore all backups)"
    Write-Host " 6. Partial Restore                (select backups)"
    Write-Host " 7. Verify Backup(s)"
    Write-Host " 8. Change Paths"
    Write-Host " 9. Exit"
    Write-Host "================================================" -ForegroundColor DarkCyan
}

function Start-Menu {
    Load-Config
    while ($true) {
        Show-MenuHeader
        $choice = (Read-Host "Select an option (1-9)").Trim()
        switch ($choice) {
            '1' { Invoke-FullBackup }
            '2' { Invoke-PartialBackup }
            '3' { Invoke-IncrementalBackupAll }
            '4' { Invoke-IncrementalBackupPartial }
            '5' { Invoke-FullRestore }
            '6' { Invoke-PartialRestore }
            '7' { Invoke-VerifyBackup }
            '8' { Invoke-PathChange }
            '9' { Write-Host "Goodbye." -ForegroundColor Cyan; return }
            default { Write-Host "Invalid option." -ForegroundColor Red }
        }
        if ($choice -ne '9') {
            Write-Host ""
            Read-Host "Press Enter to return to the menu" | Out-Null
            Write-Host ""
        }
    }
}

Start-Menu
