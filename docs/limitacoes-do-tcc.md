# Limitações do estudo (rascunho para a discussão do TCC)

Rascunho em português para virar a seção de limitações. Os números vêm do banco congelado em 09/11/2026 (`pm25-congelado-2026-10-09_2026-11-08.db`, SHA-256 `2d6dfd45891e8d91f6eb34afda3748a39c38a84b4c04af94dbf206c93f293e87`), que cobre 09/10 a 08/11/2026 (31 dias, horário de Brasília), pelo `period_metrics`, pelo `compare_cetesb` e pelo `train_forecast`. A análise principal usa só o `no-01`. Cada item traz o que é, a evidência, o efeito na conclusão e a mitigação. Os pontos ainda sem resultado estão na seção final e não foram preenchidos de propósito.

## 1. Amostra curta e nós em locais diferentes

**O que é.** A coleta cobre 31 dias, abaixo das cerca de 5 semanas que o README recomenda para a avaliação de modelos. Só um nó tem dados confiáveis, o `no-01`, em Osasco (bairro Veloso, no apoio externo de uma janela, coberto por uma estrutura da casa, a 1,1 m do chão). O `no-02` entrou em 21/10 e mede na zona sul da capital, a mais de 15 km do `no-01`, então os dois nós não medem o mesmo ar.

**Evidência.** `no-01`: completude de 97,2% (43.390 de 44.640 minutos esperados), 651 horas válidas de 744 esperadas e 26 dias com média de 24 h válida. `no-02`, na mesma janela de 31 dias: completude de 18,6% (a definição é a mesma no painel, na API e no `period_metrics`: a janela é fixa e o trecho antes da primeira leitura conta como esperado), 37 reinícios, 76 horas válidas e 59 suspeitas. Em 22/10, entre ~09:27 e ~15:50 UTC, ele reiniciou cerca de 27 vezes seguidas, uma a cada ~15 minutos, com `rssi` ausente; isso é compatível com a regra do firmware de reiniciar após 15 min sem Wi-Fi, mas a causa não foi confirmada. Em 05 e 06/11 ele enviou cerca de 1.400 leituras por dia, com uma interrupção em 07/11.

**Efeito na conclusão.** Os resultados são preliminares. Não se generaliza para outros locais, estações do ano ou episódios de poluição que o mês não cobriu. Com os nós em locais diferentes, não há como medir a concordância entre dois sensores iguais no mesmo ar.

**Mitigação.** O período e a limitação constam no texto. A análise principal usa só o `no-01` (`period_metrics --devices no-01`, `compare_cetesb --devices no-01`, `train_forecast --devices no-01`). A rodada do `train_forecast` com os dois nós fica como análise de sensibilidade. A concordância entre sensores exige um período com os dois lado a lado: o `no-02` será levado para junto do `no-01`, e a análise será separada e restrita ao período de sobreposição, com a data da mudança registrada.

## 2. Horas suspeitas do `no-01`

**O que é.** Em episódios, o sensor do `no-01` leu 0,0 µg/m³ em PM1, PM2,5 e PM10 enquanto respondia. Uma hora com pelo menos 25% das leituras abaixo de 0,5 µg/m³, ou média abaixo de 1,0 µg/m³, é suspeita e fica sem média na análise (o banco imutável não é alterado; ver `docs/adr/0004`).

**Evidência.** 70 horas suspeitas de 744 esperadas (9,4%; eram 26 em 26/10 e 44 em 04/11), além de 23 horas sem média por falta ou escassez de leituras; restam 651 válidas. A causa não está decidida: pode ser defeito do sensor ou ar muito limpo. Na comparação com a CETESB Osasco, incluir as horas suspeitas melhora o ajuste (711 horas pareadas, viés de +6,8 µg/m³ e r de 0,45, contra 641 horas, +8,3 µg/m³ e r de 0,43 sem elas). É uma pista de que parte dos episódios pode ser ar limpo, ainda não verificada hora a hora.

**Efeito na conclusão.** Retirar essas horas pode enviesar para cima as médias e as comparações, se o ar estava de fato limpo, ou, ao contrário, mantê-las pode subestimar o PM2,5 se o sensor falhou. O resultado depende dessa escolha.

**Mitigação.** A regra é a mesma em painel, API, treino e métricas. Os resultados são relatados com e sem as horas suspeitas (`compare_cetesb --include-suspect` e a opção equivalente do `period_metrics`; as saídas ficam em `resultados/` e em `resultados/com_horas_suspeitas/`).

## 3. Previsões retroativas separadas das prospectivas

**O que é.** Em 17 e 18/10, uma queda do túnel deixou 5 horas-alvo sem previsão; elas foram recalculadas depois, só com as leituras anteriores a cada hora-alvo, e gravadas na versão `v0-retro`, à parte das previsões em tempo real (`v0`, 28 na data do registro).

**Efeito na conclusão.** As previsões retroativas não são validação prospectiva e não podem entrar no mesmo conjunto das em tempo real. Desde 20/10 os scripts agendados recalculam sozinhos quedas de até 24 horas, também na versão `-retro`.

**Mitigação.** Versões separadas, identificadas no painel e no app, e esta ressalva no texto.

## 4. Hiperparâmetros fixos e validação progressiva com poucas dobras

**O que é.** Os hiperparâmetros dos modelos são fixos e foram definidos antes de ver os dados (`forecasting.DEFAULTS`: Ridge com alpha 10; gradient boosting com taxa 0,1, 100 iterações, 31 folhas e 20 amostras mínimas por folha; MLP com camadas 32 e 16, taxa 1e-3, 200 épocas e paciência 15). Não há busca de hiperparâmetros: a validação progressiva compara modelos e não os ajusta. Com os padrões do script (14 dias mínimos de treino, dobras de 7 dias, teste de 7 dias), uma dobra de validação exige pelo menos 28 dias; com 31 dias há exatamente uma.

**Evidência.** Só com o `no-01`: 494 horas completas, 91 horas na validação e 149 no teste final (31/10 a 07/11). RMSE no teste (µg/m³) e skill score sobre a persistência: persistência 7,08; Ridge 6,50 (+0,082); MLP 6,90 ± 0,15 (+0,025 ± 0,021, média de 5 sementes); gradient boosting 7,47 (−0,055). Com os dois nós juntos o quadro é o mesmo, com erros maiores (persistência 8,50; Ridge 8,05, +0,053; MLP 8,39 ± 0,11; gradient boosting 8,62), porque o teste inclui 27 horas do `no-02`.

**Efeito na conclusão.** Nenhum modelo supera a persistência de forma clara: o Ridge fica um pouco acima, a MLP é estatisticamente igual a ela e o gradient boosting fica pior. Com uma dobra e 149 horas de teste, a diferença do Ridge não é sólida. Sem ajuste, um modelo mais flexível (MLP, boosting) pode perder só por estar mal calibrado, e a comparação entre modelos fica mais fraca.

**Mitigação.** Relatório reproduzível (versões das bibliotecas, hash do banco congelado), várias sementes para a MLP (`--seeds`), skill score contra a persistência calculado sobre as mesmas horas. Os hiperparâmetros não foram alterados depois de ver o teste final. Se a banca ou a orientação exigirem ajuste, uma busca pequena só na validação, com a grade registrada, mantém o teste final intocado. Decisão pendente.

## 5. Umidade e viés do PMS5003

**O que é.** Acima de ~75% de umidade relativa, o PMS5003 tende a superestimar o PM2,5. O app avisa quantas horas da janela passaram desse limite.

**Evidência.** Das 641 horas pareadas com a CETESB, só 16 tiveram umidade média acima de 75% (viés de +21,4 µg/m³ nessas horas, contra +8,0 nas demais), o que não basta para correlação nem regressão. Pode ser que o BME280 meça a umidade do ar sob a cobertura, mais baixa que a do ambiente, ou do interior da caixa; isso não foi verificado.

**Efeito na conclusão.** O viés contra a estação de referência pode depender da umidade, mas a amostra não permite concluir. Nenhuma correção por umidade foi aplicada nem avaliada.

**Mitigação.** O aviso no app e a comparação com a CETESB, com a separação por umidade já calculada. Verificar a posição do BME280 e relatar a umidade como limitação.

## 6. Reinícios do `no-01`

**O que é.** O `no-01` reiniciou 32 vezes em 31 dias, cerca de uma por dia.

**Evidência.** 23 dos 32 reinícios deixaram no máximo 2 minutos sem leitura, 3 deixaram 3 minutos e 6 deixaram lacunas de 6 a 543 minutos (6, 26, 34, 52, 320 e 543); isso aponta para reinício por software (watchdog ou rotina) e não para falta de energia. Nenhuma leitura se perdeu (0 mensagens perdidas): o buffer em flash e o reenvio funcionaram. O tempo de operação antes do reinício vai de poucos minutos (nos dias de instalação, 09/10 e 20–21/10) a ~98 horas; 19 dos 32 passaram de 15 horas. O `api.log` não registra o motivo de reinício (nenhuma ocorrência de watchdog, reset ou brownout).

**Efeito na conclusão.** Cada reinício custa poucos minutos de dados, então o efeito na completude é pequeno (97,2% no período; 999 dos 1.250 minutos de lacuna foram por reinício e 251 pela borda inicial, antes da primeira leitura). A causa, porém, é desconhecida e pode se repetir.

**Mitigação.** **Causa não investigada.** O firmware não informa o motivo do reinício; investigar exigiria registrar a causa do reset no firmware e acompanhar por mais tempo.

## 7. Servidor único e segurança da implantação

**O que é.** Um só servidor e um só banco (ponto único de falha); as tarefas agendadas do Windows rodam como SYSTEM sem restringir as permissões da pasta do servidor, e quem escreve nela (ou em `data\models`, lido com `joblib.load`) executa código como SYSTEM; o token de leitura vai embutido no APK e pode ser extraído, mas só dá acesso de leitura e pode ser trocado no `.env`.

**Efeito na conclusão.** Nenhum efeito nos resultados científicos; são limites de robustez e de segurança do sistema. Se o servidor parar, os nós guardam 5 dias de leituras e o app avisa com 15 minutos ou mais de atraso.

**Mitigação.** Backup diário com verificação de integridade (em um HD separado do disco do banco), API presa ao loopback atrás de túnel gerenciado, tokens por papel, banco de leitura somente leitura, e cópia do banco congelado em dois discos. O endurecimento das tarefas (conta de baixo privilégio e ACLs) é trabalho futuro.

## 8. Comparação com a estação da CETESB: distância, ambiente e hora

**O que é.** A referência é a estação Osasco da CETESB (código 120, Av. dos Autonomistas, esquina com a Rua São Maurício, Vila Quitaúna, segundo documento da CETESB; o endereço não está bem documentado e um segundo candidato, Rua Tomé de Souza, 438, no Jardim D'Abril, foi descartado), com as médias horárias de MP2,5 do QUALAR. O `no-01` fica a cerca de 4,4 km dela (estimativa pelo eixo da Rua São Maurício e da rua do nó no OpenStreetMap, sem o número dos imóveis, com incerteza de poucas centenas de metros; com o segundo candidato seriam cerca de 2,5 km), no apoio externo de uma janela, coberto, a 1,1 m do chão e junto à fachada, enquanto a estação segue o padrão regulatório de instalação. O PMS5003 não foi calibrado.

**Evidência.** 641 horas pareadas (a CETESB tem 10 horas vazias nos 744 do arquivo). Média do nó 21,2 µg/m³ contra 12,9 da CETESB; viés de +8,3 µg/m³; MAE de 12,0; RMSE de 16,0; correlação de Pearson de 0,43 (R² de 0,18); reta do nó em função da CETESB com inclinação 0,82 e intercepto 10,6. Os valores da CETESB são inteiros.

**Efeito na conclusão.** O nó lê mais alto que a referência e acompanha pouco a variação horária dela. O r baixo mistura o erro do sensor, a distância entre os pontos, o microambiente (fachada, cobertura, altura) e a resolução inteira da estação; a comparação não separa essas causas. Ela não valida o PMS5003 como instrumento de referência.

**Mitigação.** Resultados relatados com e sem as horas suspeitas e separados por umidade. A distância e a descrição do ponto constam no texto. O rótulo de hora do QUALAR foi tratado como fim da hora (01:00 = 00:00 a 01:00), segundo a documentação do pacote qualR; com o rótulo como início, o r cai para 0,39 e o RMSE sobe para 16,4. A convenção precisa ser confirmada com a CETESB.

## Lacunas a preencher (não rodado ainda)

- Concordância entre dois nós: depende de levar o `no-02` para junto do `no-01` e de um período de sobreposição estável; os nós estão hoje em locais diferentes.
- Escolha do modelo do TCC e treino de uma versão nova para o job horário; decisão sobre a busca de hiperparâmetros.
- Causa das horas suspeitas e dos reinícios do `no-01`, e conferência hora a hora dos episódios suspeitos contra a CETESB.
- Coordenadas oficiais da estação Osasco, para substituir a distância estimada de 4,4 km; confirmação da convenção de hora do QUALAR.
- Posição do BME280 e o que a umidade medida representa.
