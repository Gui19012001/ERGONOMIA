# NR-17 Visão — APK Android Local MVP

Este projeto é um APK de teste/validação do núcleo ergonômico.

## Arquitetura

Câmera física do tablet -> preview Kivy local -> frame reduzido -> ML Kit Pose Android -> 33 landmarks -> ângulos -> IRE/RULA/REBA.

O vídeo não é enviado para Streamlit e não abre o aplicativo externo de câmera.

## O que já está no projeto

- câmera traseira local incorporada no APK
- preview contínuo
- rotação configurável por `teste.env`
- ML Kit Pose em `STREAM_MODE`
- somente um frame de pose por vez, evitando backlog
- frame da IA reduzido para 640 px no lado maior
- esqueleto desenhado sobre o preview
- qualidade/cobertura corporal
- tronco, pescoço, braço, cotovelo, punho e joelhos
- IRE experimental
- RULA assistido
- REBA assistido
- tempo de exposição
- início/fechamento de ciclo
- captura de evidência com esqueleto e scores
- build GitHub Actions

## Por que ML Kit no APK

`mediapipe` Python possui binários nativos e não é um simples requirement do python-for-android.
O ML Kit Pose é um SDK Android nativo, possui 33 landmarks e modo de vídeo/streaming.
A lógica de ângulos, IRE, RULA e REBA continua em Python no próprio APK.

## Primeira compilação

1. Suba toda a pasta para um repositório GitHub.
2. Abra `Actions`.
3. Rode `Build NR17 Android APK`.
4. Baixe o artifact `nr17-visao-apk`.
5. Instale no tablet.

## Se a câmera vier girada

Altere no workflow ou crie `teste.env`:

CAMERA_PREVIEW_ROTATION=270
POSE_ROTATION=270

Teste também 90, 180 ou 0 conforme o tablet.

## Se a câmera traseira estiver invertida

CAMERA_TRASEIRA_INDEX=1

## Ajuste de desempenho

Padrão:
- preview: 1280x720
- pose: lado maior 640
- intervalo: 0,12 s (~8 análises solicitadas/s)

Para tablet mais fraco:
POSE_INPUT_LONG_SIDE=480
POSE_INTERVAL=0.16

Para tablet forte:
POSE_INPUT_LONG_SIDE=720
POSE_INTERVAL=0.10

## Nota metodológica

RULA/REBA neste MVP são assistidos. Fatores que a câmera 2D não determina com segurança
(carga, pega, torção, suporte, repetitividade etc.) estão neutros nesta primeira versão.
O APK é ferramenta de apoio à análise ergonômica e não declara conformidade automática com NR-17.
