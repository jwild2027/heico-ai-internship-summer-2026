# download_nist_pdfs.ps1
# Downloads a curated set of publicly available NIST Special Publications
# from nvlpubs.nist.gov into a local /data/nist_pdfs/ folder.
#
# Usage:
#   .\download_nist_pdfs.ps1
#   .\download_nist_pdfs.ps1 -MaxDocs 10   # start small, ~20 min
#   .\download_nist_pdfs.ps1 -MaxDocs 50   # full set, ~100 min to ingest

param(
    [int]$MaxDocs = 10,
    [string]$OutputDir = "data\nist_pdfs"
)

# ---------------------------------------------------------------------------
# Curated list of publicly available NIST Special Publications
# All from nvlpubs.nist.gov — no auth, no cost, public domain USG works
# ---------------------------------------------------------------------------
$NIST_DOCS = @(
    @{ name="NIST-SP-800-53r5.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf" },
    @{ name="NIST-SP-800-171r2.pdf";      url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-171r2.pdf" },
    @{ name="NIST-SP-800-37r2.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-37r2.pdf" },
    @{ name="NIST-SP-800-61r2.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r2.pdf" },
    @{ name="NIST-SP-800-63b.pdf";        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-63b.pdf" },
    @{ name="NIST-SP-800-92.pdf";         url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-92.pdf" },
    @{ name="NIST-SP-800-115.pdf";        url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-115.pdf" },
    @{ name="NIST-SP-800-122.pdf";        url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-122.pdf" },
    @{ name="NIST-SP-800-137.pdf";        url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-137.pdf" },
    @{ name="NIST-SP-800-145.pdf";        url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-145.pdf" },
    @{ name="NIST-SP-800-146.pdf";        url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-146.pdf" },
    @{ name="NIST-SP-800-150.pdf";        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-150.pdf" },
    @{ name="NIST-SP-800-160v1.pdf";      url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-160v1.pdf" },
    @{ name="NIST-SP-800-181r1.pdf";      url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-181r1.pdf" },
    @{ name="NIST-SP-800-184.pdf";        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-184.pdf" },
    @{ name="NIST-SP-800-190.pdf";        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-190.pdf" },
    @{ name="NIST-SP-800-193.pdf";        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-193.pdf" },
    @{ name="NIST-SP-800-207.pdf";        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-207.pdf" },
    @{ name="NIST-SP-800-210.pdf";        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-210.pdf" },
    @{ name="NIST-SP-800-218.pdf";        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf" },
    @{ name="NIST-SP-800-219.pdf";        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-219.pdf" },
    @{ name="NIST-SP-800-226.pdf";        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-226.pdf" },
    @{ name="NIST-CSF-1.1.pdf";           url="https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.04162018.pdf" },
    @{ name="NIST-SP-800-12r1.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-12r1.pdf" },
    @{ name="NIST-SP-800-14.pdf";         url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-14.pdf" },
    @{ name="NIST-SP-800-30r1.pdf";       url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-30r1.pdf" },
    @{ name="NIST-SP-800-34r1.pdf";       url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-34r1.pdf" },
    @{ name="NIST-SP-800-39.pdf";         url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-39.pdf" },
    @{ name="NIST-SP-800-40r4.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-40r4.pdf" },
    @{ name="NIST-SP-800-41r1.pdf";       url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-41r1.pdf" },
    @{ name="NIST-SP-800-45v2.pdf";       url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-45ver2.pdf" },
    @{ name="NIST-SP-800-46r2.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-46r2.pdf" },
    @{ name="NIST-SP-800-47r1.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-47r1.pdf" },
    @{ name="NIST-SP-800-50.pdf";         url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-50.pdf" },
    @{ name="NIST-SP-800-52r2.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-52r2.pdf" },
    @{ name="NIST-SP-800-57p1r5.pdf";     url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-57pt1r5.pdf" },
    @{ name="NIST-SP-800-63-3.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-63-3.pdf" },
    @{ name="NIST-SP-800-63a.pdf";        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-63a.pdf" },
    @{ name="NIST-SP-800-63c.pdf";        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-63c.pdf" },
    @{ name="NIST-SP-800-70r4.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-70r4.pdf" },
    @{ name="NIST-SP-800-77r1.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-77r1.pdf" },
    @{ name="NIST-SP-800-82r3.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-82r3.pdf" },
    @{ name="NIST-SP-800-83r1.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-83r1.pdf" },
    @{ name="NIST-SP-800-84.pdf";         url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-84.pdf" },
    @{ name="NIST-SP-800-86.pdf";         url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-86.pdf" },
    @{ name="NIST-SP-800-88r1.pdf";       url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-88r1.pdf" },
    @{ name="NIST-SP-800-94.pdf";         url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-94.pdf" },
    @{ name="NIST-SP-800-100.pdf";        url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-100.pdf" },
    @{ name="NIST-SP-800-111.pdf";        url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-111.pdf" },
    @{ name="NIST-SP-800-113.pdf";        url="https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-113.pdf" }
)

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
$selected = $NIST_DOCS | Select-Object -First $MaxDocs

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
Write-Host ""
Write-Host "Downloading $($selected.Count) NIST PDFs to '$OutputDir'" -ForegroundColor Cyan
Write-Host "This may take a few minutes depending on your connection." -ForegroundColor Yellow
Write-Host ""

$downloaded = 0
$failed     = 0
$skipped    = 0

foreach ($doc in $selected) {
    $dest = Join-Path $OutputDir $doc.name

    if (Test-Path $dest) {
        Write-Host "  [SKIP] $($doc.name) already exists" -ForegroundColor DarkGray
        $skipped++
        continue
    }

    Write-Host "  [DOWN] $($doc.name)..." -NoNewline
    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $doc.url -OutFile $dest -UseBasicParsing -TimeoutSec 60
        $size = [math]::Round((Get-Item $dest).Length / 1MB, 1)
        Write-Host " OK ($size MB)" -ForegroundColor Green
        $downloaded++
    }
    catch {
        Write-Host " FAILED: $($_.Exception.Message)" -ForegroundColor Red
        if (Test-Path $dest) { Remove-Item $dest }
        $failed++
    }
}

Write-Host ""
Write-Host "Done: $downloaded downloaded, $skipped skipped, $failed failed" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next step — ingest into RAG DB:" -ForegroundColor Yellow
Write-Host "  python scripts\ingest_batch.py --dir $OutputDir --db-path rag.db" -ForegroundColor White
Write-Host ""