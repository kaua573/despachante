# Limpeza de custos do Sistema Despachante no Google Cloud.
# Rode na pasta onde estao policy.json e lifecycle.json:
#   .\limpar-custos.ps1

$projeto = "sistema-despachante-503923"
$regiao  = "southamerica-east1"

Write-Host "1) Artifact Registry: mantendo so as 2 imagens mais recentes..."
gcloud artifacts repositories set-cleanup-policies cloud-run-source-deploy `
  --project=$projeto --location=$regiao --policy=policy.json --no-dry-run

Write-Host ""
Write-Host "2) Cloud Storage: buckets de deploy encontrados:"
$buckets = gcloud storage ls --project=$projeto | Where-Object { $_ -match "run-sources|cloudbuild" }

if (-not $buckets) {
  Write-Host "Nenhum bucket de deploy encontrado. Veja a lista completa com:"
  Write-Host "  gcloud storage ls --project=$projeto"
  exit
}

$buckets | ForEach-Object { Write-Host "  $_" }
$resp = Read-Host "Aplicar regra de apagar arquivos com mais de 7 dias nesses buckets? (s/n)"
if ($resp -ne "s") { Write-Host "Cancelado."; exit }

foreach ($b in $buckets) {
  gcloud storage buckets update $b --lifecycle-file=lifecycle.json
}

Write-Host ""
Write-Host "Pronto."
