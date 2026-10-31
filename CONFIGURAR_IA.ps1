param([string]$Modelo = 'gpt-5.6-luna')
$ErrorActionPreference = 'Stop'
$env:NEO_IA_PROVIDER = 'openai'
if (-not $env:OPENAI_API_KEY) {
    $neoApiSecret = Read-Host 'Introduce tu clave de API de OpenAI (entrada oculta)' -AsSecureString
    $env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $neoApiSecret).Password
}
$env:OPENAI_MODEL = $Modelo
Write-Host "Configuracion preparada para esta terminal. Modelo: $Modelo"
Write-Host 'Ahora ejecuta: python probar_ia.py'
Write-Host 'La clave no se guarda en archivos ni se muestra en pantalla.'
