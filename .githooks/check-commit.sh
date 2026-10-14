#!/bin/sh
# Padrão de commits do repositório: cabeçalho em Conventional Commits e nenhuma menção proibida
# (nomes de ferramentas e fornecedores, rodapé de coautoria, rodapé "gerado com") na mensagem, no
# autor ou no committer. Os termos proibidos são montados a partir de bytes para que este arquivo
# não contenha o que ele mesmo recusa.
#
# Uso: check-commit.sh msg ARQUIVO     mensagem de um commit (hook commit-msg)
#      check-commit.sh title TEXTO     título de PR, que vira a mensagem num squash merge
#      check-commit.sh range A..B      cada commit do intervalo: mensagem, autor e committer (CI)
#
# Ativação em cada clone: git config core.hooksPath .githooks

set -eu

TERM_1=$(printf '\143\154\141\165\144\145')
TERM_2=$(printf '\141\156\164\150\162\157\160\151\143')
TERM_3=$(printf '\143\157\055\141\165\164\150\157\162\145\144\055\142\171')
TERM_4=$(printf '\147\145\156\145\162\141\164\145\144\040\167\151\164\150')
FORBIDDEN="$TERM_1|$TERM_2|$TERM_3|$TERM_4"
TYPES='feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert'
HEADER_RE="^($TYPES)(\([a-z0-9._/-]+\))?!?: [^ ]"
MAX_HEADER=72

errors=0

fail() {
    echo "commit-standards: $1" >&2
    errors=$((errors + 1))
}

# Verdadeiro se o texto tem algum termo proibido. Palavras comuns que contêm TERM_2 com os prefixos
# "phil" e "mis" não contam.
has_forbidden() {
    printf '%s\n' "$1" | tr '[:upper:]' '[:lower:]' \
        | sed -e "s/phil$TERM_2//g" -e "s/mis$TERM_2//g" \
        | grep -qE "$FORBIDDEN"
}

check_header() {
    where=$1
    header=$2
    case "$header" in
        "Merge "* | "Revert \""*) return 0 ;;  # mensagens que o próprio git escreve
    esac
    if ! printf '%s\n' "$header" | grep -qE "$HEADER_RE"; then
        fail "$where: cabeçalho fora do formato tipo(escopo): descrição (tipos: $TYPES): '$header'"
    fi
    if [ "$(printf '%s' "$header" | wc -m)" -gt "$MAX_HEADER" ]; then
        fail "$where: cabeçalho com mais de $MAX_HEADER caracteres"
    fi
    case "$header" in
        *.) fail "$where: cabeçalho termina com ponto" ;;
    esac
}

check_message() {
    where=$1
    text=$2
    header=$(printf '%s\n' "$text" | sed -n '/[^[:space:]]/{p;q;}')
    check_header "$where" "$header"
    if has_forbidden "$text"; then
        fail "$where: a mensagem tem menção proibida (veja os termos em .githooks/check-commit.sh)"
    fi
}

case "${1:-}" in
    msg)
        # sem as linhas de comentário e o diff do "git commit -v", que o git remove depois do hook
        text=$(sed -e '/^# -* >8 -*$/,$d' -e '/^#/d' "$2")
        check_message "mensagem" "$text"
        ;;
    title)
        check_message "título do PR" "$2"
        ;;
    range)
        for commit in $(git rev-list "$2"); do
            short=$(git rev-parse --short "$commit")
            check_message "$short" "$(git log -1 --format=%B "$commit")"
            if has_forbidden "$(git log -1 --format='%an %ae %cn %ce' "$commit")"; then
                fail "$short: autor ou committer com menção proibida; refaça com git commit --amend --reset-author"
            fi
        done
        ;;
    *)
        echo "uso: $0 msg ARQUIVO | title TEXTO | range A..B" >&2
        exit 2
        ;;
esac

[ "$errors" -eq 0 ]
