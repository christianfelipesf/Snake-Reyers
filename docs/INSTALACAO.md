# Tutorial de instalação

Este guia instala o Snake Reyers Lite sem exigir o projeto-fonte do Godot. O jogo já vem compilado no pacote da plataforma.

Ao baixar, instalar ou executar o sistema, o usuário aceita a [Licença Snake Reyers Lite](../LICENSE). O uso é gratuito, e a monetização é permitida exclusivamente nas próprias lives do usuário no TikTok. A venda, revenda, locação, sublicença e oferta do sistema como serviço pago são proibidas.

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

Dê **dois cliques em `INSTALAR.cmd`** dentro da pasta `SnakeReyers`. O instalador abre uma janela,
mostra o progresso e, ao terminar, cria o atalho **Snake Reyers Lite** na Área de Trabalho.

O instalador prepara cópias locais de Python e Node.js, instala a voz local (Piper) e baixa as
vozes em português e os pacotes de música de fundo. Esses componentes ficam dentro da pasta do Snake
Reyers Lite e não substituem instalações globais do computador.

Se preferir a linha de comando, abra o terminal na pasta e execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\windows\install.ps1
```

### 4. Iniciar

Ao concluir, abra o atalho **Snake Reyers Lite** criado na Área de Trabalho. Ele inicia o servidor sem deixar uma janela do PowerShell aberta e abre o painel automaticamente.

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
./INSTALAR.sh
```

Depois da instalação, abra o atalho **Snake Reyers Lite** criado na Área de Trabalho.

O painel permite informar o display usado pelo jogo e escolher entre o build compilado e o Godot editor, quando o projeto estiver disponível.

## O que o instalador baixa da web

O Snake Reyers Lite é leve: as peças abaixo não acompanham o pacote e são buscadas por HTTPS, com verificação de SHA-256 sempre que existe um hash oficial.

| Download | Origem | Quando |
| --- | --- | --- |
| Python 3.12 (cópia local) | python.org | só no Windows, na primeira instalação |
| Node.js 22 (cópia local) | nodejs.org | só no Windows, na primeira instalação |
| Pacotes Python (FastAPI, Piper, etc.) | PyPI | na primeira instalação |
| Dependências do monitor TikTok | npm registry | na primeira instalação |
| Vozes Piper em português (Faber, Cadu, Jeff) | Hugging Face (rhasspy/piper-voices) | na primeira instalação |
| Músicas de fundo e reações | anexos da Release no GitHub | quando o manifesto de áudio pede |
| Atualizações do programa | GitHub Releases | ao abrir, se houver versão nova |
| Conteúdos novos (músicas, reações) | anexos no GitHub | quando o catálogo de conteúdo indica |

O Snake Reyers Lite **não instala Torch**: a voz local usa Piper. Se o instalador estiver baixando `torch`, a pasta foi sobrescrita por uma versão antiga (esse era um problema da versão `0.1.9`).

Quando a pasta é uma cópia do código-fonte, o instalador tenta buscar o jogo compilado e o áudio na Release oficial. Ele **nunca rebaixa** para uma versão mais antiga: se a Release publicada for anterior à versão da sua pasta, o pacote é ignorado e um aviso aparece. No Linux, o Python, o Node.js e o npm precisam já estar instalados no sistema.

Nenhuma chave ou dado privado sai do computador: elas ficam em `server/private`. As respostas com IA usam a **sua** chave da OpenAI (`api.openai.com`), e os custos ficam na sua conta. O monitor da live conversa com o TikTok para ler comentários e presentes.

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

Por padrão, o monitor usa uma conexão direta. Se a sua rede exigir um proxy SOCKS, defina `SNAKE_REYERS_MONITOR_PROXY` antes de abrir o Snake Reyers Lite, por exemplo `socks5h://127.0.0.1:1080`. Se você usa um provedor de assinatura do TikTok, defina também `SNAKE_REYERS_SIGN_API_KEY`. Essas duas opções são opcionais e não são necessárias para o funcionamento normal.

### A primeira fala demora

Na primeira fala depois de iniciar, o Piper carrega o modelo de voz na memória. As falas seguintes ficam mais rápidas.

### O Windows bloqueou um arquivo

Extraia novamente em uma pasta comum, como `C:\SnakeReyers`, e autorize o aplicativo apenas se o pacote tiver sido baixado da Release oficial e o hash SHA-256 estiver correto.

### A instalação ficou sem espaço

As dependências, as vozes e os pacotes de áudio ocupam alguns gigabytes. Libere pelo menos 5 GB e execute o instalador novamente.

## Ajuda

Participe da [comunidade Snake Reyers Lite no WhatsApp](https://chat.whatsapp.com/Ey2Z4l9JXpc8ueVBmLh50g).
