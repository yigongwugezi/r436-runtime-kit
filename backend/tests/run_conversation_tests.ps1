$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Python virtual environment not found: $python"
}

function Invoke-PythonTest {
    param(
        [Parameter(Mandatory=$true)]
        [string[]]$Arguments
    )

    & $python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $python $($Arguments -join ' ')"
    }
}

Push-Location $root
try {
    Invoke-PythonTest @("tests\conversation_eval.py")
    Invoke-PythonTest @("tests\conversation_regression.py")
    Invoke-PythonTest @("tests\profile_extractor_test.py")
    Invoke-PythonTest @("tests\planner_agent_test.py")
    Invoke-PythonTest @("tests\resource_agent_test.py")
    Invoke-PythonTest @("tests\agent_generation_test.py")
    Invoke-PythonTest @("tests\session_data_contract_test.py")
    Invoke-PythonTest @("tests\course_catalog_test.py")
    Invoke-PythonTest @("tests\import_app_test.py")
    Invoke-PythonTest @("tests\learning_tracker_test.py")
    Invoke-PythonTest @("tests\product_routes_test.py")
    Invoke-PythonTest @("-m", "compileall", "app", "tests")
}
finally {
    Pop-Location
}
