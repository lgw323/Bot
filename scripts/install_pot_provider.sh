#!/bin/bash

set -eu

PROVIDER_VERSION="1.3.1"
PROVIDER_REPOSITORY="https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git"
INSTALL_ROOT="/home/os/.local/share"
PROVIDER_DIR="$INSTALL_ROOT/bgutil-ytdlp-pot-provider"
DENO_BIN="/home/os/.local/bin/deno"
CACHE_DIR="/home/os/.cache/bgutil-ytdlp-pot-provider"

candidate_root=""
candidate_provider=""
previous_provider="$PROVIDER_DIR.previous"


restore_previous_provider() {
    if [ ! -e "$PROVIDER_DIR" ] && [ -e "$previous_provider" ]; then
        mv "$previous_provider" "$PROVIDER_DIR"
    fi
}


cleanup() {
    if [ -n "$candidate_root" ] && [ -d "$candidate_root" ]; then
        rm -rf -- "$candidate_root"
    fi
}


provider_is_current() {
    [ -f "$PROVIDER_DIR/.installed-version" ] &&
        [ "$(head -n 1 "$PROVIDER_DIR/.installed-version")" = "$PROVIDER_VERSION" ] &&
        [ -f "$PROVIDER_DIR/server/src/generate_once.ts" ] &&
        [ -d "$PROVIDER_DIR/server/node_modules" ]
}


verify_provider() {
    local provider_root="$1"
    local installed_version

    mkdir -p "$CACHE_DIR"
    installed_version="$(
        cd "$provider_root/server/node_modules"
        "$DENO_BIN" run \
            --allow-env \
            --allow-net \
            --allow-ffi=. \
            --allow-write="$CACHE_DIR" \
            --allow-read="$CACHE_DIR,." \
            ../src/generate_once.ts \
            --version
    )"
    test "$installed_version" = "$PROVIDER_VERSION"
}


main() {
    mkdir -p "$CACHE_DIR"
    chmod 700 "$CACHE_DIR"
    if provider_is_current; then
        return 0
    fi
    if [ ! -x "$DENO_BIN" ]; then
        printf "Deno 실행 파일을 찾을 수 없습니다: %s\n" "$DENO_BIN" >&2
        return 1
    fi

    mkdir -p "$INSTALL_ROOT"
    candidate_root="$(mktemp -d "$INSTALL_ROOT/.bgutil-pot.XXXXXX")"
    candidate_provider="$candidate_root/provider"

    git clone --quiet --depth 1 --branch "$PROVIDER_VERSION" \
        "$PROVIDER_REPOSITORY" "$candidate_provider"
    (
        cd "$candidate_provider/server"
        "$DENO_BIN" install --allow-scripts=npm:canvas --frozen
    )
    verify_provider "$candidate_provider"
    printf "%s\n" "$PROVIDER_VERSION" \
        > "$candidate_provider/.installed-version"

    rm -rf -- "$previous_provider"
    if [ -e "$PROVIDER_DIR" ]; then
        mv "$PROVIDER_DIR" "$previous_provider"
    fi
    if ! mv "$candidate_provider" "$PROVIDER_DIR"; then
        restore_previous_provider
        return 1
    fi
    rm -rf -- "$previous_provider"
}


trap cleanup EXIT
main "$@"
