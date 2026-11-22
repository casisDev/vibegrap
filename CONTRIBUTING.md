# Como contribuir

Contribuições são bem-vindas, inclusive correções pequenas, traduções e relatos de erro.

## Relatar um erro
Abra uma *issue* e informe: versão do Windows, versão do programa (barra lateral), o link que falhou (se puder compartilhar) e a mensagem da página **Registro**.
Erros de download costumam ser resolvidos em **Ferramentas → Atualizar o yt-dlp**; confira isso antes.

## Enviar código
1. Faça um *fork* e crie uma branch.
2. Rode localmente: `pip install -r requirements.txt` e `python ytdlp_gui.py`.
3. Rode os testes: `python tests/test_app.py` (no Linux: `xvfb-run -a python tests/test_app.py`; precisa de `ffmpeg` instalado).
4. Abra um *pull request* explicando o que mudou e por quê.

## Publicar uma versão (release)
O número da versão vem do **nome da tag** — não existe arquivo para editar à mão. Se você enviar o código sem a tag, **nada é publicado** e quem usa a versão anterior não recebe a atualização.

1. Atualize o `CHANGELOG.md` em uma **seção nova** (ex.: `## [2.2.4]`) com o que mudou. **Nunca** reescreva uma versão já publicada.
2. Rode os testes: `python tests/test_app.py`.
3. Envie o código: `git push origin main`.
4. Crie e envie a tag **com o mesmo número** da seção do CHANGELOG:
   ```
   git tag v2.2.4
   git push origin v2.2.4
   ```
5. Aguarde a Action **“Construir instalador (Windows)”** e confira a página **Releases**: o `VibeGrap-Setup.exe`, o pacote leve e o `.sha256` anexados, com as notas iguais à seção do CHANGELOG.

Se esquecer a tag, é só criá-la depois: o código já está no `main` e a release sai normalmente.
Para corrigir uma tag errada: `git tag -d vX.Y.Z` e `git push origin --delete vX.Y.Z`, depois repita os passos 4 e 5.
As tags criadas no GitHub só aparecem aqui depois de um `git fetch --tags`.

## Este projeto nasceu de “vibe coding” com IA
Boa parte do código foi escrita com ajuda de um assistente de IA e **pode ter falhas que ninguém percebeu**. Por isso, revisão de código, testes novos e simplificações são especialmente úteis. Se o seu PR também usar IA, tudo bem: apenas revise o resultado e diga isso na descrição.

## Regras simples
- Textos da interface em português.
- Nada de dados pessoais, chaves ou senhas no código.
- Ao incluir uma nova biblioteca ou programa, acrescente a licença dele em `THIRD_PARTY_NOTICES.md`.
