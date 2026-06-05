Set-Location $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" -m streamlit run "$PSScriptRoot\app.py" --server.port 8501 --server.headless true *> "$PSScriptRoot\streamlit.log"
