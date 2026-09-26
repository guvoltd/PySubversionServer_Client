$start = 0
$end = 161
$total = $end - $start + 1
$repoPath = "E:\svn_mcc\REPOS\software_mcc"  # CHANGE THIS to your actual repo path
$outputDir = "D:\VisualSVN_Backups\software_mcc"  # CHANGE THIS to where you want dump files

# Create output directory if it doesn't exist
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force
}

for ($i = $start; $i -le $end; $i++) {
    $fileName = Join-Path $outputDir "rev_$($i.ToString('000')).dmp"
    $revisionNumber = $i - $start + 1
    
    Write-Host "Starting revision $i ($revisionNumber of $total)..." -ForegroundColor Yellow
    
    # Start the dump process in background with full paths
    $job = Start-Job -ScriptBlock {
        param($rev, $outputFile, $repo)
        $cmd = "svnadmin dump `"$repo`" -r $rev --incremental -M 256 > `"$outputFile`""
        cmd.exe /c $cmd
    } -ArgumentList $i, $fileName, $repoPath
    
    # Monitor the file size in real-time
    $lastSize = 0
    $lastUpdate = Get-Date
    
    while ($job.State -eq 'Running') {
        Start-Sleep -Milliseconds 200
        
        if (Test-Path $fileName) {
            $currentSize = (Get-Item $fileName).Length
            $currentTime = Get-Date
            
            # Calculate dump speed
            $timeDiff = ($currentTime - $lastUpdate).TotalSeconds
            $sizeDiff = $currentSize - $lastSize
            
            if ($timeDiff -gt 0 -and $sizeDiff -gt 0) {
                $speed = $sizeDiff / $timeDiff / 1KB  # KB/s
                
                # Calculate estimated percentage
                # Adjust the multiplier based on your average revision size
                $percent = [math]::Min(99, [math]::Round(($currentSize / 1MB) * 2))
                
                Write-Progress -Activity "Dumping SVN Revisions" `
                    -Status "Revision $i ($revisionNumber of $total) - Size: $([math]::Round($currentSize/1KB, 1))KB - Speed: $([math]::Round($speed, 1))KB/s" `
                    -PercentComplete $percent `
                    -Id 1
                    
                $lastSize = $currentSize
                $lastUpdate = $currentTime
            } elseif ($currentSize -gt 0 -and $lastSize -eq 0) {
                # File just appeared, update display
                Write-Progress -Activity "Dumping SVN Revisions" `
                    -Status "Revision $i ($revisionNumber of $total) - Starting dump..." `
                    -PercentComplete 1 `
                    -Id 1
                $lastSize = $currentSize
                $lastUpdate = $currentTime
            }
        }
    }
    
    # Check for errors in the job
    $jobOutput = Receive-Job -Job $job
    if ($jobOutput) {
        Write-Host "Warning/Error for revision $i : $jobOutput" -ForegroundColor Red
    }
    Remove-Job -Job $job
    
    # Show 100% for completed revision
    if (Test-Path $fileName) {
        $finalSize = (Get-Item $fileName).Length
        if ($finalSize -gt 0) {
            Write-Progress -Activity "Dumping SVN Revisions" `
                -Status "Revision $i Complete ($revisionNumber of $total) - Final Size: $([math]::Round($finalSize/1KB, 1))KB" `
                -PercentComplete 100 `
                -Id 1
        } else {
            Write-Host "Warning: Revision $i produced empty dump (might be normal for empty revisions)" -ForegroundColor Yellow
            Write-Progress -Activity "Dumping SVN Revisions" `
                -Status "Revision $i Complete ($revisionNumber of $total) - Empty revision" `
                -PercentComplete 100 `
                -Id 1
        }
    }
    
    Start-Sleep -Milliseconds 300
}

Write-Host "`nDump completed!" -ForegroundColor Green