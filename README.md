README do Projeto: Comparação de Imagens de Partes da Aeronave (Baseline SSIM + ORB)
Visão Geral:
Este projeto tem como objetivo desenvolver um sistema para comparar automaticamente duas imagens da mesma parte de uma aeronave – uma imagem de referência “antes” e outra imagem de inspeção “depois” – a fim de identificar diferenças visuais relevantes (potenciais danos ou alterações). A solução inicial emprega métodos clássicos de visão computacional (não há uso de deep learning neste estágio) combinando o cálculo do SSIM (Índice de Similaridade Estrutural) e a comparação de features locais via ORB.
Objetivo: Detectar e destacar discrepâncias significativas entre a foto de referência e a foto atual de uma peça ou região da aeronave, fornecendo um escore de similaridade e indicando visual e textualmente se há suspeita de dano ou mudança estrutural.
Não-objetivos (Fora do Escopo no MVP):

Classificação de tipo de dano: Nesta primeira versão não diferenciamos o tipo de defeito (ex.: trinca vs. corrosão), apenas sinalizamos se existe alguma diferença significativa.
Detecção sem alinhamento complexo: Pressupõe-se que as imagens foram capturadas de ângulos e posições semelhantes; o sistema não realiza correção de perspectiva ou registro geométrico avançado. Pequenos desalinhamentos podem reduzir a eficácia de detecção.
Uso de redes neurais: O MVP não utiliza machine learning supervisionado ou redes neurais; ele não aprende padrões de dano. Em vez disso, aplica métricas fixas. Isso significa que, inicialmente, pode não capturar diferenças muito sutis ou sob condições muito diferentes de iluminação/perspectiva. Futuramente, pretende-se incorporar deep learning para maior robustez, mas isso não faz parte deste escopo inicial.
Decisões autônomas finais: O sistema não substitui o discernimento do inspetor humano. Ele serve como ferramenta de auxílio – cabe ao inspetor validar os alertas fornecidos.

Workflow do Pipeline (Passo a Passo):

Carregamento das Imagens: Leitura das duas imagens de entrada (uma imagem de referência “antes” e uma imagem atual “depois”) a partir de arquivos no disco.
Pré-processamento: Redimensionamento de ambas as imagens para um tamanho padrão (ex.: 256×256 pixels) para permitir uma comparação direta. Normalização dos valores de pixel para faixa [0.0, 1.0] (necessário para o cálculo correto do SSIM). (Opcional: conversão para escala de cinza para focar apenas em estrutura/luminância; nesta versão manteremos as imagens RGB mas poderemos converter dentro do cálculo do SSIM para obter o mapa de luminância).
Cálculo do SSIM: Utilizando a função tf.image.ssim do TensorFlow, calculamos o Índice de Similaridade Estrutural entre as duas imagens. Obtemos:

Score SSIM Global: um valor entre -1 e 1 (no nosso caso tratado como 0 a 1, já que imagens não serão negativas) que indica quão similares as imagens são em termos de estrutura visual (1.0 = imagens idênticas).
Mapa de Diferenças (SSIM local): uma matriz de mesmo tamanho das imagens, onde cada valor representa a similaridade local. Podemos derivar dele uma máscara de diferenças marcando onde a similaridade local é baixa (i.e., áreas possivelmente alteradas).


Extração de Features Locais (ORB): Utilizando o OpenCV, aplicamos o detector ORB em ambas as imagens para obter pontos-chave (features) e seus descritores. Em seguida, usamos um matcher (força bruta com norma de Hamming) para encontrar correspondências entre descritores das duas imagens. Resultado: um conjunto de correspondências encontradas. A partir delas, calculamos um escore de similaridade de features locais – por exemplo, poderíamos usar a porcentagem de correspondências válidas em relação ao número total de features detectadas, ou uma métrica inversamente proporcional à distância média das melhores matches. Neste MVP, adotaremos uma métrica simples normalizada de 0 a 1 (1 = imagens com muitas correspondências fortes, 0 = nenhuma correspondência) baseada nas distâncias dos descritores correspondentes.
Combinação de Métricas e Decisão: Unimos a informação do SSIM e do ORB para formar um score final de similaridade. Por exemplo, podemos calcular a média entre o SSIM global e o score ORB. Em seguida, comparamos esse score final a um threshold pré-definido (por exemplo, 0.80 ou 80%). Se o score final estiver abaixo do threshold, significa que as imagens são insuficientemente semelhantes – o sistema então gera um alerta de diferença detectada. Se o score final estiver acima do threshold, considera-se que as imagens estão essencialmente similares e não há indício forte de alteração.

Detalhe: O threshold pode ser ajustado conforme experiências futuras. Um threshold mais alto (próximo de 1.0) tornará o sistema mais sensível (detectando qualquer pequena diferença, mas possivelmente gerando alarmes falsos), enquanto um threshold mais baixo focará apenas em mudanças maiores (podendo perder alguns danos sutis). Para começar, definiremos um valor razoável (ex.: 0.8) e refinaremos conforme necessário.


Geração de Máscara de Diferença: A partir do mapa local de SSIM (ou mesmo da diferença absoluta de pixel entre as imagens, complementado pelas correspondências ORB), geramos uma máscara binária que indica onde as diferenças ultrapassam um certo critério. Essa máscara marca regiões possivelmente problemáticas (por exemplo, áreas com SSIM local muito baixo ou sem correspondências de features).
Saída e Apresentação: Por fim, o sistema apresenta os resultados ao usuário:

Um score de similaridade estrutural (ex.: “Similaridade estrutural: 92%”).
Uma mensagem de recomendação (ex.: “Diferença detectada – inspeção manual recomendada” ou “Nenhuma diferença significativa detectada”).
Uma visualização mostrando as duas imagens: a foto de referência e a foto atual, lado a lado. Sobre a foto atual, as regiões com diferenças detectadas são destacadas em vermelho semi-transparente (ou contornadas em vermelho) para focar a atenção do inspetor nesses pontos. Isso agiliza a análise humana, facilitando a compreensão do que o algoritmo identificou.



Decisões Técnicas & Trade-offs:

Optamos por um baseline sem aprendizado de máquina porque é rápido de implementar e interpretável: sabemos exatamente o que está sendo medido (diferentemente de um modelo de rede neural, que age como uma “caixa preta”). O trade-off é que podemos ter menor sensibilidade a diferenças muito sutis ou grande suscetibilidade a alterações de iluminação e posicionamento. A mitigação é garantir fotos consistentes (mesma posição e iluminação) e, no futuro, evoluir para modelos aprendidos.
SSIM foi escolhido por ser uma métrica bem estabelecida para quantificar a similaridade de imagens de forma perceptualmente significativa. Ele avalia mudanças em termos de luminância, contraste e estrutura, se alinhando bem com o que um inspetor humano consideraria uma alteração visível. O SSIM também pode fornecer um “mapa de diferenças” que podemos usar para localização espacial de alterações.
ORB + correspondência de features complementa o SSIM, pois pode ser mais robusto para certos tipos de diferenças estruturais (ele foca em padrões locais específicos). O trade-off do ORB é que ele não produz um mapeamento denso de diferenças (apenas pontos correspondentes), e seu funcionamento pode ser afetado por superfícies pouco texturizadas ou com padrões repetitivos. Entretanto, se um dano introduzir novos contornos/texturas, o ORB possivelmente captará features ali sem correspondência na imagem antiga, sinalizando a mudança.
Pipeline vs. Modelo Monolítico: Estamos deliberadamente separando a lógica em etapas modulares (carregar dados, calcular métricas, fundir resultados, exibir) em vez de fazer uma única função gigante. Isso torna o código mais legível, testável e fácil de atualizar. Por exemplo, poderemos substituir a etapa de ORB por outra técnica (talvez FLANN matching ou um deep embedding) no futuro sem reescrever todo o pipeline.

Estrutura de Pastas e Módulos:
Organizamos o projeto em sub-pacotes dentro de src/ para refletir as etapas do pipeline:
src/
├── preprocessing/
│   └── image_loader.py      # Funções para carregar e pré-processar imagens (leitura, resize, normalização, etc.)
├── similarity/
│   ├── ssim.py              # Funções para calcular SSIM global e mapa de diferença
│   └── orb.py               # Funções para extrair features ORB e computar similaridade por correspondências locais
├── fusion/
│   └── decision.py          # Função para combinar os escores (SSIM, ORB) e tomar decisão com base em threshold
├── visualization/
│   └── viewer.py            # Funções para destacar diferenças nas imagens e exibí-las lado a lado com anotações
└── pipeline.py              # Script principal que integra todos os módulos acima e executa o fluxo completo

(Além disso, há um diretório data/ contendo imagens de exemplo para testes: data/reference/ com imagens de referência e data/inspection/ com as imagens correspondentes das inspeções.)
Fluxo de Execução (Resumo Técnico):

Etapa de Dados: pipeline.py usa funções de src/preprocessing/image_loader.py para criar um tf.data.Dataset dos pares de caminhos de imagem. Isso permite carregar e preprocessar as imagens em lote e de forma eficiente (com paralelismo).
Etapa de Similaridade: Para cada par de imagens, calculamos o SSIM (em src/similarity/ssim.py) e o score ORB (em src/similarity/orb.py).

O SSIM será calculado via TensorFlow (tf.image.ssim), dentro do pipeline, possivelmente usando tf.map_fn ou aplicando a função a cada par do Dataset. Retorna um valor de similaridade e podemos também obter o mapa de similaridade local (diferenças) se necessário.
O cálculo de ORB não é nativamente suportado dentro do grafo TensorFlow, então usaremos tf.numpy_function ou executaremos fora do pipeline. Nessa função, convertendo temporariamente os tensores para numpy arrays e usando OpenCV (cv2) para obter keypoints, descritores e matches. O resultado será um score (float) representando a fração/qualidade das correspondências.


Etapa de Fusão: Em src/fusion/decision.py, definimos um threshold (inicialmente 0.8) e combinamos os dois escores: se ambos os indicadores de similaridade estiverem altos, o final_score será alto; se um despencar devido a um dano, a média cairá abaixo do threshold. Implementamos a função fuse_and_decide para retornar o final_score e a mensagem de recomendação.
Etapa de Visualização: Em src/visualization/viewer.py, definimos:

Uma função highlight_differences(image, mask) que pinta os pixels da imagem atual em vermelho onde o mask (derivado do mapa de diferenças do SSIM) indica alteração.
Uma função show_comparison(image_ref, image_cur, mask, scores, recommendation) para exibir, usando Matplotlib, a imagem de referência e a imagem atual lado a lado. A imagem atual será exibida já com as marcações vermelhas por meio de highlight_differences. O título das imagens ou anotações incluirão os valores dos scores (ex.: “SSIM: 0.94”) e possivelmente do score ORB, e a recomendação final será exibida como legenda ou texto abaixo.



Pontos de Evolução Futura:
O MVP fornecerá uma base prática e testável. Com ele funcionando:

Podemos coletar feedback sobre casos de falso positivo (sistema indicando dano onde não há, possivelmente por diferença de iluminação, etc.) e falso negativo (sistema perdendo um dano real), para ajustar processamento ou thresholds.
Assim que tivermos um dataset maior de imagens com e sem danos verificados, planeja-se treinar uma Rede Neural Siamese para aprender a métrica de similaridade, possivelmente substituindo ou complementing o método atual. Um backbone CNN ou ViT pré-treinado poderia extrair embeddings robustos às variações de contexto e então usaríamos uma loss contrastiva/triplet para posicionar imagens similares próximas neste espaço. Isso tende a melhorar a detecção de diferenças sutis e a reduzir sensibilidades a pequenas mudanças de iluminação/ângulo.
Futuramente, podemos integrar este sistema a flujos de trabalho de manutenção: por exemplo, vinculá-lo a um banco de dados de inspeção, ou habilitar captura de imagens via drone ou smartphone e processamento em tempo real com esse algoritmo. Também podemos evoluir o pipeline para identificar automaticamente qual região da aeronave a imagem pertence (usando metadados ou visão computacional) e recuperar a referência correta de forma autônoma.

aircraft_image_comparison/
├── data/
│   ├── reference/         # Imagens estáticas de referência ("antes")
│   └── inspection/        # Imagens capturadas durante inspeções ("depois")
├── src/
│   ├── preprocessing/
│   │   └── image_loader.py    # Funções para carregar & pré-processar imagens (leitura, resize, normalização)
│   ├── similarity/
│   │   ├── ssim.py            # Cálculo do SSIM global e mapa de diferenças
│   │   └── orb.py             # Extração de features ORB e cálculo de similaridade por correspondências
│   ├── fusion/
│   │   └── decision.py        # Combinação dos escores (SSIM/ORB) e decisão com threshold (alerta ou não)
│   ├── visualization/
│   │   └── viewer.py          # Funções de visualização: destaque de áreas diferentes e exibição lado a lado
│   └── pipeline.py            # Script principal integrando todos os módulos acima
└── README.md                  # Documentação geral do projeto (este arquivo)