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

## Este projeto nasceu de “vibe coding” com IA
Boa parte do código foi escrita com ajuda de um assistente de IA e **pode ter falhas que ninguém percebeu**. Por isso, revisão de código, testes novos e simplificações são especialmente úteis. Se o seu PR também usar IA, tudo bem: apenas revise o resultado e diga isso na descrição.

## Regras simples
- Textos da interface em português.
- Nada de dados pessoais, chaves ou senhas no código.
- Ao incluir uma nova biblioteca ou programa, acrescente a licença dele em `THIRD_PARTY_NOTICES.md`.
