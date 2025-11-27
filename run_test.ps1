param(
    [Parameter(Position=0)]
    [string]$TestName,
    
    [switch]$All
)

if ($All) {
    uv run pytest tests/ -sv
}
elseif ($TestName) {
    uv run pytest tests/ -sv -k $TestName
}
else {
    Write-Host "Usage:" -ForegroundColor Cyan
    Write-Host "  .\run_test.ps1 <test_name>     - run a specific test"
    Write-Host "  .\run_test.ps1 -All            - run all tests"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Green
    Write-Host "  .\run_test.ps1 test_get_building_id_valid_address"
    Write-Host "  .\run_test.ps1 TestMFC"
    Write-Host "  .\run_test.ps1 TestBuildingSearch"
}