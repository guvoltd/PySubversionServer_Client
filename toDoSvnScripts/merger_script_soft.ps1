$targetFile = "software_mcc.dmp"
$testRepoPath = "E:\svn_mcc\testREpo\software_mcc"

# 1. Gather and Sort Chunk Files
$dumpFiles = Get-ChildItem "rev_*.dmp" | Sort-Object Name
if ($dumpFiles.Count -eq 0) {
    Write-Error "No rev_*.dmp files found in the current directory."
    exit
}

# 2. Calculate Total Expected Size (Sum of all parts)
$finalExpectedSize = 0
$expectedSize = 0
foreach ($file in $dumpFiles) { $finalExpectedSize += $file.Length }

Write-Host "Starting merge of $($dumpFiles.Count) files..." -ForegroundColor Cyan
if (Test-Path $targetFile) { Remove-Item $targetFile -Force }

# 3. Stream-Append Files to Avoid Memory Bloat
foreach ($file in $dumpFiles) {
    $expectedSize += $file.Length
    Write-Host "Appending $($file.Name) ($([math]::Round($file.Length / 1GB, 2)) GB)..."
    cmd /c "type `"$($file.FullName)`" >> `"$targetFile`""
	while(1){
		$currentSize = (Get-Item $targetFile).Length
        Write-Host "Current written size for Rev ${i}: ${currentSize} bytes" -ForegroundColor Gray
        
        # In a single-revision dump loop, we check if the file size is stable and matches the final write
        # To handle HDD lag, we test if the file is still actively being written/modified by the OS
        Start-Sleep -Seconds 5
        $newSize = (Get-Item $targetFile).Length
        
        if ($newSize -eq $currentSize) {
            # The HDD has completely stopped writing to this file. 
            # If it's a 0-byte file (and shouldn't be) or lower than expected, it's an error.
            if ($newSize -eq 0) {
                Write-Error "CRITICAL: Revision $i stopped writing and resulted in a 0-byte file."
                exit
            }
            Write-Host "SUCCESS: Revision $i size stabilized cleanly at ($([math]::Round($newSize / 1GB, 2)) GB)..." -ForegroundColor Green
            break
        } elseif ($newSize -gt $currentSize) {
            # The file size increased! The HDD is still catching up. Loop continues.
            Write-Host "HDD is still actively writing data. Size increased by $($newSize - $currentSize) bytes. Waiting..." -ForegroundColor Yellow
            continue
        } else {
            # The size didn't increase or somehow errored
            Write-Error "CRITICAL ERROR: HDD write stalled or failed to progress for Revision $i."
            exit
        }
	}
}

# 4. Verification Step 1: File Size Integrity Check
Clear-Variable targetFileInfo -ErrorAction SilentlyContinue
$targetFileInfo = Get-Item $targetFile
$actualSize = $targetFileInfo.Length

Write-Host "`n--- VERIFICATION 1: FILE SIZE CHECK ---" -ForegroundColor Yellow
Write-Host "Expected Total Size: $expectedSize bytes"
Write-Host "Actual Merged Size: $actualSize bytes"

if ($actualSize -eq $expectedSize) {
    Write-Host "SUCCESS: Merged file size matches the sum of individual chunks exactly!" -ForegroundColor Green
} else {
    Write-Error "CRITICAL MISMATCH: The merged file size does not match the sum of parts. File may be truncated."
    exit
}

# 5. Verification Step 2: Structural SVN Validation
Write-Host "`n--- VERIFICATION 2: SVNADMIN LOGICAL VERIFY ---" -ForegroundColor Yellow
Write-Host "Creating a temporary repository for dry-run verification..."

if (Test-Path $testRepoPath) { Remove-Item $testRepoPath -Recurse -Force }
svnadmin create $testRepoPath

Write-Host "Loading merged stream into temporary repository to check internal checksums..." -ForegroundColor Cyan
# Pipe the file stream natively into svnadmin load to check structural integrity
cmd /c "type `"$targetFile`" | svnadmin load $testRepoPath"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nSUCCESS: The merged dump file is 100% structurally valid and fully loadable!" -ForegroundColor Green
} else {
    Write-Error "CRITICAL SVN ERROR: The dump file failed internal validation checks during load."
}

# 6. Cleanup Verification Repository
Write-Host "`nCleaning up temporary testing workspace..."
if (Test-Path $testRepoPath) { Remove-Item $testRepoPath -Recurse -Force }
