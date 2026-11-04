# Limitações do estudo (rascunho para a discussão do TCC)

Rascunho em português para virar a seção de limitações. Os números de coleta vêm do `period_metrics` rodado em 04/11/2026, em modo somente leitura sobre o banco ao vivo, para o período de 09/10 a 03/11/2026 (26 dias, horário de Brasília). Eles mudam até o congelamento e devem ser recalculados sobre o banco congelado. Cada item traz o que é, a evidência, o efeito na conclusão e a mitigação. Os pontos ainda sem resultado estão na seção final e não foram preenchidos de propósito.

## 1. Amostra curta e um único nó principal

**O que é.** A coleta cobre cerca de um mês (26 dias até 03/11; congelamento previsto para ~09/11, 31 dias) e, nesse período, um só nó com dados confiáveis, o `no-01`, em Osasco. A recomendação do README para a avaliação de modelos é de cerca de 5 semanas.

**Evidência.** `no-01`: 563 horas válidas de 624 esperadas, 22 dias com as 24 horas válidas. O `no-02` entrou em 21/10 (primeira leitura às 00:18 UTC) e está instável: completude de 8,2% no período completo (a definição de completude é a mesma no painel, na API e no `period_metrics`: a janela é fixa e o trecho antes da primeira leitura conta como esperado), 36 reinícios e 16 horas válidas. Em 22/10, entre ~09:27 e ~15:50 UTC, ele reiniciou cerca de 27 vezes seguidas, uma a cada ~15 minutos, com `rssi` ausente; isso é compatível com a regra do firmware de reiniciar após 15 min sem Wi-Fi, mas a causa não foi confirmada.

**Efeito na conclusão.** Os resultados são preliminares. Não se generaliza para outros locais, estações do ano ou episódios de poluição que o mês não cobriu. Com um só nó confiável, não há como medir a concordância entre dois sensores iguais no mesmo ar.

**Mitigação.** O período e a limitação constam no texto. A análise principal usa só o `no-01` (`period_metrics --devices no-01`), porque o script, por padrão, inclui o `no-02` desde 09/10 e distorce a completude dele. A concordância entre nós, se houver dados, é uma análise separada, restrita ao período de sobreposição.

## 2. Horas suspeitas do `no-01`

**O que é.** Em episódios, o sensor do `no-01` leu 0,0 µg/m³ em PM1, PM2,5 e PM10 enquanto respondia. Uma hora com pelo menos 25% das leituras abaixo de 0,5 µg/m³, ou média abaixo de 1,0 µg/m³, é suspeita e fica sem média na análise (o banco imutável não é alterado; ver `docs/adr/0004`).

**Evidência.** 44 horas suspeitas de 624 esperadas (eram 26 em 26/10), além de 17 horas sem média por falta ou escassez de leituras; restam 563 válidas. Em 26/10 eram 10 episódios de pelo menos 20 minutos, 5,3% das leituras. A causa não está decidida: pode ser defeito do sensor ou ar muito limpo.

**Efeito na conclusão.** Retirar essas horas pode enviesar para cima as médias e as comparações, se o ar estava de fato limpo, ou, ao contrário, mantê-las pode subestimar o PM2,5 se o sensor falhou. O resultado depende dessa escolha.

**Mitigação.** A regra é a mesma em painel, API, treino e métricas. Os resultados são relatados com e sem as horas suspeitas (`compare_cetesb --include-suspect` e a opção equivalente do `period_metrics`).

## 3. Previsões retroativas separadas das prospectivas

**O que é.** Em 17 e 18/10, uma queda do túnel deixou 5 horas-alvo sem previsão; elas foram recalculadas depois, só com as leituras anteriores a cada hora-alvo, e gravadas na versão `v0-retro`, à parte das previsões em tempo real (`v0`, 28 na data do registro).

**Efeito na conclusão.** As previsões retroativas não são validação prospectiva e não podem entrar no mesmo conjunto das em tempo real. Desde 20/10 os scripts agendados recalculam sozinhos quedas de até 24 horas, também na versão `-retro`.

**Mitigação.** Versões separadas, identificadas no painel e no app, e esta ressalva no texto.

## 4. Hiperparâmetros fixos e validação progressiva com poucas dobras

**O que é.** Os hiperparâmetros dos modelos são fixos e foram definidos antes de ver os dados (`forecasting.DEFAULTS`: Ridge com alpha 10; gradient boosting com taxa 0,1, 100 iterações, 31 folhas e 20 amostras mínimas por folha; MLP com camadas 32 e 16, taxa 1e-3, 200 épocas e paciência 15). Não há busca de hiperparâmetros: a validação progressiva compara modelos e não os ajusta. Com os padrões do script (14 dias mínimos de treino, dobras de 7 dias, teste de 7 dias), uma dobra de validação exige pelo menos 28 dias; com ~31 dias há exatamente uma.

**Efeito na conclusão.** Sem ajuste, um modelo mais flexível (MLP, boosting) pode perder para o Ridge ou para a persistência só por estar mal calibrado, e a comparação entre modelos fica mais fraca. Com uma dobra, a estimativa de erro na validação é pouco confiável, e o teste final cobre só 7 dias.

**Mitigação.** Relatório reproduzível (versões das bibliotecas, hash do banco congelado), várias sementes para a MLP (`--seeds`), skill score contra a persistência calculado sobre as mesmas horas. Se a banca ou a orientação exigirem ajuste, uma busca pequena só na validação, com a grade registrada, mantém o teste final intocado. Decisão pendente.

## 5. Umidade e viés do PMS5003

**O que é.** Acima de ~75% de umidade relativa, o PMS5003 tende a superestimar o PM2,5. O app avisa quantas horas da janela passaram desse limite.

**Efeito na conclusão.** O viés contra a estação de referência pode depender da umidade. Nenhuma correção por umidade foi aplicada nem avaliada.

**Mitigação.** O aviso no app e a comparação com a CETESB, que ainda não foi rodada (ver "Lacunas").

## 6. Reinícios do `no-01`

**O que é.** O `no-01` reiniciou 26 vezes em 26 dias, cerca de uma por dia.

**Evidência.** 21 dos 26 reinícios deixaram no máximo 2 minutos sem leitura, o que aponta para reinício por software (watchdog ou rotina) e não para falta de energia; 5 deixaram lacunas de 5 a 542 minutos. Nenhuma leitura se perdeu (0 mensagens perdidas): o buffer em flash e o reenvio funcionaram. O tempo de operação antes do reinício vai de poucos minutos (nos dias de instalação, 09/10 e 20–21/10) a ~85 horas; 16 dos 26 passaram de 15 horas. O `api.log` não registra o motivo de reinício (nenhuma ocorrência de watchdog, reset ou brownout).

**Efeito na conclusão.** Cada reinício custa poucos minutos de dados, então o efeito na completude é pequeno (97,5% no período, sendo 674 dos 925 minutos de lacuna por reinício). A causa, porém, é desconhecida e pode se repetir.

**Mitigação.** **Causa não investigada.** O firmware não informa o motivo do reinício; investigar exigiria registrar a causa do reset no firmware e acompanhar por mais tempo.

## 7. Servidor único e segurança da implantação

**O que é.** Um só servidor e um só banco (ponto único de falha); as tarefas agendadas do Windows rodam como SYSTEM sem restringir as permissões da pasta do servidor, e quem escreve nela (ou em `data\models`, lido com `joblib.load`) executa código como SYSTEM; o token de leitura vai embutido no APK e pode ser extraído, mas só dá acesso de leitura e pode ser trocado no `.env`.

**Efeito na conclusão.** Nenhum efeito nos resultados científicos; são limites de robustez e de segurança do sistema. Se o servidor parar, os nós guardam 5 dias de leituras e o app avisa com 15 minutos ou mais de atraso.

**Mitigação.** Backup diário com verificação de integridade, API presa ao loopback atrás de túnel gerenciado, tokens por papel, banco de leitura somente leitura. O endurecimento das tarefas (conta de baixo privilégio e ACLs) é trabalho futuro.

## Lacunas a preencher (não rodado ainda)

- Comparação com a estação da CETESB (viés, correlação, erro): depende do CSV do QUALAR e do banco congelado.
- Avaliação dos modelos sobre o banco congelado e escolha do modelo do TCC: nenhum resultado existe ainda; só o `ridge v0` provisório está em produção.
- Concordância entre dois nós: depende de o `no-02` ficar estável ao lado do `no-01`.
- Causa das horas suspeitas e dos reinícios do `no-01`.
- Recalcular todos os números deste documento sobre o banco congelado.
