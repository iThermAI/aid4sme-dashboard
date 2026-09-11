# Run on the development PC (Docker Desktop). Output: frontend/dist -> copy to the capture PC.
Set-Location $PSScriptRoot
docker build --target export --output type=local,dest=dist .
