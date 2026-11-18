# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Streamlit (com grafo pyvis/vis-network) como interface, chamando o pipeline Python direto; FastAPI opcional para acesso por HTTP; Neo4j 5 (GDS). O usuário trocou o React por Streamlit em 18/11/2026.

## Users

Grupo de 4 a 6 alunos de Ciência da Computação (P7/P8) que apresenta o projeto final da disciplina Tendências em Ciência da Computação, e a banca/professor que avalia a defesa ao vivo. Na defesa, um aluno faz perguntas em português e a banca precisa ver, na tela projetada, de onde veio cada resposta.

## Product Purpose

Assistente GraphRAG/KAG sobre jogos online, construído a partir de 65 artigos da Wikipedia (MOBAs, battle royale, FPS, MMOs, sandbox, mobile, e-sports). O domínio mudou de artigos de IA do arXiv para jogos online em 18/11/2026. Responde perguntas multi-hop ancorando cada afirmação em triplas do grafo de conhecimento (Neo4j) e mostra o subgrafo usado, as consultas Cypher executadas, os nós consultados e o nível de confiança. Sucesso: a banca entende a resposta e a sua procedência sem explicação extra.

## Positioning

A resposta não vem sozinha: vem com o caminho no grafo que a sustenta (triplas com a frase literal do artigo como evidência), e o sistema recusa responder quando a pergunta não toca o grafo.

## Operating Context

Demonstração ao vivo em projetor, normalmente em notebook com tela de 1280 a 1920 px. Rubrica do professor: modelagem (25%), engenharia GraphRAG (30%), interface e explicabilidade (20%), código e artigo (25%). Sem chave da API, o sistema roda em modo extrativo (respostas montadas das triplas).

## Capabilities and Constraints

- Busca híbrida: vetorial (e5 multilíngue), fulltext Lucene e dicionário de entidades; travessia de 1 a 3 saltos; allShortestPaths entre âncoras; consulta dirigida pela intenção da pergunta; PageRank e Louvain (GDS).
- Modos de recuperação: grafo (GraphRAG) e vetorial puro (baseline), para comparação na banca.
- Geração: Claude quando há ANTHROPIC_API_KEY; extrativa sem chave.
- Interface em português.

## Evidence on Hand

- data/raw/articles.json: introduções reais de 65 artigos da Wikipedia (CC BY-SA 4.0).
- data/extracted/*.json: entidades e relações extraídas, cada relação com evidência literal.
- results/eval.md: avaliação GraphRAG vs RAG vetorial (26 perguntas).
- Nenhum depoimento, métrica de uso ou cliente: não inventar.

## Product Principles

1. Procedência visível antes de eloquência: toda afirmação aponta para uma tripla ou trecho.
2. Dizer "não sei" é um resultado correto.
3. O grafo é o protagonista da demonstração, não um enfeite.
4. Legível no projetor: contraste alto, texto que se lê do fundo da sala.
