# Frontend do Find Hub Map

Este documento descreve o frontend operacional servido por `main.py`: identidade visual, fluxo de uso, comportamento responsivo e validação local. A arquitetura completa e os limites da integração com o Google permanecem em [arquitetura.md](arquitetura.md).

## 1. Princípios

- O SQLite local é consultado antes de qualquer sincronização externa.
- O Google só é acessado depois de uma ação explícita do usuário e nunca no modo `--demo`.
- IDs canônicos, credenciais e payloads brutos não são enviados ao navegador.
- A lista de reports é a alternativa textual do mapa.
- Leaflet e OpenStreetMap permanecem identificados pela atribuição visível.
- A aplicação é uma ferramenta local e não deve ser publicada diretamente na internet.

## 2. Executar o frontend

### Demonstração local sem Google

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --demo
```

Acesse `http://127.0.0.1:8765/`. O modo demo usa devices e coordenadas sintéticos.

### Execução real local

```powershell
.\.venv\Scripts\python.exe main.py
```

A autenticação, quando necessária, acontece pelo fluxo interativo oficial em uma janela visível do Chrome. Nunca cole credenciais no terminal nem publique `Auth/secrets.json`.

### Docker em modo demo

```powershell
docker compose up --build --detach app
docker compose ps
python scripts/container_smoke.py
```

O endpoint continua sendo `http://127.0.0.1:8765/`. Para os modos real e de testes, consulte [CONTAINER_RUNTIME.md](CONTAINER_RUNTIME.md).

## 3. Fluxo da interface

1. Ao abrir, o frontend carrega devices e últimas posições do cache SQLite.
2. **Sincronizar devices** consulta a integração configurada e atualiza o cadastro local.
3. **Atualizar localizações** solicita a posição mais recente de todos os devices carregados.
4. **Atualizar**, no card de um device, atualiza apenas aquele item.
5. **Histórico** carrega as posições anteriores e desenha sua sequência no mapa.
6. Um report da lista pode ser acionado por clique, `Enter` ou `Espaço` para centralizar o mapa.
7. **Enquadrar reports** ajusta a câmera para todos os pontos visíveis e transfere o foco para o mapa.

Jobs assíncronos exibem progresso e terminam com estado textual de sucesso ou erro. Botões incompatíveis com o estado atual permanecem desabilitados.

## 4. Identidade visual Kezpo

A fonte de verdade da marca, os valores observados e as regras de uso estão em [KEZPO_DESIGN_SYSTEM.md](KEZPO_DESIGN_SYSTEM.md).

- `Outfit` local: títulos e nome do produto;
- `Inter` local: corpo, botões, labels e dados;
- navy: áreas institucionais e chrome do mapa;
- azul: ação primária e foco;
- azul-claro: report da rede Find Hub;
- dourado: report próprio e destaques seletivos;
- superfícies claras: painel, cards e controles operacionais.

Os arquivos versionados ficam em `MapApp/static/assets/`. A origem, o tipo e o hash de cada asset são registrados nos manifestos de `brand/` e `fonts/`. O frontend não busca logo nem fontes no site institucional em runtime.

## 5. Comportamento responsivo

| Largura | Comportamento |
|---|---|
| `< 640px` | mapa no topo; painel inferior; ações em uma coluna |
| `640–767px` | mapa no topo; painel inferior; ações em duas colunas |
| `768–1023px` | painel recolhível sobre o mapa e controles reposicionados na área livre |
| `1024–1279px` | painel lateral persistente de até `380px` |
| `1280–1399px` | painel lateral persistente de `400px` |
| `≥ 1400px` | painel lateral persistente de `420px` e mapa com maior área útil |

O botão **Ocultar painel** aparece em tablet e smartphone. Ao recolher o painel, o mapa ocupa a área liberada e recalcula suas dimensões.

## 6. Acessibilidade e movimento

- skip link leva diretamente ao mapa e aparece imediatamente ao receber foco;
- foco visível em botões, links, cards de report e mapa;
- controles principais com alvo mínimo de `44 × 44px`;
- estados comunicados por texto e ícone, não somente por cor;
- reports são botões com nomes acessíveis;
- mapa possui nome acessível e equivalente textual na lista;
- `prefers-reduced-motion: reduce` remove transições decorativas e evita animação de câmera.

## 7. Mapa e conectividade

O Leaflet é carregado por CDN e os tiles vêm do OpenStreetMap, portanto o mapa cartográfico precisa de acesso à rede. Devices e reports ainda podem ser lidos do SQLite quando tiles externos estiverem indisponíveis.

Os testes E2E substituem tiles reais por uma imagem sintética local. Por isso as capturas automatizadas mostram um fundo uniforme; marcadores, controles e camadas continuam sendo exercitados sem depender da internet.

## 8. Testes

### Suíte determinística

```powershell
python -B -m unittest discover -s tests -v
```

Essa suíte não autentica no Google e não usa coordenadas reais.

### Navegador e responsividade

```powershell
New-Item -ItemType Directory -Force .artifacts | Out-Null
$env:RUN_BROWSER_E2E = '1'
$env:BROWSER_E2E_SCREENSHOT = (Resolve-Path .artifacts).Path + '\kezpo-desktop-visual-qa.png'
$env:BROWSER_RESPONSIVE_SCREENSHOT_DIR = (Resolve-Path .artifacts).Path
python -B -m unittest tests.e2e.test_frontend_v1 -v
```

O E2E usa Chrome/Selenium e valida os fluxos de cache, sincronização demo, atualização, histórico, teclado, painel responsivo, ausência de overflow horizontal e movimento reduzido. Ele gera evidências para `1440`, `1300`, `1200`, `900`, `700` e `390` pixels.

`.artifacts/` é local e ignorado pelo Git. As capturas podem conter informações visíveis na interface; não use conta real para gerar material destinado a issues ou pull requests.

## 9. Critério de aceite visual

Uma mudança de frontend só está pronta quando:

1. preserva sincronização, atualização individual, atualização geral e histórico;
2. mantém a atribuição Leaflet/OpenStreetMap visível;
3. não cria overflow horizontal nas larguras testadas;
4. mantém controles e conteúdo utilizáveis com o painel aberto e recolhido;
5. funciona por teclado e respeita movimento reduzido;
6. passa pela suíte determinística e pelo E2E opt-in;
7. não registra credenciais, IDs privados ou coordenadas reais em screenshots e logs.

## 10. Regra reutilizável

Toda nova faixa responsiva ou interação visual deve entrar no mesmo ciclo: contrato documentado, teste local reproduzível, captura sanitizada e inspeção visual antes de commit.
