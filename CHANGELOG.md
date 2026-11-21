# Histórico de versões

## [2.2.2]

- Aviso claro quando o navegador (Chrome, Brave ou Edge novos) não deixa ler os cookies por causa da criptografia DPAPI, com o passo a passo para usar um arquivo cookies.txt.
- Corrigido: analisar um link depois de outro podia travar a tela em "Analisando o link…" e registrar `image "pyimage…" doesn't exist` no Registro. Agora a miniatura é limpa sem deixar uma imagem apagada, erros internos avisam e destravam o botão, e respostas de análises antigas são ignoradas.
- Vídeo em **MP4** agora sai em **H.264 + AAC**, o padrão que o WhatsApp, TVs e celulares aceitam: converte HEVC/VP9/AV1 e áudio HE-AAC quando preciso e acrescenta uma faixa silenciosa em vídeos mudos (o que costuma fazer o WhatsApp recusar arquivos baixados do Instagram). Em MKV/WEBM o codec original é mantido.
- TikTok: instalado o suporte a *impersonation* (`curl_cffi`) que o yt-dlp usa para passar pela verificação do site; novos avisos explicam o que fazer quando o TikTok ou o Instagram recusam o link (atualizar o yt-dlp, usar cookies do navegador).

## [2.2.1]

- Corrigido: com "Pasta própria para playlists" ligado, os vídeos da playlist agora vão para uma subpasta com o nome dela (antes o nome virava `Lista⧸Vídeo.mp4`, tudo solto na pasta de destino).
- Histórico bem mais rápido: a lista aparece em lotes de 12 itens, com o botão "Mostrar mais", em vez de montar tudo de uma vez.
- As abas são montadas só quando abertas: o programa abre mais rápido e trocar de aba ficou mais leve.
- Com a janela minimizada nada é redesenhado; a fila e o histórico se atualizam de uma vez quando você volta.

## [2.2.0]

- Playlists: digite os itens que quer baixar, como `1-10`, `1, 2, 3` ou `1-5, 8, 12-`. Eles são marcados na lista e você ainda pode ajustar com o clique.
- Interruptor "Extrair só o áudio de todos os itens" na aba Playlist, para baixar a playlist como áudio em lote.
- Mostra quantos itens estão selecionados e avisa quando um número está fora da playlist.

## [2.1.1]

- Mudança do logo e icone

## [2.1.0]

- Atualização leve: o botão de atualizar baixa só o que mudou (pacote pequeno, conferido por hash) em vez do instalador inteiro.
- Se a atualização leve não for possível, o programa usa o instalador completo sozinho.
- O status "Concluído" na fila deixou de ser verde, para manter a paleta vermelho, branco e preto.
- README com a seção de capturas de tela e explicação das atualizações.

## [2.0.0]

- Primeira versão com o nome **VibeGrap**, programa de vibe coding por casisDev.
- Visual novo em vermelho, branco e preto, com tema claro e escuro.
- Escolha da faixa de áudio, legendas, playlists com trecho, fila e progresso total.
- Histórico de downloads com busca e aviso ao terminar.
- Erros do yt-dlp explicados em português.
- yt-dlp se atualiza sozinho, conferindo o hash oficial.
- Botão de atualização do programa pelo GitHub Releases.
