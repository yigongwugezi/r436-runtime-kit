# DeepTutor 启动脚本 — 自动从 .env 读取配置
cd D:\EduAgent

Get-Content .env | ForEach-Object {
    $line = $_.Trim()
    if ($line -and $line -notmatch '^#' -and $line -match '^(\w[^=]*)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        if ($name -eq 'LLM_API_KEY') { $env:OPENAI_API_KEY = $value }
        if ($name -eq 'LLM_BASE_URL') { $env:OPENAI_BASE_URL = $value }
        if ($name -eq 'LLM_MODEL') { $env:DEEPTUTOR_DEFAULT_MODEL = $value }
    }
}

$env:DEEPTUTOR_HOME = "D:\EduAgent\runtime_data"
.\.venv\Scripts\activate
python -m deeptutor serve --host 0.0.0.0 --port 8000
