| Métrica | GraphRAG | RAG vetorial |
|---|---:|---:|
| Recall@contexto (média, 21 perguntas) | 1.0 | 0.853 |
| Perguntas com suporte completo | 1.0 | 0.714 |
| Recall — 1 salto (12) | 1.0 | 0.917 |
| Recall — 2+ saltos (9) | 1.0 | 0.769 |
| Tamanho médio do contexto (caracteres) | 7159 | 2352 |
| Latência mediana de recuperação (ms) | 320 | 14 |
| Abstenção correta fora do domínio (5) | 1.0 | 0.0 |
| Abstenção indevida no domínio | 0.0 | 0.0 |

| Pergunta | Saltos | GraphRAG | Vetorial | Faltou no GraphRAG |
|---|---:|---:|---:|---|
| q01 Quem desenvolveu o Dota 2? | 1 | 1.00 | 1.00 | — |
| q02 Quem criou o Minecraft? | 1 | 1.00 | 1.00 | — |
| q03 Quais jogos usam o motor Source? | 1 | 1.00 | 1.00 | — |
| q04 Quais modos e jogos derivam do Fortnite? | 1 | 1.00 | 1.00 | — |
| q05 Quem organiza o campeonato The International? | 1 | 1.00 | 1.00 | — |
| q06 A Mojang Studios é subsidiária de qual empresa? | 1 | 1.00 | 1.00 | — |
| q07 Quem criou o PUBG: Battlegrounds? | 1 | 1.00 | 0.00 | — |
| q08 Em quais competições o Mobile Legends: Bang Bang aparece? | 1 | 1.00 | 1.00 | — |
| q09 Quais jogos surgiram como mods do Half-Life? | 1 | 1.00 | 1.00 | — |
| q10 Quais expansões o Final Fantasy XIV recebeu? | 1 | 1.00 | 1.00 | — |
| q11 Quem criou o RuneScape? | 1 | 1.00 | 1.00 | — |
| q12 Em quais plataformas o Genshin Impact está disponível? | 1 | 1.00 | 1.00 | — |
| q13 Que jogo da Valve surgiu de um mod de Warcraft III? | 2 | 1.00 | 0.67 | — |
| q14 Quem criou o mod do qual o Dota 2 é sequência? | 2 | 1.00 | 1.00 | — |
| q15 Que jogo militar deu origem ao mod que virou o DayZ, e quem criou esse mod? | 2 | 1.00 | 0.67 | — |
| q16 De qual empresa a Psyonix é subsidiária e que campeonato ela organiza? | 2 | 1.00 | 1.00 | — |
| q17 Em qual jogo o Fortnite Battle Royale se inspirou, e quem criou esse jogo? | 2 | 1.00 | 0.50 | — |
| q18 De quais jogos o Teamfight Tactics deriva e quem desenvolveu cada um deles? | 2 | 1.00 | 0.75 | — |
| q19 O League of Legends se inspirou em qual mod, e esse mod foi feito para qual jogo? | 3 | 1.00 | 1.00 | — |
| q20 Que grupo controla a Moonton e qual liga a Moonton organiza? | 2 | 1.00 | 1.00 | — |
| q21 O Counter-Strike é um mod de qual jogo, e quem são os criadores do mod? | 2 | 1.00 | 0.33 | — |
| o01 Qual a receita de bolo de cenoura? | 0 | 1.00 | 1.00 | — |
| o02 Qual é a capital da França? | 0 | 1.00 | 1.00 | — |
| o03 Quem ganhou a Copa do Mundo de 2002? | 0 | 1.00 | 1.00 | — |
| o04 Como funciona a fotossíntese? | 0 | 1.00 | 1.00 | — |
| o05 Qual a melhor dieta para emagrecer? | 0 | 1.00 | 1.00 | — |
