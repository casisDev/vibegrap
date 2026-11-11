# Créditos e licenças de terceiros

O **VibeGrap**, desenvolvido por casisDev, é apenas uma interface. Quem faz o trabalho pesado são os projetos abaixo, e todo o mérito é deles.
Este arquivo lista o que é usado, sob qual licença e onde obter o código-fonte.

> Este documento é informativo e **não é aconselhamento jurídico**. Em caso de dúvida, vale o texto original da licença de cada projeto.

## 1. Programas que acompanham o instalador

| Componente | Para que serve aqui | Licença | Código-fonte / site |
|---|---|---|---|
| **yt-dlp** | Faz os downloads (é o motor do programa) | Unlicense (domínio público) | https://github.com/yt-dlp/yt-dlp |
| **yt-dlp-ejs** | Resolve os desafios de JavaScript do YouTube | Unlicense, MIT e ISC | https://github.com/yt-dlp/ejs |
| **FFmpeg** (build “GPL” da BtbN) | Junta vídeo e áudio, converte para MP3 etc. | **GPL v3** | Código: https://ffmpeg.org/download.html · Build: https://github.com/BtbN/FFmpeg-Builds |
| **Deno** | Executa o JavaScript exigido pelo YouTube | MIT | https://github.com/denoland/deno |
| **Python** (embutido pelo PyInstaller) | Linguagem do programa | PSF License | https://docs.python.org/3/license.html |
| **Tcl/Tk** (embutido com o Python) | Janelas | Licença estilo BSD | https://www.tcl-lang.org/software/tcltk/license.html |

## 2. Bibliotecas Python embutidas no programa

| Biblioteca | Licença | Site |
|---|---|---|
| customtkinter | MIT (© Tom Schimansky) ¹ | https://github.com/TomSchimansky/CustomTkinter |
| Roboto (fonte, distribuída com o customtkinter) | Apache 2.0 | https://github.com/googlefonts/roboto |
| Pillow | MIT-CMU (HPND) | https://github.com/python-pillow/Pillow |
| mutagen | **GPL-2.0 ou posterior** | https://github.com/quodlibet/mutagen |
| pycryptodomex | BSD / domínio público | https://github.com/Legrandin/pycryptodome |
| brotli | MIT | https://github.com/google/brotli |
| websockets | BSD-3-Clause | https://github.com/python-websockets/websockets |
| certifi | MPL-2.0 | https://github.com/certifi/python-certifi |
| requests | Apache 2.0 | https://github.com/psf/requests |
| urllib3 | MIT | https://github.com/urllib3/urllib3 |
| darkdetect | BSD-3-Clause | https://github.com/albertosottile/darkdetect |
| packaging | Apache 2.0 ou BSD-2-Clause | https://github.com/pypa/packaging |
| charset-normalizer, idna | MIT, BSD-3-Clause | https://github.com/jawah/charset_normalizer · https://github.com/kjd/idna |

¹ O arquivo `LICENSE` distribuído dentro do customtkinter é a licença MIT; o campo de metadados do pacote cita CC0, o que é uma inconsistência dele. Usamos o texto do arquivo de licença.

## 3. Ferramentas usadas só para construir o instalador (não ficam no programa)

| Ferramenta | Licença | Site |
|---|---|---|
| PyInstaller | GPL-2.0 ou posterior **com exceção** que permite usá-lo em programas de qualquer licença | https://github.com/pyinstaller/pyinstaller |
| Inno Setup | Licença própria, gratuita, que permite distribuir os instaladores gerados | https://jrsoftware.org/files/is/license.txt |

## 4. Em que licença é distribuído cada pedaço

- **Código-fonte deste repositório** (`ytdlp_gui.py`, `installer.iss`, scripts, testes, documentação): **licença MIT** (arquivo `LICENSE`).
- **Instalador e programas empacotados** (`VibeGrap-Setup.exe`): como o instalador junta código sob GPL (FFmpeg, mutagen) com o resto, **o conjunto é distribuído sob os termos da GPLv3 ou posterior**. É o mesmo modelo adotado pelo próprio yt-dlp, cujo código é Unlicense mas cujos executáveis empacotados são GPLv3+.
  - Na prática: você pode usar, copiar e redistribuir o instalador livremente, desde que mantenha estes avisos e permita acesso ao código-fonte correspondente.
  - **Código-fonte correspondente:** este repositório + os links das tabelas acima (FFmpeg e demais componentes). O instalador é reproduzível a partir do código por `Criar-Instalador.bat` ou pelo fluxo do GitHub Actions.
  - O texto da GPLv3 do FFmpeg e a licença do Deno acompanham o instalador, na pasta `licenses` dentro da pasta de instalação.

## 5. Marcas e independência

“YouTube”, “FFmpeg”, “Deno”, “Python” e outros nomes citados pertencem aos seus donos. Este projeto **não é afiliado, aprovado nem mantido** pelo projeto yt-dlp, pelo YouTube ou por qualquer um dos citados.
