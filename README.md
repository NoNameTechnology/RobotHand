# 🤖 RobotHand – Dynamixel XL330-M288 Hand-Controller

[![Python Version](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![GUI Framework](https://img.shields.io/badge/GUI-Tkinter-lightgrey.svg)](https://docs.python.org/3/library/tkinter.html)
[![Dynamixel SDK](https://img.shields.io/badge/SDK-Dynamixel_Protocol_2.0-red.svg)](https://emanual.robotis.com/docs/en/software/dynamixel/dynamixel_sdk/overview/)
[![Platform Support](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-brightgreen.svg)](https://github.com/Robotis-GIT/DynamixelSDK)

Willkommen bei der **RobotHand**-Software! Mit diesem Tool steuerst du eine robotergestützte Hand über eine moderne, intuitive Benutzeroberfläche. 

Ursprünglich wurde das Programm für das Projekt „Soft!-robotic Hands“ (SoSe 2026) entwickelt. Es ermöglicht dir eine elastische, kraftgesteuerte Bedienung von Seilzügen und Fingern, angetrieben von **Dynamixel XL330-M288** Servomotoren. Egal, ob du einfach nur ein paar Greifbewegungen testen oder komplexe, automatisierte Sequenzen abspielen möchtest – hier bist du richtig.

---

## 🚀 Hauptmerkmale

### 1. Betriebsmodi für jede Situation
* **Positionsmodus (Joint Mode):** Die klassische, gradgenaue Winkelregelung der Servos.
* **Geschwindigkeitsmodus (Wheel Mode):** Endlose Drehung mit kontinuierlicher Geschwindigkeitsregelung (z. B. super praktisch für Spindeln oder Seilwickler).
* **Strombasierten Positionsmodus (Soft-Robotic Mode):** Unser wichtigster Modus! Er kombiniert Positionsregelung mit einer aktiven Strombegrenzung. **Der Vorteil:** Die Hand greift sanft zu, gibt bei Widerstand nach und schützt so die empfindlichen mechanischen Seilzüge zuverlässig vor dem Reißen.

### 2. Live-Telemetrie & Hardware-Schutz
Wir lassen die Motoren nicht blind laufen, sondern passen gut auf deine Hardware auf:
* **Echtzeit-Stromüberwachung:** Behalte den Motorstrom (mA) aller 5 Kanäle im integrierten Graphen im unteren Bereich der App jederzeit im Blick.
* **Temperatur-Wächter:** Überschreitet ein Motor 55 °C, warnt dich das System sofort optisch im UI (die Anzeige färbt sich rot), damit nichts überhitzt.
* **Hardware-Diagnose:** Die Software liest direkt das Fehlerregister der Motoren (z. B. Overload) aus und zeigt dir den Status übersichtlich an ($\checkmark$ oder Warnung).
* **EMERGENCY STOP (Not-Aus):** Ein Klick schaltet sofort das Drehmoment aller Motoren ab (Torque OFF).

### 3. Smarte Kontakt- & Greiferkennung
* **Flankenerkennung:** Das System erkennt plötzliche Strom-Peaks, wenn ein Finger auf physischen Widerstand stößt.
* **Gleitender Durchschnitt:** Um Fehler durch kleines Signalrauschen zu vermeiden, glätten wir die Messwerte über ein kurzes Zeitfenster.
* **Sichtbares Feedback:** Ein Ampelsystem pro Motor zeigt dir, was gerade passiert (● `No Contact` / ● `Approaching` / ● `Contact!`).

---

## 📸 Benutzeroberfläche (GUI)

Wir haben die GUI bewusst aufgeräumt und minimalistisch gestaltet, damit du dich voll und ganz auf die Steuerung konzentrieren kannst:
* **Dark & Light Mode:** Ein augenfreundliches Dark Theme sowie ein sauberer Light Mode, zwischen denen du nahtlos wechseln kannst.
* **Zweisprachiges Design:** Die Benutzeroberfläche ist auf Englisch (Industriestandard), bietet aber detaillierte, deutsche Hover-Erklärungen (Tooltips), um dir den Einstieg im Labor zu erleichtern.
* **Intuitive Bedienung:** Du kannst alle Regler (Positionen, Strombegrenzungen, Geschwindigkeiten) ganz präzise mit dem Mausrad verstellen.
* **Undo-Funktion (Rückgängig):** Aus Versehen einen Slider verstellt? Mit `Strg + Z` oder per Knopfdruck machst du das sofort rückgängig.

---

## 🧠 Wie der Code funktioniert (Für Anfänger & Entwickler)

Wenn du den Code verstehen oder erweitern möchtest, hilft dir dieser kurze Überblick über die Architektur:

### 1. Das MVC-Prinzip (Model-View-Controller)
Der Code ist nicht einfach alles in einer riesigen Datei, sondern sauber in drei logische Bereiche getrennt:
* **Model (`models.py`):** Hier leben die Daten. Zustände wie "Welcher Motor hat gerade welche Temperatur?" oder "Ist die Verbindung aktiv?" werden hier gespeichert.
* **View (`ui.py`):** Das ist das Aussehen der App (Buttons, Slider, Fenster). Die View ist "dumm" – sie zeigt nur Daten an und meldet Klicks an den Controller weiter.
* **Controller (`main.py`):** Das Gehirn der App. Der Controller verbindet das Model mit der View und reagiert auf deine Eingaben.

### 2. Das Geheimnis einer flüssigen App: Multithreading
Das Auslesen von Hardware über ein USB-Kabel (serielle Kommunikation) dauert oft ein paar Millisekunden. Würden wir das im selben Programmteil machen, der auch die Benutzeroberfläche (Tkinter) zeichnet, würde die App ständig "einfrieren" oder ruckeln. 
**Die Lösung:** Wir nutzen zwei getrennte "Fäden" (Threads), die gleichzeitig laufen:
* **Der UI-Thread (`main.py`):** Kümmert sich *nur* um das flüssige Zeichnen der Oberfläche und nimmt deine Klicks entgegen.
* **Der Hardware-Thread (`hardware.py`):** Läuft unsichtbar im Hintergrund. Er schickt pausenlos (in einer `while`-Schleife) Befehle an die Motoren (z.B. "Fahre zu Position X") und fragt gleichzeitig Telemetriedaten ab ("Wie warm bist du?"). 
Beide Threads kommunizieren sicher über sogenannte *Queues* (Warteschlangen) und Thread-sichere Variablen miteinander.

### 3. Posen und Sequenzen (`sequences.py`)
Wenn du eine Pose speicherst, merkt sich das System einfach die aktuellen Slider-Werte aller 5 Motoren in einer JSON-Datei (`poses.json`). Der Sequenzer nimmt dann eine Liste solcher Posen, schickt sie nacheinander an die Motoren und wartet dazwischen eine von dir eingestellte Zeit.

---

## 🎓 Ausrichtung auf das Robotik-Projekt (SoSe 2026)

* **Opponierbarkeit:** Das System steuert bis zu 5 Motoren (IDs `0` bis `4`). Perfekt für vier Finger und einen Daumen.
* **Passive Nachgiebigkeit:** Durch den speziellen Strom-Modus der XL330-Servos können die Finger elastisch nachgeben. So kannst du auch ein rohes Ei greifen, ohne es zu zerdrücken!
* **Pflicht-Grasps integriert:** Die geforderten Demogriffe (**Edge-Grasp**, **Top-Grasp** und **Wall-Grasp**) sind als Vorlagen direkt einsatzbereit.
* **Automatisierte Abläufe:** Der Sequenz-Player ermöglicht die exakte Wiederholung von Greifvorgängen (ideal für die Projektdemonstration!).

---

## 🛠 Hardware-Verkabelung

So verbindest du die Komponenten miteinander:

```text
+------------+     USB     +----------------+   Half-Duplex   +----------+
|  Steuer-   | <=========> |  Robotis U2D2  | <-------------> | Motor #0 | (Daumen-MCP)
|    PC      |             |   Konverter    |   TTL-Bus       +----------+
+------------+             +----------------+                      |
                                   ^                               V
                                   | Externe Spannung         +----------+
                                   +--- (5.6V)         | Motor #1 | (Daumen-ALL)
                                                              +----------+
                                                                   |
                                                                   V
                                                                  ...
                                                              +----------+
                                                              | Motor #4 | (Motor 4)
                                                              +----------+
```

---

## 📦 Installation & Setup

So richtest du das Projekt auf deinem Rechner ein:

1. **Python 3** herunterladen und installieren (falls noch nicht geschehen).
2. Installiere die benötigten Bibliotheken (das **Dynamixel SDK** und **Pillow** für die Graphen) über das Terminal:
   ```bash
   pip install dynamixel-sdk pillow
   ```
3. Öffne die Datei `config.json` und passe den COM-Port (unter Windows meist `COM3` oder ähnlich, bei Mac/Linux `/dev/ttyUSB...`) an dein Setup an:
   ```json
   {
     "hardware": {
       "port": "COM10",
       "baudrate": 115200
     },
     "motors": {
       "ids": [0, 1, 2, 3, 4]
     }
   }
   ```

---

## 📖 Kurzanleitung zur Bedienung

### 1. Verbindung herstellen
* Starte die Software im Terminal mit: `python main.py`
* Klicke in der App oben links auf **"Connect"**. Der Status sollte auf ● **ONLINE** wechseln.

### 2. Finger richtig kalibrieren
Damit die Software weiß, wo "offen" und wo "geschlossen" ist, musst du die Motoren einmal anlernen:
* Bewege einen Finger (entweder per Slider im Wheel-Modus oder bei ausgeschaltetem Torque per Hand) in die **offene Position**. Klicke bei diesem Motor auf **"Set Zero"**.
* Bewege denselben Finger in die **voll geschlossene Greifposition**. Klicke auf **"Set Limit"**.
* Klicke oben auf das Speichern-Symbol (Diskette). Die Werte werden in der `calibration.json` gespeichert.
* *Cooler Nebeneffekt:* Danach skaliert der Slider für diesen Motor exakt von 0 % (ganz offen) bis 100 % (ganz geschlossen).

### 3. Posen speichern & Sequenzen abspielen
* **Pose anlegen:** Stelle alle Finger so ein, wie du sie brauchst. Gib oben rechts einen Namen ein (z. B. "Stift-Greifen") und speichere sie.
* **Ablauf erstellen:** Wähle eine Pose, stelle eine Wartezeit ein (z. B. 1000 ms = 1 Sekunde) und füge sie mit **"+ Sequence"** dem Ablauf hinzu.
* **Ablauf starten:** Ein Klick auf den großen, blauen **"Start"**-Button reicht, und die Hand führt deine programmierte Sequenz automatisch aus!

---

## 📂 Projektstruktur & Dateien im Detail

Wer noch tiefer einsteigen will, findet hier die Erklärung zu jeder Datei:

### Python-Code (Die Logik)
* **`main.py`**: Der zentrale App-Controller. Startet das Fenster und den Hintergrund-Thread.
* **`ui.py`**: Baut die gesamte grafische Oberfläche (Tkinter) auf. Hier findest du Buttons, Slider und Farben.
* **`hardware.py`**: Der "Arbeiter" im Hintergrund. Spricht über das USB-Kabel direkt mit den Servomotoren.
* **`models.py`**: Speicherstrukturen (Datenmodelle) wie `MotorState`. Sorgen dafür, dass sich UI und Hardware beim Datenaustausch nicht in die Quere kommen (Thread-Sicherheit).
* **`calibration.py`**: Kümmert sich um die Mathematik, um die rohen Motor-Ticks (z. B. 2048) in Prozentwerte (0-100%) umzurechnen.
* **`sequences.py`**: Der "Player" für automatisierte Abläufe.
* **`motor_control.py`**: Ein kleines Start-Skript, das aus Gewohnheit früherer Versionen noch existiert (startet intern einfach `main.py`).
* **`test_app.py`**: Automatisierte Tests, um sicherzugehen, dass Kernfunktionen beim Weiterprogrammieren nicht kaputtgehen. Starten mit: `python -m unittest test_app.py`

### Datenspeicher (Konfigurationen & Speicherstände)
* **`config.json`**: Welche COM-Ports und Motor-IDs verwendet werden.
* **`calibration.json`**: Hier merkt sich das System deine eingelernten "Auf/Zu"-Punkte.
* **`motor_names.json`**: Wie die Motoren in der GUI heißen sollen (z. B. "Daumen" statt "Motor 0").
* **`poses.json`**: Deine gespeicherten Hand-Positionen.
* **`sequences.json`**: Deine gespeicherten, automatisierten Handlungsabläufe.
