# per_test_coverage_helper.ps1
param(
    [string]$Mode = 'sample', # estimate | sample | batch | full
    [int]$SampleSize = 10,
    [int]$BatchSize = 10,
    [string]$TestPath = 'tests/unit'
)

$env:PYTHONPATH = 'src'
if (-not (Get-Command mayapy -ErrorAction SilentlyContinue)) {
    Write-Host "WARNING: 'mayapy' was not found on PATH. Set PATH to Maya's mayapy or run these commands from Maya's mayapy binary." -ForegroundColor Yellow
    exit 1
}

# Collect test node ids
Write-Host "Collecting tests from $TestPath..."
$collected = mayapy -m pytest $TestPath --collect-only -q 2>$null | Select-String -Pattern '::' | ForEach-Object { $_.ToString().Trim() }
$nodes = $collected | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
$total = $nodes.Count
Write-Host "Discovered $total test nodes.`n"
if ($Mode -eq 'estimate') { exit 0 }

# Sample to estimate per-test runtime
function Time-TestNode($node) {
    Write-Host "Timing test: $node"
    $time = Measure-Command { mayapy -m pytest $node -q --maxfail=1 }
    return $time.TotalSeconds
}

if ($Mode -eq 'sample') {
    if ($total -eq 0) { Write-Host 'No tests found.'; exit 0 }
    $sample = if ($total -le $SampleSize) { $nodes } else { Get-Random -InputObject $nodes -Count $SampleSize }
    $times = @()
    foreach ($n in $sample) { $t = Time-TestNode $n; $times += $t }
    $avg = ($times | Measure-Object -Average).Average
    $estTotalSeconds = [math]::Round($avg * $total)
    Write-Host "Sample size: $($sample.Count). Average test time: $($avg) sec. Estimated full run: $([TimeSpan]::FromSeconds($estTotalSeconds)) (hh:mm:ss)"
    exit 0
}

# Batch mode (faster, approximate coverage by groups)
if ($Mode -eq 'batch') {
    if ($total -eq 0) { Write-Host 'No tests found.'; exit 0 }
    $batches = [System.Collections.ArrayList]::new()
    for ($i = 0; $i -lt $total; $i += $BatchSize) { $batches.Add($nodes[$i..([Math]::Min($i+$BatchSize-1,$total-1))]) }
    $i = 0
    foreach ($batch in $batches) {
        $i++
        Write-Host "Running batch $i/$($batches.Count) with $($batch.Count) tests"
        $tmpFile = "tests/_batch_$i.txt"
        $batch | Set-Content $tmpFile
        # Run the batch with coverage once (faster than one mayapy per test)
        mayapy -m coverage run --source=src -m pytest --maxfail=1 --disable-warnings -q --pyargs -k "$($batch -join ' or ')"
        # Save batch coverage
        Rename-Item -Path .coverage -NewName ".coverage.batch.$i" -ErrorAction SilentlyContinue
        Remove-Item $tmpFile -ErrorAction SilentlyContinue
    }
    mayapy -m coverage combine
    mayapy -m coverage html -d build/coverage_batch_html
    Write-Host "Batch coverage html generated at build/coverage_batch_html/index.html"
    exit 0
}

# Full per-test coverage (REQUIRES explicit confirmation)
if ($Mode -eq 'full') {
    if ($total -eq 0) { Write-Host 'No tests found.'; exit 0 }
    # Quick sample to estimate runtime before asking
    $sampleCount = [Math]::Min(10, $total)
    $sample = if ($total -le $sampleCount) { $nodes } else { Get-Random -InputObject $nodes -Count $sampleCount }
    $times = @()
    foreach ($n in $sample) { $t = Time-TestNode $n; $times += $t }
    $avg = ($times | Measure-Object -Average).Average
    $estTotalSeconds = [math]::Round($avg * $total)
    $estTimespan = [TimeSpan]::FromSeconds($estTotalSeconds)
    Write-Host "Estimated full per-test run time: $estTimespan (for $total tests)."
    Write-Host "This will start mayapy $total times and may take a long time and significant CPU."
    $confirm = Read-Host "Type YES to proceed with full per-test coverage (or anything else to abort)"
    if ($confirm -ne 'YES') { Write-Host 'Aborting full run.'; exit 1 }

    # Proceed: run each test individually and store .coverage files
    $idx = 0
    foreach ($node in $nodes) {
        $idx++
        Write-Host "($idx/$total) Running test: $node"
        Remove-Item .coverage -ErrorAction SilentlyContinue
        mayapy -m coverage run --source=src -m pytest $node -q --maxfail=1
        $safeName = ($node -replace '[\\/:<>|*?"\s]','_')
        Rename-Item -Path .coverage -NewName ".coverage.$safeName" -ErrorAction SilentlyContinue
    }
    mayapy -m coverage combine
    mayapy -m coverage html -d build/coverage_per_test_html
    Write-Host "Per-test coverage html generated at build/coverage_per_test_html/index.html"
    exit 0
}

Write-Host "Unknown mode: $Mode. Choose estimate|sample|batch|full"
