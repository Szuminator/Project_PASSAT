# PASSAT — GroqCloud, Gemini i tryb offline

Passat to desktopowy asystent samochodowy w Pythonie i PySide6. Aplikacja ma
animowany rdzeń, prosty czat, ograniczoną historię rozmowy i wymienne źródło
odpowiedzi. Obecnie dostępne są GroqCloud, opcjonalne Gemini i podstawowy tryb
offline. Mikrofon i lokalna synteza mowy działają po instalacji zależności,
pobraniu głosu Piper oraz polskiego modelu Vosk dla nasłuchu hasła. Trwała
pamięć, wyszukiwanie internetowe, GPS i integracja z samochodem nie są podłączone.

## Struktura

```text
Project_PASSAT/
├── main.py                       # okno PySide6, czat i praca w tle
├── core_widget.py                # animowany rdzeń
├── passat/
│   ├── assistant.py              # historia, osobowość i awaryjny fallback
│   ├── models.py                 # wspólne typy wiadomości i odpowiedzi
│   ├── prompts.py                # instrukcja osobowości
│   ├── settings.py               # odczyt ustawień i .env
│   ├── audio/
│   │   ├── input.py              # mikrofon i faster-whisper
│   │   ├── output.py             # synteza Piper i odtwarzanie
│   │   ├── tts_text.py           # przygotowanie tekstu tylko dla Piper
│   │   └── wake_word.py          # wymienny detektor hasła i worker Qt
│   └── providers/
│       ├── base.py                # wspólny kontrakt i błędy dostawców
│       ├── factory.py             # wybór dostawcy AI albo offline
│       ├── gemini.py              # opcjonalna integracja Google Gen AI SDK
│       ├── groq.py                # integracja z GroqCloud
│       └── offline.py             # proste odpowiedzi bez modelu
├── tests/                         # testy bez klucza i żądań do API
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── README.md
```

GUI rozmawia wyłącznie ze wspólnym `PassatAssistant`. Każdy dostawca przyjmuje
wiadomość, wspólną historię `ChatMessage` oraz instrukcję systemową. Dzięki temu
kolejni dostawcy mogą realizować ten sam kontrakt bez zmian w oknie czatu.

## Wymagania

- Windows 10/11
- Python 3.13
- Klucz wybranego dostawcy jest opcjonalny — bez niego działa tryb offline.

## Instalacja

Otwórz PowerShell w katalogu projektu:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Jeśli PowerShell blokuje aktywację środowiska, pomiń ją i użyj jego interpretera:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Do uruchomienia testów doinstaluj zależności deweloperskie:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## GroqCloud (domyślnie)

1. Utwórz klucz API w [konsoli GroqCloud](https://console.groq.com/keys).
2. Skopiuj przykład konfiguracji i otwórz lokalny plik `.env`:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Uzupełnij klucz w `.env` obok `main.py`:

   ```dotenv
   PASSAT_PROVIDER=groq
   GROQ_API_KEY=tu_wklej_swoj_klucz
   PASSAT_GROQ_MODEL=qwen/qwen3.8-27b
   ```

   `.env` jest wykluczony z Git. Nie wpisuj prawdziwego klucza do kodu ani
   wiadomości. Bez klucza aplikacja uruchomi się w trybie offline.

Model `qwen/qwen3.8-27b` jest obecnie wymieniony w [katalogu modeli Groq](https://console.groq.com/docs/models)
i w tabeli limitów bezpłatnego [planu GroqCloud](https://console.groq.com/docs/rate-limits).
Dokumentacja modelu wskazuje obsługę wielojęzyczną, przydatną do rozmowy po
polsku. Groq oznacza go jako **Preview**, więc może zostać zmieniony lub
wycofany. Nazwa modelu pozostaje konfigurowalna przez `PASSAT_GROQ_MODEL`.
Limity Free obowiązują i mogą się zmieniać; sprawdź je w dokumentacji i swoim koncie.
Passat nie przełącza się na płatne plany ani endpointy.

Oficjalny SDK ma automatyczne ponowienia wyłączone w Passacie. Przy HTTP 429
aplikacja wykona najwyżej jedną dodatkową próbę, jeśli serwer poda
`Retry-After` nie dłuższy niż 15 sekund; w przeciwnym razie pokaże czas
oczekiwania. Timeout odpowiedzi wynosi 60 sekund i nie blokuje GUI.

## Gemini (opcjonalnie)

1. Utwórz klucz w [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Zmień dostawcę i wpisz klucz w lokalnym `.env`:

   ```dotenv
   PASSAT_PROVIDER=gemini
   GEMINI_API_KEY=tu_wklej_swoj_klucz
   PASSAT_GEMINI_MODEL=gemini-3.8-flash
   ```

   `.env` jest wykluczony z Git. Nie wklejaj klucza do kodu, README ani zgłoszeń.

Jeśli chcesz uruchamiać testy Gemini, zainstaluj również `requirements-dev.txt`.
Domyślnym modelem Gemini jest `gemini-3.8-flash`, widoczny w aktualnym
[katalogu modeli Google](https://ai.google.dev/gemini-api/docs/models) i z
bezpłatnym poziomem dla wejścia i wyjścia. Dostępność konkretnego modelu oraz
limity zależą od konta i projektu: sprawdź, czy model jest dostępny w AI Studio,
przetestuj go tam, a aktywne limity zobacz w panelu **Rate limits**. Aktualne
warunki i limity bezpłatne opisuje [cennik Gemini API](https://ai.google.dev/gemini-api/docs/pricing),
a [dokumentacja limitów](https://ai.google.dev/gemini-api/docs/rate-limits)
wyjaśnia, jak je sprawdzić. Nie zakładaj, że limit jest nieograniczony. Możesz
zmienić model w `PASSAT_GEMINI_MODEL`, bez edycji kodu.

Bezpłatny poziom ma ograniczenia. Według informacji Google treści wysyłane w
ramach bezpłatnego poziomu mogą być używane do ulepszania produktów Google;
nie wysyłaj tam danych wrażliwych. Jeśli klucz należy do projektu z włączonym
płatnym rozliczaniem, mogą mieć zastosowanie opłaty. Passat nie konfiguruje
płatności, nie zmienia modelu automatycznie i nie używa narzędzi takich jak
Google Search grounding. Każde żądanie ma limit oczekiwania 120 sekund i
ustawiony niski poziom `thinking`, co pomaga ograniczyć opóźnienie w zwykłej
rozmowie. Przy HTTP 503 SDK ponawia żądanie najwyżej raz, z krótkim odstępem;
pozostałe błędy nie są automatycznie ponawiane.

## Uruchomienie i testy

```powershell
python main.py
```

Testy lokalne nie potrzebują klucza i nie łączą się z API:

```powershell
python -m pytest -q
```

Pole wysyła wiadomość przyciskiem **WYŚLIJ** lub klawiszem **Enter**. Podczas
oczekiwania interfejs pokazuje **MYŚLĘ**; odpowiedź dostawcy AI kończy się
statusem **GOTOWY**, a odpowiedź offline — **OFFLINE**. Początkowy opis wybranego
dostawcy mówi tylko, że jest skonfigurowany. Aplikacja pokazuje powodzenie
połączenia dopiero po otrzymaniu pierwszej odpowiedzi.

Jeśli nie ma klucza albo dostawca AI zwróci błąd, Passat przełącza pojedynczą
wiadomość na prosty tryb offline i pokazuje informację o użytym dostawcy. Tryb
offline rozpoznaje powitania, pytania o tożsamość Passata i tryb działania;
potrafi też podać lokalną godzinę i dzisiejszą datę po polsku. Wartości pobiera
z zegara i strefy czasowej komputera. Pozostałych odpowiedzi nie generuje model
językowy.

## Rozmowa głosowa (lokalna)

Zależności `faster-whisper`, `sounddevice`, Vosk i Piper są instalowane razem z
`requirements.txt`. Rozpoznawanie i synteza działają lokalnie. Przy pierwszym
użyciu faster-whisper pobiera wybrany model do pamięci podręcznej Hugging Face;
audio z mikrofonu nie jest wysyłane do tej usługi ani zapisywane na stałe.

Pobierz polski głos Piper raz, gdy komputer ma dostęp do internetu:

```powershell
.\.venv\Scripts\python.exe -m piper.download_voices pl_PL-gosia-medium --download-dir models/voices
```

Piper potrzebuje osobnych plików `pl_PL-gosia-medium.onnx` i
`pl_PL-gosia-medium.onnx.json`. Model ma około 63 MB i jest ignorowany przez Git.
Karta głosu opisuje zbiór danych jako CC0; przed dalszą dystrybucją głosu
sprawdź bieżącą kartę modelu. Sam silnik Piper ma licencję GPL-3.0.

W `.env` możesz zmienić konfigurację:

```dotenv
PASSAT_STT_MODEL=small
PASSAT_PIPER_MODEL=models/voices/pl_PL-gosia-medium.onnx
```

Model Whisper ładuje się po pierwszej próbie transkrypcji i działa na CPU w
trybie `int8`. Pierwsze użycie wymaga internetu, aby pobrać model; kolejne
transkrypcje są lokalne. Nagrywanie kończy się automatycznie po wykryciu ciszy
po mowie; przycisk **ZATRZYMAJ NAGRYWANIE** nadal pozwala zatrzymać je wcześniej.
Odpowiedzi są odczytywane po zakończeniu odpowiedzi AI;
**PRZERWIJ MÓWIENIE** zatrzymuje aktualne odtwarzanie. Jeśli Piper lub głos nie
są dostępne, tekstowa odpowiedź nadal pojawia się w czacie.

### Nasłuch hasła aktywacyjnego

Nasłuch hasła **Passat** jest domyślnie włączony i działa lokalnie przez Vosk.
Audio nie jest wysyłane do chmury ani zapisywane na dysku. Do detekcji i
nagrywania używany jest jeden strumień mikrofonu. Po rozpoznaniu hasła Passat
przechodzi do stanu **SŁUCHAM**. Lokalne wykrywanie energii audio kończy nagranie
po domyślnych 0,8 sekundy ciszy po rozpoczęciu mowy. Początkowa cisza nie kończy
sesji; krótki bufor zachowuje fragment sprzed wykrycia początku wypowiedzi.
Przycisk **ZATRZYMAJ NAGRYWANIE** pozostaje awaryjną opcją ręcznego zatrzymania.
Nasłuch hasła jest wstrzymany podczas myślenia i odtwarzania odpowiedzi, aby
Passat nie aktywował się od własnego głosu.

Biblioteka Vosk jest instalowana z `requirements.txt`, ale model językowy pobierz
ręcznie z [oficjalnego katalogu modeli Vosk](https://alphacephei.com/vosk/models).
Wybierz `vosk-model-small-pl-0.22` (około 50 MB, licencja Apache 2.0), rozpakuj
folder do `models/wake-word/` i uruchom ponownie Passata. Ścieżka do folderu
modelu musi odpowiadać ustawieniu `PASSAT_WAKE_WORD_MODEL_PATH`.
Testy nie pobierają modelu. Model nie jest pobierany automatycznie przy starcie.

Ustawienia w `.env`:

```dotenv
PASSAT_WAKE_WORD_ENABLED=true
PASSAT_WAKE_WORD_MODEL_PATH=models/wake-word/vosk-model-small-pl-0.22
PASSAT_WAKE_WORD_MIN_CONFIDENCE=0.0
PASSAT_VAD_SILENCE_SECONDS=0.8
PASSAT_VAD_RMS_THRESHOLD=0.004
PASSAT_VAD_PRE_ROLL_MS=200
```

`PASSAT_VAD_SILENCE_SECONDS` ustawia ciszę wymaganą do zakończenia nagrania.
`PASSAT_VAD_RMS_THRESHOLD` reguluje czułość, a `PASSAT_VAD_PRE_ROLL_MS` długość
bufora początku. VAD używa energii krótkich ramek audio i adaptuje próg do tła
podczas oczekiwania na hasło. Głośne otoczenie lub bardzo cichy mikrofon mogą
wymagać dostrojenia progu. Wartości spoza bezpiecznego zakresu są ograniczane,
a błędny wpis wraca do wartości domyślnej.
`PASSAT_WAKE_WORD_MIN_CONFIDENCE` pozwala ustawić minimalny confidence słowa
z końcowego wyniku Vosk (zakres 0–1). Domyślne `0.0` wyłącza ten filtr, ponieważ
wynik nie jest skalibrowanym prawdopodobieństwem; ustawienie wyższego progu
wymaga sprawdzenia na poprawnych wywołaniach z różnych odległości. Jeśli próg
jest aktywny, ale wynik nie zawiera confidence, detektor nie zaakceptuje tego
wywołania. Wyniki częściowe nigdy same nie aktywują Passata.

Detektor potwierdza hasło dopiero po końcowym wyniku Vosk i dopasowuje pełny
token `passat`. Gramatyka uwzględnia też znane pomyłki (`pa`, `fasola`), żeby
dekoder miał możliwość zwrócenia ich zamiast wymuszania nazwy Passata. To
ogranicza fałszywe aktywacje, ale nie gwarantuje ich całkowitego wyeliminowania;
sprawdź zachowanie na docelowym mikrofonie i w typowej odległości.

Przycisk **WYŁĄCZ NASŁUCH HASŁA** zatrzymuje oczekiwanie; można je później
włączyć ponownie. Jeżeli brakuje modelu, biblioteki lub mikrofonu, nasłuch się
wyłączy i pokaże informację. Nadal działa czat tekstowy oraz ręczny przycisk
mikrofonu. Ponieważ Vosk jest rozpoznawaniem mowy z ograniczoną gramatyką, a nie
dedykowanym modelem wake-word, warto sprawdzić liczbę fałszywych aktywacji na
własnym mikrofonie i w typowym otoczeniu.

Tekst w czacie zachowuje Markdown. Do Piper przekazywana jest oddzielnie
przygotowana wersja: nie odczytuje znaczników formatowania, adresów URL ani
surowego kodu/JSON.

Nagranie i rozpoznawanie mogą zająć chwilę, zwłaszcza przy pierwszym pobraniu
modelu. Interfejs pozostaje responsywny. Stan **MÓWIĘ** i deformacja pierścieni
otrzymują wygładzony poziom RMS z rzeczywiście odtwarzanego dźwięku.

Przy przenoszeniu na Raspberry Pi 5 trzeba będzie sprawdzić koła dla konkretnego
systemu ARM64 i wydajność wybranego modelu. Na Linuksie `sounddevice` może wymagać
systemowego PortAudio, np. pakietu `libportaudio2`; dobór urządzenia audio może
też zależeć od ALSA/PipeWire. Implementacja jest oddzielona od interfejsu tak,
aby te ustawienia można było dostroić bez przebudowy czatu.

## Rozwiązywanie problemów

- **Passat działa offline:** sprawdź, czy `.env` znajduje się obok `main.py`,
  czy `PASSAT_PROVIDER=groq` i czy `GROQ_API_KEY` jest ustawiony. Gemini wymaga
  `PASSAT_PROVIDER=gemini` oraz `GEMINI_API_KEY`.
- **Błąd autoryzacji:** utwórz lub sprawdź klucz u wybranego dostawcy. Aplikacja
  nie pokazuje surowych błędów API ani klucza.
- **Limit Groq:** sprawdź limity Free w konsoli GroqCloud; aplikacja respektuje
  `Retry-After` i nie wykonuje nieograniczonych ponowień.
- **Model niedostępny:** wybierz model dostępny dla projektu i ustaw go w
  `PASSAT_GROQ_MODEL` albo `PASSAT_GEMINI_MODEL`.
- **Mikrofon nie działa:** sprawdź uprawnienia mikrofonu w ustawieniach
  prywatności Windows, wybór domyślnego urządzenia wejściowego oraz czy inna
  aplikacja go nie blokuje. Listę urządzeń sprawdzisz poleceniem:

  ```powershell
  .\.venv\Scripts\python.exe -c "import sounddevice as sd; print(sd.query_devices())"
  ```

- **Brak głosu:** pobierz model Piper poleceniem z sekcji „Rozmowa głosowa” i
  sprawdź `PASSAT_PIPER_MODEL`.
- **Zależności:** uruchom `python -m pip install -r requirements-dev.txt`
  w aktywnym środowisku `.venv`. Bez aktywacji:

  ```powershell
  .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
  ```
