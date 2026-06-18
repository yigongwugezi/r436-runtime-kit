$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Python virtual environment not found: $python"
}

Push-Location $root
try {
    & $python "tests\conversation_eval.py"
    & $python "tests\conversation_regression.py"
    & $python "tests\profile_extractor_test.py"
    & $python "tests\agent_generation_test.py"
    & $python "tests\course_catalog_test.py"
    & $python "tests\import_app_test.py"
    & $python "tests\learning_tracker_test.py"
    & $python "tests\product_routes_test.py"
    & $python -m compileall app tests
}
finally {
    Pop-Location
}
