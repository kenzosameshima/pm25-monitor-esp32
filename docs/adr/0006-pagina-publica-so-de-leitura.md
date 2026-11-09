# A API publica uma página só de leitura, e o dashboard continua fora da internet

Para qualquer pessoa ver os dados sem instalar o Tailscale, o túnel passa a publicar também `/public`, além dos três caminhos da ADR 0003. É uma página gerada pela própria API, sem login, sem JavaScript e sem recurso externo, que mostra só o estado do ar de cada nó: a última leitura, a média de 24 horas, o gráfico das médias horárias e a previsão. O dashboard Streamlit continua só na tailnet. Ele traz a saúde da coleta, a avaliação dos modelos e as leituras por minuto, que dizem como o sistema funciona por dentro e precisam de contexto para não serem mal interpretadas.

## Considered Options

- **Publicar o dashboard pelo Funnel:** sem login, exporia tudo a qualquer um, e cada visita rodaria as consultas do Streamlit no servidor da residência.
- **Publicar o dashboard com login (`st.login` e um provedor OIDC):** protege, mas exige manter o provedor e as credenciais, e quem recebe o link precisa ter uma conta.
- **Compartilhar a máquina pelo Tailscale:** é grátis e não exige código, mas cada pessoa precisa instalar o app e ser convidada. Serve para a banca, não para um link aberto.

## Consequences

A página não pede token, então tudo o que ela mostra é público: pôr um item novo nela é decidir publicar aquele dado. O local do nó aparece só até o primeiro parêntese, porque é ali que o cadastro descreve a instalação. A página fica em cache por 60 s e abre o banco só para leitura; o limite de banda do Funnel segura o resto. Se o servidor ou o túnel caem, a página cai junto, o mesmo ponto único de falha da ADR 0003.
