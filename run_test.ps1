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
    Write-Host "Использование:" -ForegroundColor Cyan
    Write-Host "  .\run_test.ps1 <имя_теста>     - запустить конкретный тест"
    Write-Host "  .\run_test.ps1 -All            - запустить все тесты"
    Write-Host ""
    Write-Host "Примеры:" -ForegroundColor Green
    Write-Host "  .\run_test.ps1 test_get_building_id_valid_address"
    Write-Host "  .\run_test.ps1 TestMFC"
    Write-Host "  .\run_test.ps1 TestBuildingSearch"
}