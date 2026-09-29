#!/bin/sh
# Instalator sejfika dla Linuksa i macOS.
#
#   curl -fsSL https://raw.githubusercontent.com/OWNER/sejfik-cli/main/install.sh | sh
#
# Pobiera wydanie z GitHuba, sprawdza sumę SHA-256 i kładzie jeden plik
# w PATH. Bez sudo instaluje do ~/.local/bin.
#
# Zmienne: SEJFIK_CLI_REPO, SEJFIK_CLI_VERSION (domyślnie latest), PREFIX.

set -eu

REPO="${SEJFIK_CLI_REPO:-bartlomiejszwakop/sejfik-cli}"
VERSION="${SEJFIK_CLI_VERSION:-latest}"

czerwony() { printf '\033[31m%s\033[0m\n' "$1" >&2; }
info()     { printf '%s\n' "$1" >&2; }

koniec() {
  czerwony "instalacja przerwana: $1"
  exit 1
}

# --- czego potrzebujemy ----------------------------------------------------

command -v curl >/dev/null 2>&1 || koniec "brak curl-a"

PYTHON=""
for kandydat in python3 python; do
  if command -v "$kandydat" >/dev/null 2>&1; then
    if "$kandydat" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      PYTHON="$kandydat"
      break
    fi
  fi
done
[ -n "$PYTHON" ] || koniec "potrzebny Python 3.9 lub nowszy"

if command -v sha256sum >/dev/null 2>&1; then
  SUMA="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
  SUMA="shasum -a 256"
else
  koniec "brak sha256sum i shasum — nie mam czym sprawdzić pobranego pliku"
fi

# --- gdzie instalujemy -----------------------------------------------------

if [ -n "${PREFIX:-}" ]; then
  CEL="$PREFIX/bin"
elif [ "$(id -u)" = "0" ]; then
  CEL="/usr/local/bin"
else
  CEL="$HOME/.local/bin"
fi
mkdir -p "$CEL" || koniec "nie mogę utworzyć $CEL"

# --- pobranie --------------------------------------------------------------

if [ "$VERSION" = "latest" ]; then
  BAZA="https://github.com/$REPO/releases/latest/download"
else
  BAZA="https://github.com/$REPO/releases/download/$VERSION"
fi

ROBOCZY="$(mktemp -d)"
# shellcheck disable=SC2064
trap "rm -rf '$ROBOCZY'" EXIT INT TERM

info "Pobieram sejfika ($VERSION) z $REPO..."
curl -fsSL "$BAZA/sejfik" -o "$ROBOCZY/sejfik" || koniec "nie udało się pobrać pliku sejfik"
curl -fsSL "$BAZA/SHA256SUMS" -o "$ROBOCZY/SHA256SUMS" || koniec "nie udało się pobrać sum kontrolnych"

# Suma z wydania musi zgodzić się z tym, co faktycznie przyszło. To jedyne,
# co odróżnia instalację od uruchomienia losowego kodu z internetu.
OCZEKIWANA="$(awk '$2 ~ /(^|\/)sejfik$/ {print $1; exit}' "$ROBOCZY/SHA256SUMS")"
[ -n "$OCZEKIWANA" ] || koniec "w SHA256SUMS nie ma wpisu dla pliku sejfik"
FAKTYCZNA="$($SUMA "$ROBOCZY/sejfik" | awk '{print $1}')"

if [ "$OCZEKIWANA" != "$FAKTYCZNA" ]; then
  czerwony "suma kontrolna się nie zgadza!"
  czerwony "  oczekiwano: $OCZEKIWANA"
  czerwony "  otrzymano:  $FAKTYCZNA"
  koniec "pobrany plik nie jest tym, co opublikowano"
fi

# --- instalacja ------------------------------------------------------------

chmod 755 "$ROBOCZY/sejfik"
mv "$ROBOCZY/sejfik" "$CEL/sejfik" || koniec "nie mogę zapisać do $CEL"

# Zgodność wstecz: stare wywołania sejfik-run --ref X --env Y -- polecenie.
ln -sf "$CEL/sejfik" "$CEL/sejfik-run" 2>/dev/null || true

info ""
info "Gotowe: $CEL/sejfik ($("$CEL/sejfik" --version))"

case ":$PATH:" in
  *":$CEL:"*) ;;
  *) info ""
     info "UWAGA: $CEL nie jest w PATH. Dopisz do ~/.profile:"
     info "    export PATH=\"$CEL:\$PATH\"" ;;
esac

cat >&2 <<'NASTEPNE'

Zostały dwie rzeczy:

  1. Adres Sejfika:
       mkdir -m 700 -p ~/.sejfik
       echo "url=https://sejfik.twoja-domena.pl" > ~/.sejfik/config

  2. Token osobisty — wygeneruj w Sejfiku (Konto → tokeny MCP) i zapisz:
       install -m 600 /dev/stdin ~/.sejfik/token
       (wklej token, potem Ctrl-D)

Sprawdzenie:
       sejfik whoami
NASTEPNE
