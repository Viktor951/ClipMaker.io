# Inicia a API (FastAPI) em um job
Start-Job -Name "API_FastAPI" -ScriptBlock {
    uvicorn backend.main:app --reload
}

# Inicia o Worker (Huey) em outro job
Start-Job -Name "Worker_Huey" -ScriptBlock {
    python huey_consumer.py backend.worker.huey -w 1
}

Write-Host "Processos iniciados em background (Jobs)."
Write-Host "Para visualizar os logs, você pode usar 'Receive-Job -Name API_FastAPI' ou 'Receive-Job -Name Worker_Huey'."
Write-Host "Para parar, use 'Stop-Job -Name API_FastAPI, Worker_Huey'"
Write-Host ""
Write-Host "Nota: Se preferir ver os logs em tempo real na tela, considere rodar em dois terminais separados,"
Write-Host "ou instale a ferramenta 'concurrently' do Node.js."

# Esperar para que os jobs continuem rodando se o usuário quiser acompanhar,
# mas aqui estamos usando Jobs, então o script já pode finalizar e os jobs continuam no PowerShell.
