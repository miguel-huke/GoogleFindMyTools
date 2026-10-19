# ARCH-013 — Smoke Google real sanitizado

Data: 2026-10-19
Modo: MANUAL/OPT-IN autorizado pelo usuário
Resultado: APROVADO COM LIMITAÇÃO DOCUMENTADA

## Escopo executado

1. Inicialização do `main.py` em modo real e banco SQLite isolado.
2. Abertura visível do frontend localhost.
3. Sincronização real do inventário Google.
4. Atualização real de apenas um device.
5. Reinicialização com leitura exclusiva do cache SQLite.

## Evidências sanitizadas

- `SYNC_DEVICES`: `SUCCEEDED`;
- devices descobertos: 3;
- `REFRESH_ONE`: `SUCCEEDED`;
- reports recebidos: 1;
- reports inseridos: 1;
- posição mais recente presente após persistência: sim;
- reinicialização preservou 3 devices e ao menos uma posição: sim.

## Privacidade e segurança

- nenhum nome, ID interno, token, payload ou coordenada foi registrado neste relatório;
- nenhuma captura de tela da localização real foi criada;
- o banco do smoke foi removido do workspace e movido para `%LOCALAPPDATA%\GoogleFindMyTools\smoke-arch013-20261019.db`;
- `Auth/secrets.json` não foi exibido nem copiado; a própria integração pode atualizar seu cache FCM durante o fluxo normal;
- a instância real foi encerrada ao final.

## Limitação observada

A sessão em cache estava válida, portanto o fluxo abriu o frontend visível, mas não precisou abrir uma nova janela oficial de login. Uma reautenticação forçada não foi executada porque exigiria alterar credenciais locais válidas.

Durante o primeiro encerramento, uma desconexão de tile produziu stack trace sem dados de localização ou credenciais. O servidor foi corrigido para suprimir tracebacks de desconexões do navegador, recebeu teste de regressão e o encerramento foi repetido sem saída sensível.
