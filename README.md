# Snake Reyers

Olá! Meu nome é **Thiago Reyes** e este é o **Snake Reyers**, um sistema gratuito para criar lives interativas de cobrinha no TikTok.

O projeto combina um jogo 3D, personagens, comentários e presentes da live, respostas com inteligência artificial, geração local de voz e um painel de controle no navegador. Minha intenção é permitir que outras pessoas também criem sua própria live interativa sem precisar montar toda a estrutura do zero.

> O jogo é distribuído compilado. O código do servidor, do monitor, do painel e dos instaladores está disponível para consulta neste repositório, mas o projeto-fonte do Godot não faz parte da distribuição.

## O que está incluído

- jogo compilado para Windows e Linux;
- painel local para configurar e acompanhar a live;
- monitor de comentários e presentes do TikTok;
- respostas usando a chave da API OpenAI do próprio usuário;
- vozes locais em português com Piper;
- música de fundo com controle de volume;
- atualizador do programa e de novos conteúdos com verificação SHA-256.

## Instalação rápida no Windows

1. Abra a página de [Releases](https://github.com/golgol2/Snake-Reyers/releases).
2. Baixe `SnakeReyers-0.2.0-Windows-x64.zip`.
3. Extraia o ZIP para uma pasta comum, como `C:\SnakeReyers`.
4. Abra o PowerShell dentro da pasta extraída.
5. Execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\installer\windows\install.ps1
```

O instalador prepara cópias locais de Python e Node.js, instala o Piper e baixa as vozes em português e os pacotes de música de fundo verificados. A primeira instalação exige alguns gigabytes livres.

Ao terminar, o instalador cria o atalho **Snake Reyers** na Área de Trabalho. Nas próximas vezes, basta abrir esse atalho: ele inicia o servidor sem mostrar o PowerShell e abre o painel automaticamente.

Use o arquivo da página **Releases**, e não a opção **Code > Download ZIP**. A partir da versão `0.1.2`, o instalador também reconhece automaticamente um ZIP de código-fonte incompleto e recupera o pacote oficial, com verificação SHA-256. Os downloads interrompidos são repetidos automaticamente a partir da versão `0.1.3`.

Quando o painel abrir em `http://127.0.0.1:9393`:

1. informe o seu usuário do TikTok, sem `@`;
2. salve sua própria chave da API OpenAI na área de IA;
3. conecte o monitor da live;
4. abra o jogo pelo painel;
5. no TikTok LIVE Studio, adicione a janela **Snake Reyers** como captura de jogo ou de janela;
6. confirme imagem e som antes de iniciar a transmissão.

O áudio sai pelo próprio jogo. A captura e a transmissão ficam por conta do TikTok LIVE Studio.

## Instalação rápida no Linux

Requisitos: Python 3 com suporte a `venv`, Node.js 22 ou superior, npm e um ambiente gráfico com display ativo.

```bash
tar -xzf SnakeReyers-0.2.0-Linux-x64.tar.gz
cd SnakeReyers
chmod +x installer/linux/install.sh
./installer/linux/install.sh
```

Ao terminar, use o atalho **Snake Reyers** criado na Área de Trabalho. O painel será aberto em `http://127.0.0.1:9393`.

O tutorial completo, incluindo solução de problemas, está em [docs/INSTALACAO.md](docs/INSTALACAO.md).

## Atualizações automáticas

A partir da versão `0.1.1`, o launcher procura uma versão nova do programa antes de abrir o painel. Desde a versão `0.1.5`, o botão **Atualizar sistema** também permite verificar, baixar, instalar e reiniciar o Snake Reyers sem usar comandos. A instalação fica bloqueada enquanto o jogo estiver aberto.

O painel também possui a área **Atualizações de conteúdo**, que procura músicas de fundo e reações publicadas separadamente.

A partir da versão `0.1.6`, a instalação e as atualizações também criam ou reparam o atalho **Snake Reyers** na Área de Trabalho.

Conteúdos novos são baixados individualmente, têm o SHA-256 conferido e só são instalados com o jogo fechado. A configuração, os áudios já instalados e os dados privados do usuário são preservados. Consulte [docs/CONTEUDO.md](docs/CONTEUDO.md) para conhecer o formato do catálogo.

## Antes de instalar

- Use Windows 10/11 ou uma distribuição Linux 64 bits.
- Reserve pelo menos 5 GB livres para dependências, vozes e áudios.
- Tenha acesso a lives no TikTok e, no Windows, o TikTok LIVE Studio instalado.
- Crie sua própria chave da API OpenAI. Nenhuma chave do criador acompanha o projeto.

## Privacidade e segurança

Chaves, cookies, sessões e configurações privadas ficam somente no computador do usuário, dentro de `server/private`, e são ignorados pelo Git.

O painel e os serviços locais escutam em `127.0.0.1`. Nunca publique a pasta `server/private` nem compartilhe sua chave da API OpenAI.

## Comunidade

Entre no grupo para trocar ideias, relatar problemas e acompanhar o desenvolvimento:

[Participar da comunidade Snake Reyers no WhatsApp](https://chat.whatsapp.com/Ey2Z4l9JXpc8ueVBmLh50g)

## Apoie o projeto

Estou dando o sistema de graça. Que tal me pagar um cafezinho? Haha!

**Chave Pix:** `4b3d5583-daa5-4d66-9972-3c7ac33741f3`

## Atualizações

As novas versões serão publicadas nas [Releases](https://github.com/golgol2/Snake-Reyers/releases). Cada pacote possui um hash SHA-256 para conferência de integridade.

## Licença

O Snake Reyers é gratuito para uso nas suas próprias lives do TikTok. Você pode monetizar essas lives pelos recursos oficiais da plataforma, incluindo presentes, inscrições, recompensas e anúncios.

É proibido vender, revender, alugar, sublicenciar, oferecer como serviço pago, distribuir cópias não oficiais ou explorar comercialmente o Software fora da monetização da própria live no TikTok.

Este projeto é **source available**, não código aberto. Ao baixar, instalar ou usar o sistema, você aceita a [Licença Snake Reyers de Uso Gratuito para Lives no TikTok](LICENSE).

## Aviso

Snake Reyers é um projeto independente e não possui vínculo oficial com TikTok, OpenAI, Godot ou qualquer outro serviço. O uso das plataformas e APIs depende dos termos e das permissões de cada serviço.
