# sejfik

Sekrety z [Sejfika](https://github.com/bartlomiejszwakop/seifik_v2) bez przepuszczania ich przez terminal, historię powłoki i rozmowę z agentem.

Powstało z konkretnego problemu: ludzie wklejają hasła i klucze API do linii poleceń i do czata z modelem. Jedno i drugie zostawia sekret w miejscu bez kontroli dostępu i bez wygasania — w transkrypcie modelu, w `~/.bash_history`, w liście procesów, w logach.

## Pomysł: referencja zamiast wartości

```
sejfik://item/1523/password
```

Referencja jest **adresem**, nie sekretem. Może leżeć w repozytorium, w pliku konfiguracyjnym, w zgłoszeniu i w rozmowie z agentem. Bez osobistego tokenu i bez jawnego wpisania wpisu do teczki agenta nie daje nikomu niczego.

Wartość pobiera dopiero `sejfik`, tuż przed uruchomieniem procesu, który jej potrzebuje.

## Instalacja

```bash
curl -fsSL https://raw.githubusercontent.com/bartlomiejszwakop/sejfik-cli/main/install.sh | sh
```

Jeden plik w Pythonie 3.9+, zero zależności. Instalator sprawdza sumę SHA-256 wydania.

Potem dwie rzeczy:

```bash
mkdir -m 700 -p ~/.sejfik
echo "url=https://sejfik.twoja-domena.pl" > ~/.sejfik/config

# token z Sejfika: Konto → tokeny MCP
install -m 600 /dev/stdin ~/.sejfik/token   # wklej, Ctrl-D

sejfik whoami
```

`sejfik` odmówi użycia pliku z kluczem, jeśli jest czytelny dla kogokolwiek poza właścicielem.

Dwa klucze, celowo osobne:

| plik | skąd | do czego |
|---|---|---|
| `~/.sejfik/token` | Konto → tokeny MCP | `run`, `inject`, `read`, `create-login`, `rotate-password` |
| `~/.sejfik/send-token` | Konto → klucze przesyłek | `send` |

Maszyna, która tylko wysyła zrzuty ekranu, potrzebuje wyłącznie drugiego.

## Użycie

### `run` — sekret w procesie, nie na ekranie

```bash
sejfik run --env HERMES_API_KEY=sejfik://item/1523/password -- hermes start
```

Sekret trafia do zmiennej środowiskowej procesu potomnego. **Nie ma go w `argv`**, więc `ps` go nie pokaże; nie ma w historii powłoki; nie ma w żadnym pliku. Można wstrzyknąć kilka naraz:

```bash
sejfik run \
  --env DB_PASS=sejfik://item/12/password \
  --env API_KEY=sejfik://item/34/password \
  -- ./deploy.sh
```

Na stałe, w systemd:

```ini
ExecStart=/usr/local/bin/sejfik run --env HERMES_API_KEY=sejfik://item/1523/password -- /usr/bin/hermes
```

Narzędzia, które czytają hasło z wejścia, a nie ze środowiska:

```bash
sejfik run --stdin sejfik://item/12/password -- mysql -u root -p
```

Kod wyjścia i strumienie przechodzą bez zmian, więc agent widzi wynik polecenia — ale nie sekret.

### `inject` — sekret w pliku konfiguracyjnym

Kiedy program uparcie chce klucz w swoim `config.yaml`:

```yaml
# config.tpl
api_key: {{ sejfik://item/1523/password }}
database:
  password: {{ sejfik://item/12/password }}
```

```bash
sejfik inject -i config.tpl -o config.yaml
```

Plik powstaje atomowo i z prawami `600` — nie ma chwili, w której leży czytelny dla wszystkich. Szablon trzymasz w repozytorium, wynik nigdy tam nie trafia.

Tu ochrona się kończy: od tego momentu sekret leży na dysku jawnym tekstem. Jeśli program umie czytać ze środowiska, `run` jest bezpieczniejszy.

### `read` — do potoku, nie na ekran

```bash
sejfik read sejfik://item/1523/password > /run/secrets/klucz
sejfik read sejfik://item/1523/password | docker secret create klucz -
```

`read` **odmówi wypisania sekretu na terminal**, bo zostałby w scrollbacku i w nagraniu sesji. Świadome obejście: `--force`.

### `create-login` — nowe hasło, którego nikt nie widzi

```bash
sejfik create-login --name "Sklep ALSO" --url https://also.com --username bartek
```

Hasło generuje **Sejfik** i tam zostaje. Gdyby generował je agent albo
model językowy, wartość przeszłaby przez rozmowę — a o to właśnie chodzi,
żeby nie przeszła.

Na standardowe wyjście idzie sama referencja, opis na strumień błędów, więc
to działa tak, jak wygląda:

```bash
REF=$(sejfik create-login --name "Sklep ALSO")
sejfik run --env HASLO="$REF" -- ./zaloz-konto.sh
```

### `rotate-password` — nowe hasło dla istniejącego wpisu

```bash
sejfik rotate-password 1608
sejfik rotate-password sejfik://item/1608/password    # obie formy działają
```

Poprzednie hasło zostaje w historii wpisu, więc rotacja, która nie zdążyła
dojechać do serwisu po drugiej stronie, nie zostawia nikogo bez dostępu.

Uwaga: to zmienia hasło **w Sejfiku**, a nie w serwisie. Ustawienie go tam
to osobny krok i nikt go za Ciebie nie zrobi.

### `send` — zrzut ekranu jednym poleceniem

```bash
sejfik send --screen            # wybierz obszar, wyślij, dostań link
sejfik send --screen --full     # cały ekran bez wybierania
sejfik send --clipboard         # obraz ze schowka
sejfik send zrzut.png raport.pdf --note "błąd na produkcji"
```

Link idzie na standardowe wyjście, opis na strumień błędów, więc to działa
tak, jak wygląda:

```bash
LINK=$(sejfik send --screen)
```

Jeśli w systemie jest `wl-copy`, `xclip` albo `pbcopy`, link ląduje też
w schowku. Zrzut robi pierwsze narzędzie, które znajdzie: `grim`+`slurp`,
`gnome-screenshot`, `spectacle`, `maim`, `scrot`, ImageMagick, a na macOS
wbudowany `screencapture`.

Opcje przesyłki: `--hours`, `--downloads`, `--length` (6, 16, 22 albo 48
znaków linku), `--note`.

Wygodnie podwiązać to pod skrót klawiszowy systemu — wtedy wysłanie zrzutu
to jedno naciśnięcie i wklejenie linku.

**To polecenie używa innego klucza niż pozostałe.** Klucz przesyłek umie
wyłącznie utworzyć przesyłkę: nie otwiera sejfu i nie czyta haseł. Dzięki
temu maszyna, która tylko wysyła zrzuty, nie nosi klucza do sekretów.

```bash
install -m 600 /dev/stdin ~/.sejfik/send-token   # klucz z: Konto → klucze przesyłek
```

### `whoami`

```bash
$ sejfik whoami
Bartek (id 7)
wpisów w teczce agenta: 3
```

Sprawdza token, nie dotykając żadnego sekretu — więc nie zostawia wpisu w audycie ujawnień.

## Czego to nie robi

Uczciwie, bo obietnice bez pokrycia są tu gorsze niż ich brak.

**Agent uruchamiający polecenie może zobaczyć sekret.** Jeśli agent steruje procesem potomnym, może kazać mu zrobić `echo $HASLO`. Tego nie da się obejść po stronie CLI. Celem jest to, żeby sekret **nie pojawiał się w kontekście modelu, w argumentach i w historii** — a to eliminuje drogi, którymi sekrety wyciekają naprawdę. Nie eliminuje złośliwego agenta.

**`sejfik` nie cenzuruje wyjścia.** Jeśli uruchomione polecenie samo wypisze hasło (`env`, gadatliwy debug), zobaczysz je.

**Sekret w pliku to sekret na dysku.** `inject` zawęża prawa i pisze atomowo, ale nie zmienia tego faktu.

## Audyt

Każde rozwiązanie referencji zostaje po stronie Sejfika: kto, co, kiedy i z jakiego adresu. `--reason` dopisuje powód:

```bash
sejfik run --reason "wdrożenie 2026-09-29" --env X=sejfik://item/12/password -- ./deploy.sh
```

## Rozwój

```bash
python3 tests/test_sejfik.py
```

Testy podstawiają atrapę serwera HTTP, więc nie potrzebują działającego Sejfika.

## Licencja

MIT — patrz [LICENSE](LICENSE).
