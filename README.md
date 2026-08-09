# HonraDinho

Bot para Discord com moderação, tickets, boas-vindas, níveis, economia, sugestões e ferramentas de comunidade.

- Site: https://heitormeire.github.io/honradinho-site/
- Comandos: https://heitormeire.github.io/honradinho-site/comandos.html
- Suporte: https://discord.gg/SvZHVPdbR
- Adicionar ao Discord: https://discord.com/oauth2/authorize?client_id=1535116053649162300&scope=bot%20applications.commands&permissions=1374658096214

## Recursos

- Tickets V2 com categorias, claim, transcript e logs
- Moderação com ban, kick, timeout, warns, lock e slowmode
- Logs de moderação e eventos de mensagens
- Boas-vindas, despedidas e autorole
- Níveis, XP com cooldown e leaderboard
- Economia com saldo, daily e transferências
- Sugestões com aprovação e enquetes
- 42 comandos slash documentados no site
- Consulta de dados e atalhos de privacidade

## Requisitos

- Python 3.10 ou superior
- `discord.py` 2.x
- Aplicação criada no Discord Developer Portal
- Intents **Server Members** e **Message Content** habilitadas no Developer Portal, pois os sistemas de autorole/boas-vindas e XP/logs dependem delas

## Instalação local

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Defina o token como variável de ambiente. Nunca grave o token no código, em `.env` versionado ou em commits.

Linux/macOS:

```bash
export DISCORD_TOKEN="seu_token_aqui"
python bot.py
```

PowerShell:

```powershell
$env:DISCORD_TOKEN="seu_token_aqui"
python bot.py
```

Por padrão o banco é `honradinho.db`. Para usar outro caminho, configure `HONRADINHO_DB_PATH`.

## Configuração no Discord

Depois de adicionar o bot:

1. Posicione o cargo do HonraDinho acima dos cargos que ele deverá moderar ou entregar.
2. Configure tickets com `/ticket-config staff`, `/ticket-config logs` e `/ticket-config categoria`.
3. Configure comunidade com `/welcome-config`, `/logs-config moderacao` e `/sugestoes-config canal`.
4. Confira o estado atual com `/configuracao`.
5. Publique o painel com `/ticket`.

## Segurança e dados

- `DISCORD_TOKEN` é lido exclusivamente do ambiente.
- `.env`, bancos SQLite e ambientes virtuais ficam fora do Git.
- O convite usa permissões específicas em vez de `Administrator`.
- Dados persistentes são descritos em `privacy.html`.
- Em produção, use um volume persistente protegido e criptografia em repouso oferecida pela hospedagem.
- Transcripts de tickets são gerados em memória; depois de enviados ao Discord, a cópia segue a retenção do canal/mensagem de destino.

## Verificação

```bash
python -m py_compile bot.py
python scripts/check_bot.py
python scripts/check_site.py
```

O workflow em `.github/workflows/checks.yml` executa essas verificações automaticamente em pushes e pull requests.

## Documentos

- [Termos de Serviço](terms.html)
- [Política de Privacidade](privacy.html)

HonraDinho é um projeto independente e não é afiliado, patrocinado ou endossado pela Discord Inc.
