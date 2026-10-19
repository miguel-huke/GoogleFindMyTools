# Bloco do aplicativo de mapa

BLOCK-ID: MAP-002
TYPE: criar / integrar
DESCRIPTION: fazer `main.py` abrir um frontend localhost com MapLibre GL JS, estilo gratuito do OpenFreeMap, devices protegidos por referências temporárias, marcadores de reports e linhas temporais por device.
INPUT: fluxo existente de lista de devices, solicitação FCM e descriptografia de localizações; fixtures sintéticas do modo `--demo`.
OPERATION: criação de `MapApp`, servidor HTTP local, API JSON, frontend responsivo, modo demo, abertura automática do navegador e retorno estruturado dos reports existentes.
EXPECTED OUTPUT: `python main.py` inicia o modo real; `python main.py --demo` inicia dados sintéticos; ambos servem o mapa em `http://127.0.0.1:8765/`.
ACCEPTANCE CRITERIA: nenhum ID canônico, token ou chave é enviado ao navegador; reports geográficos contêm latitude/longitude válidas; múltiplos reports do mesmo device formam uma linha temporal; login/rede só começam após ação explícita na interface.
LOCAL TEST: `python -m compileall -q main.py MapApp NovaApi tests`; `python -m unittest discover -s tests -v`; `node --check MapApp/static/app.js`; varredura de padrões de segredo.
REUSABLE RULE: o frontend usa somente referências temporárias e DTOs geográficos; o backend mantém IDs canônicos, autenticação e criptografia. Todo teste automatizado usa provider sintético.
DEPENDENCIES: Python padrão para o servidor; dependências preexistentes do GoogleFindMyTools apenas no modo real; MapLibre GL JS 6.15.0 e OpenFreeMap Liberty carregados no navegador.
NEXT BLOCK: MAP-003 — validar visualmente, em navegador controlado, os botões Conectar, Localizar e Localizar todos; depois ampliar os testes de contrato e falhas.

STATUS: COMPLETO NO CÓDIGO E NOS TESTES LOCAIS. A renderização visual ainda não foi observada porque não havia ferramenta de controle de navegador disponível nesta execução.

## Correção MAP-002-FIX-001

BLOCK-ID: MAP-002-FIX-001
TYPE: corrigir
DESCRIPTION: corrigir mapa-base branco no Brave fazendo proxy local e restrito dos recursos OpenFreeMap.
INPUT: interface e marcadores carregados, mas estilo vetorial externo sem renderização.
OPERATION: encaminhar `/map-assets/*` somente para `tiles.openfreemap.org`, reescrever URLs do estilo/tilejson para mesma origem, manter cache de sessão e exibir falhas do mapa na interface.
EXPECTED OUTPUT: ruas, áreas, nomes e demais elementos do mapa-base aparecem atrás dos reports.
ACCEPTANCE CRITERIA: estilo e sub-recursos usam `127.0.0.1`; nenhuma URL arbitrária é aceita pelo proxy; reports continuam intactos.
LOCAL TEST: suíte HTTP inclui reescrita do estilo, bloqueio de origem externa no JSON e cabeçalho de cache.
REUSABLE RULE: recursos cartográficos de terceiro que falharem sob proteção do navegador devem passar por proxy de origem fixa e allowlist, nunca por proxy de URL aberto.
DEPENDENCIES: OpenFreeMap; servidor Python local existente.
NEXT BLOCK: reiniciar o processo e validar visualmente o mapa-base no Brave.

## Correção MAP-002-FIX-002

BLOCK-ID: MAP-002-FIX-002
TYPE: corrigir
DESCRIPTION: substituir MapLibre/WebGL por Leaflet/raster após o proxy vetorial continuar em branco no Brave.
INPUT: controles e marcadores HTML visíveis, mas canvas cartográfico sem ruas ou nomes.
OPERATION: Leaflet 1.9.4, tiles raster OSM por proxy localhost restrito, cache de sete dias no navegador, círculos de precisão e linhas temporais.
EXPECTED OUTPUT: mapa-base raster renderizado sem depender de WebGL ou Web Worker.
ACCEPTANCE CRITERIA: tile PNG retorna pela mesma origem; frontend não referencia OpenFreeMap/MapLibre; reports continuam posicionados e enquadrados.
LOCAL TEST: compile, quatro testes HTTP, sintaxe JavaScript e download real de tile raster.
REUSABLE RULE: quando WebGL não é confiável no navegador-alvo, preferir renderização raster progressiva com fallback explícito.
DEPENDENCIES: Leaflet 1.9.4; tiles padrão OpenStreetMap sujeitos à política de uso.
NEXT BLOCK: reiniciar e validar visualmente no Brave.
