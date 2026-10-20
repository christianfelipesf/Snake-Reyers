# Tutorial de instalação

Este guia instala o Snake Reyers sem exigir o projeto-fonte do Godot. O jogo já vem compilado no pacote da plataforma.

Ao baixar, instalar ou executar o sistema, o usuário aceita a [Licença Snake Reyers](../LICENSE). O uso é gratuito, e a monetização é permitida exclusivamente nas próprias lives do usuário no TikTok. A venda, revenda, locação, sublicença e oferta do sistema como serviço pago são proibidas.

## Windows 10 e 11

### 1. Baixar

Abra a [Release mais recente](https://github.com/golgol2/Snake-Reyers/releases/latest) e baixe o arquivo com `Windows-x64` no nome.

Não use o botão **Code > Download ZIP** como pacote de instalação: esse ZIP é apenas o código-fonte público e não inclui o jogo compilado. Se isso acontecer, a versão `0.1.2` ou superior do instalador detecta os arquivos ausentes e recupera automaticamente o pacote oficial, verificando seu SHA-256.

O instalador baixa automaticamente os pacotes de áudio. Se preferir baixá-los manualmente, coloque todos os arquivos `SnakeReyers-*-Audio-*.zip` ao lado do ZIP principal antes de extrair.

### 2. Extrair

Extraia o pacote para um caminho curto e gravável. Exemplo:

```text
C:\SnakeReyers
```

Não execute o sistema diretamente de dentro do ZIP.

### 3. Instalar

Abra a pasta `SnakeReyers`, clique com o botão direito em uma área vazia e escolha **Abrir no Terminal**. Execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\installer\windows\install.ps1
```

O instalador prepara cópias locais de Python e Node.js, instala o Piper e baixa as vozes em português e os pacotes de música de fundo. Esses componentes ficam dentro da pasta do Snake Reyers e não substituem instalações globais do computador.

### 4. Iniciar

Ao concluir, abra o atalho **Snake Reyers** criado na Área de Trabalho. Ele inicia o servidor sem deixar uma janela do PowerShell aberta e abre o painel automaticamente.

Se o atalho for removido, execute `launcher\create_shortcut.ps1` para criá-lo novamente.

O navegador abrirá o painel. Se isso não acontecer, acesse manualmente:

```text
http://127.0.0.1:9393
```

### 5. Configurar

No painel:

1. abra as configurações de IA;
2. informe sua própria chave da API OpenAI e salve;
3. informe o nome de usuário do TikTok sem `@`;
4. conecte o monitor;
5. abra o jogo;
6. confirme que o painel mostra o jogo e o monitor como conectados.

A chave da API é salva apenas no computador local. Os custos da API, quando houver, pertencem à conta informada pelo usuário.

### 6. Capturar no TikTok LIVE Studio

1. Abra o TikTok LIVE Studio.
2. Adicione uma fonte de captura de jogo ou captura de janela.
3. Selecione `SnakeReyers.exe`.
4. Confirme que o áudio do aplicativo está entrando no mixer.
5. Faça uma prévia antes de iniciar a live.

O áudio sai pelo próprio jogo. A captura e a transmissão ficam por conta do TikTok LIVE Studio.

## Linux

Instale previamente Python 3 com suporte a `venv`, Node.js 22+, npm e um ambiente gráfico com display ativo.

Depois de baixar a Release Linux:

```bash
tar -xzf SnakeReyers-0.2.0-Linux-x64.tar.gz
cd SnakeReyers
chmod +x installer/linux/install.sh
./installer/linux/install.sh
```

Depois da instalação, abra o atalho **Snake Reyers** criado na Área de Trabalho.

O painel permite informar o display usado pelo jogo e escolher entre o build compilado e o Godot editor, quando o projeto estiver disponível.

## Verificar os downloads

Compare o SHA-256 com `SnakeReyers-0.2.0-checksums.json` publicado na Release.

Windows:

```powershell
Get-FileHash .\SnakeReyers-0.2.0-Windows-x64.zip -Algorithm SHA256
```

Linux:

```bash
sha256sum SnakeReyers-0.2.0-Linux-x64.tar.gz
```

## Problemas comuns

### O painel não abriu

Confira `server/runs/logs/server-error.log` e tente abrir `http://127.0.0.1:9393` manualmente.

### O jogo abre, mas não lê comentários

Confirme no painel se o monitor está **conectado** e **escutando**. A live do usuário informado precisa estar online.

### O monitor não conecta

Por padrão, o monitor usa uma conexão direta. Se a sua rede exigir um proxy SOCKS, defina `SNAKE_REYERS_MONITOR_PROXY` antes de abrir o Snake Reyers, por exemplo `socks5h://127.0.0.1:1080`. Se você usa um provedor de assinatura do TikTok, defina também `SNAKE_REYERS_SIGN_API_KEY`. Essas duas opções são opcionais e não são necessárias para o funcionamento normal.

### A primeira fala demora

Na primeira fala depois de iniciar, o Piper carrega o modelo de voz na memória. As falas seguintes ficam mais rápidas.

### O Windows bloqueou um arquivo

Extraia novamente em uma pasta comum, como `C:\SnakeReyers`, e autorize o aplicativo apenas se o pacote tiver sido baixado da Release oficial e o hash SHA-256 estiver correto.

### A instalação ficou sem espaço

As dependências, as vozes e os pacotes de áudio ocupam alguns gigabytes. Libere pelo menos 5 GB e execute o instalador novamente.

## Ajuda

Participe da [comunidade Snake Reyers no WhatsApp](https://chat.whatsapp.com/Ey2Z4l9JXpc8ueVBmLh50g).
