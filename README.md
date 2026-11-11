# VibeGrap

> ### Programa de *vibe coding*, desenvolvido por **casisDev**
> O VibeGrap foi criado por **casisDev** através de *vibe coding*: ele descreveu o que queria em linguagem natural e o código foi escrito e testado com a ajuda de uma IA. Detalhes em [Sobre este projeto](#sobre-este-projeto).

Interface gráfica moderna, em português, para o [yt-dlp](https://github.com/yt-dlp/yt-dlp): baixe vídeos e áudios escolhendo qualidade, **faixa de áudio (idioma/dublagem)**, legendas, itens de playlist e trechos, com fila de downloads e **progresso total** (itens, bytes, velocidade e tempo restante).

## Recursos

- Análise do link com miniatura, título, duração e **tamanho estimado** antes de baixar
- Vídeo (MP4, MKV, WEBM, até 4K) ou só áudio (MP3, M4A, Opus, FLAC, WAV)
- **Escolha da faixa de áudio** (uma ou várias dublagens no mesmo arquivo)
- Legendas (manuais e automáticas), com opção de embutir no vídeo
- Playlists com seleção de itens e download de **trecho** (início/fim)
- Fila de downloads com progresso por item e **painel de progresso total**
- Cookies do navegador, proxy, limite de velocidade, nomes de arquivo personalizáveis
- Tema claro/escuro (vermelho, branco e preto)
- **Botão de atualização:** avisa quando há versão nova e instala com um clique

## Instalação (Windows)

1. Abra a página **[Releases](../../releases)** deste repositório.
2. Baixe **`VibeGrap-Setup.exe`** e dê dois cliques.
3. Siga o assistente. Não precisa de senha de administrador. O instalador já inclui o ffmpeg e o Deno.

**Avisos normais do Windows:** o instalador não é assinado digitalmente (assinatura é paga), então o Windows pode mostrar “O Windows protegeu o computador”: clique em **Mais informações → Executar assim mesmo**. Alguns antivírus marcam programas feitos com PyInstaller por engano (falso positivo). Se desconfiar, **construa você mesmo** a partir do código (abaixo) e compare.

## Atualizações

Na barra lateral do programa há o botão **Verificar atualização**. Quando existe uma versão nova publicada em **Releases**, o botão muda para **“Atualizar para vX.Y.Z”**: um clique baixa o instalador, atualiza por cima (sem perder suas configurações) e abre o programa de novo. Dá para desligar a verificação automática em **Configurações**.

## Construir a partir do código

**Instalador automático (GitHub Actions):** o arquivo `.github/workflows/build.yml` monta o instalador num computador Windows do GitHub. Rode-o na aba **Actions → Construir instalador → Run workflow**; o resultado fica em *Artifacts*. Ao publicar uma versão (tag `v2.0.0`, por exemplo), o `VibeGrap-Setup.exe` é anexado à página **Releases** automaticamente, e é daí que o botão de atualização do programa busca as novidades.

**No seu PC:** descompacte, entre na pasta e dê dois cliques em `Criar-Instalador.bat`. Ele instala o que faltar (Python e Inno Setup, pelo winget) e cria `installer_output\VibeGrap-Setup.exe`. (Cópias feitas assim não têm o botão de atualização ligado a um repositório.)

**Rodar sem instalar (desenvolvimento):**
```
pip install -r requirements.txt
python ytdlp_gui.py
```

**Testes:** `python tests/test_app.py` (no Linux: `xvfb-run -a python tests/test_app.py`, com `ffmpeg` instalado).

## Estrutura

| Arquivo | Para que serve |
|---|---|
| `ytdlp_gui.py` | O programa inteiro |
| `assets/` | Ícone (`VibeGrap_icon.ico`) e logo (`VibeGrap_logo.png`) |
| `installer.iss` | Receita do instalador (Inno Setup) |
| `.github/workflows/` | Montagem do instalador (`build.yml`) e testes (`tests.yml`) |
| `Criar-Instalador.bat` | Gera o instalador no seu PC |
| `tests/test_app.py` | Testes automáticos |
| `LICENSE` | Licença do código (MIT) |
| `THIRD_PARTY_NOTICES.md` | Créditos e licenças de tudo que é usado |

## Se algo não funcionar

- **YouTube não baixa / erro de “challenge”:** abra **Ferramentas → Atualizar o yt-dlp** e reabra o programa (os sites mudam com frequência).
- **Vídeo exige login ou restrição de idade:** em **Configurações → Cookies do navegador**, escolha o navegador onde você está logado.
- **Detalhes de qualquer erro:** página **Registro**.
- Os ajustes ficam em `%APPDATA%\VibeGrap` (apague a pasta para voltar ao padrão).

## Sobre este projeto

O **VibeGrap** é um programa de **“vibe coding” desenvolvido por casisDev**: ele descreveu em linguagem natural o que queria e o código foi escrito, testado e refinado de forma iterativa com a ajuda de um assistente de IA. O autor humano dirigiu o resultado e é quem publica e mantém o projeto.

O que isso significa para você:

- O código tem **testes automáticos**, mas **não passou por auditoria profissional**. Pode ter falhas que ninguém percebeu.
- O instalador **não foi testado em todas as versões e configurações do Windows**.
- Revisões de código, testes novos e correções são muito bem-vindos (veja [CONTRIBUTING.md](CONTRIBUTING.md)).
- O enquadramento legal de direitos autorais sobre código gerado com IA varia conforme o país. Por isso o projeto é oferecido “**como está**”, sem garantias, nos termos da licença.

## Uso responsável

Baixe apenas conteúdo que você **tem o direito de baixar** (seu, de domínio público, com licença livre ou com permissão de quem o publicou). Respeite os **termos de serviço** dos sites e as **leis de direitos autorais** do seu país. Os autores e contribuidores não se responsabilizam pelo uso que cada pessoa fizer do programa.

## Créditos e licenças

Todo o trabalho pesado é feito por outros projetos. Os principais:

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** (Unlicense): o motor de download
- **[FFmpeg](https://ffmpeg.org)** (GPL v3, build da [BtbN](https://github.com/BtbN/FFmpeg-Builds)): junção e conversão de mídia
- **[Deno](https://deno.com)** (MIT): execução do JavaScript exigido pelo YouTube
- **[customtkinter](https://github.com/TomSchimansky/CustomTkinter)** (MIT) e **[Pillow](https://github.com/python-pillow/Pillow)**: interface e imagens

A lista completa, com licenças e links para o código-fonte, está em **[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**.

**Licenças em resumo:**
- **Código-fonte deste repositório:** [MIT](LICENSE), © casisDev.
- **Instalador (`VibeGrap-Setup.exe`):** por conter componentes GPL (FFmpeg, mutagen), o conjunto é distribuído sob os termos da **GPLv3 ou posterior**, o mesmo modelo usado pelos executáveis do próprio yt-dlp. O código-fonte correspondente é este repositório mais os links do arquivo de créditos.

O VibeGrap **não é afiliado nem aprovado** pelo projeto yt-dlp, pelo YouTube ou por qualquer outro projeto ou empresa citados.
