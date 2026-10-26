# A API fica presa ao loopback e é publicada por um túnel gerenciado

O servidor escuta só em `127.0.0.1` e um túnel gerenciado (Tailscale Funnel) o publica com certificado público, expondo apenas `/v1/measurements`, `/v1/devices` e `/health`. Assim não há porta aberta no roteador, IP fixo, domínio próprio nem autoridade certificadora própria para manter. O nó confere o servidor contra a raiz pública embutida no firmware, e por isso só envia por HTTPS depois de o relógio válido chegar pelo NTP.

## Consequences

O servidor e o túnel são um ponto único de falha, coberto pelo buffer de cinco dias do nó. A raiz embutida só muda regravando o firmware do nó.
