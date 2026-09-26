$start = 554
$end = 888
$total = $end - $start + 1

for ($i = $start; $i -le $end; $i++) {
    # 1. Total overall progress calculation
    $overallPercent = [math]::Round((($i - $start) / $total) * 100)
    Write-Progress -Id 1 -Activity "Overall Progress" -Status "Dumped $i of $end revisions ($overallPercent%)" -PercentComplete $overallPercent
    
    # 2. Setup the nested sub-progress bar
    Write-Progress -Id 2 -ParentId 1 -Activity "Current Revision: $i" -Status "Starting dump..." -PercentComplete 0
    
    # 3. Stream svnadmin progress lines into the sub-progress bar
    # 2>&1 redirects stderr (where svnadmin writes its progress text) to stdout
    $dumpFile = "D:\VisualSVN_Backups\cnc_mcc\rev_$($i.ToString('000')).dmp"
    
    & svnadmin dump cnc_mcc -r $i --incremental -M 256 2>&1 > $dumpFile | ForEach-Object {
        $line = $_.ToString().Trim()
        if ($line -match "Dumped revision (\d+)") {
            Write-Progress -Id 2 -ParentId 1 -Activity "Current Revision: $i" -Status "Finalizing revision dump..." -PercentComplete 90
        } elseif ($line) {
            # Display whatever text svnadmin outputs (e.g., paths being dumped)
            Write-Progress -Id 2 -ParentId 1 -Activity "Current Revision: $i" -Status $line -PercentComplete 50
        }
    }
    
    # Complete the sub-bar for this revision
    Write-Progress -Id 2 -ParentId 1 -Activity "Current Revision: $i" -Status "Done!" -PercentComplete 100
}
