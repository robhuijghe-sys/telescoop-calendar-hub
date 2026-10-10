@echo off
setlocal
cd /d "%~dp0"
title De Telescoop - kalender publiceren
where node >nul 2>nul
if errorlevel 1 (
  echo Installeer eerst Node.js LTS via https://nodejs.org/en/download
  echo Start dit bestand daarna opnieuw.
  pause
  exit /b 1
)
node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 24 ? 0 : 1)"
if errorlevel 1 (
  echo Node.js 24 of nieuwer is nodig. Download de huidige LTS-versie op https://nodejs.org/en/download
  pause
  exit /b 1
)
echo De kalender wordt gepubliceerd op je eigen Cloudflare-account.
echo Gebruik het Free-abonnement. Dit programma koopt geen abonnement of domein.
echo De aangeleverde kalender is na publicatie bereikbaar voor iedereen met de URL.
echo.
echo Benodigde software ophalen...
call npm ci --no-audit --no-fund
if errorlevel 1 goto failed
node scripts/publish.mjs
if errorlevel 1 goto failed
echo.
echo Open private-import\BEHEERLINK.txt voor beheer.
echo Open SMARTSCHOOL-code.txt voor de code die je in Smartschool plakt.
pause
exit /b 0
:failed
echo.
echo De publicatie is niet afgerond. Bewaar de map en de foutmelding.
echo Opnieuw starten gebruikt dezelfde installatie en herstelt geen verwijderde items.
pause
exit /b 1
