@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo            Snake Reyers Lite - Instalador
echo ============================================================
echo.
echo Este assistente prepara tudo o que o programa precisa:
echo Python e Node.js locais, voz em portugues, musicas e o
echo atalho "Snake Reyers Lite" na Area de Trabalho.
echo.
echo A primeira instalacao pode demorar e precisa de alguns
echo gigabytes livres. Voce nao precisa digitar nada.
echo.
echo Pressione uma tecla para comecar...
pause >nul

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\windows\install.ps1"
set "INSTALL_RESULT=%ERRORLEVEL%"

echo.
if "%INSTALL_RESULT%"=="0" (
    echo ============================================================
    echo    Instalacao concluida com sucesso!
    echo ============================================================
    echo.
    echo Agora abra o atalho "Snake Reyers Lite" na Area de Trabalho
    echo para iniciar o programa e abrir o painel no navegador.
) else (
    echo ============================================================
    echo    A instalacao nao foi concluida ^(codigo %INSTALL_RESULT%^).
    echo ============================================================
    echo.
    echo Leia as mensagens acima e execute o INSTALAR.cmd novamente.
    echo Detalhes tecnicos: server\runs\logs
)
echo.
echo Pressione uma tecla para fechar.
pause >nul
exit /b %INSTALL_RESULT%