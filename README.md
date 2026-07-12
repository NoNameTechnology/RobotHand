# RobotHand – Dynamixel XL330-M288 Hand-Controller

[![Python Version](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![GUI Framework](https://img.shields.io/badge/GUI-Tkinter-lightgrey.svg)](https://docs.python.org/3/library/tkinter.html)
[![Dynamixel SDK](https://img.shields.io/badge/SDK-Dynamixel_Protocol_2.0-red.svg)](https://emanual.robotis.com/docs/en/software/dynamixel/dynamixel_sdk/overview/)

Diese Dokumentation beschreibt die **RobotHand**-Software, ein Tool zur Steuerung einer robotergestützten Hand über eine grafische Benutzeroberfläche. 

Entwickelt für das Projekt „Soft!-robotic Hands“ (SoSe 2026), ermöglicht die Software eine elastische, kraftgesteuerte Bedienung von Seilzügen und Fingern über **Dynamixel XL330-M288** Servomotoren. Sie dient sowohl dem manuellen Testen von Greifbewegungen als auch dem Ausführen von automatisierten Sequenzen.

---

## Hauptmerkmale

### 1. Betriebsmodi
* **Positionsmodus (Joint Mode):** Ermöglicht die gradgenaue Winkelregelung der Servos.
* **Geschwindigkeitsmodus (Wheel Mode):** Erlaubt endlose Drehungen mit kontinuierlicher Geschwindigkeitsregelung (geeignet für Spindeln oder Seilwickler).
* **Strombasierter Positionsmodus (Current-Based Position Mode):** Kombiniert Positionsregelung mit einer aktiven Strombegrenzung. Dies führt zu einem nachgiebigen Greifverhalten. Die Hand gibt bei mechanischem Widerstand nach, wodurch die Seilzüge vor dem Reißen geschützt werden.

### 2. Telemetrie & Hardwareschutz
Die Software überwacht die Hardware kontinuierlich:
* **Stromüberwachung:** Grafische Darstellung des Motorstroms (mA) aller 5 Kanäle in Echtzeit.
* **Temperaturüberwachung:** Visuelle Warnung in der Benutzeroberfläche, sobald die Temperatur eines Motors 55 °C überschreitet.
* **Hardware-Diagnose:** Direktes Auslesen des Fehlerregisters (z. B. Overload). Der Status wird über ein Symbol ($\checkmark$ oder Warnung) angezeigt.
* **Not-Aus (Emergency Stop):** Eine dedizierte Schaltfläche deaktiviert sofort das Drehmoment aller Motoren (Torque OFF).

### 3. Kontakt- & Greiferkennung
* **Flankenerkennung:** Das System registriert plötzliche Strom-Peaks, die bei physischem Widerstand auftreten.
* **Signalglättung:** Ein gleitender Durchschnitt über ein definiertes Zeitfenster minimiert Fehlauslösungen durch Signalrauschen.
* **Statusanzeige:** Ein dreistufiges Indikatorsystem (● `No Contact` / ● `Approaching` / ● `Contact!`) visualisiert den aktuellen Zustand jedes Fingers.

---

## Architektur & Code-Erklärung

Die Software ist modular aufgebaut. Um Modifikationen zu erleichtern, werden hier die zentralen Konzepte und zugehörigen Code-Beispiele erläutert.

### 1. MVC-Architektur
Der Code ist nach dem Model-View-Controller-Muster (MVC) getrennt:
* **Model (`models.py`):** Speichert den Status der Motoren (z. B. aktuelle Position, Temperatur).
* **View (`ui.py`):** Definiert die Tkinter-Benutzeroberfläche und zeigt die Daten des Models an.
* **Controller (`main.py`):** Verbindet Model und View und leitet Benutzereingaben an die Hardware weiter.

### 2. Multithreading (Verhindern von UI-Freezes)
Serielle Kommunikation benötigt Zeit. Um zu verhindern, dass die GUI während des Wartens auf Sensorwerte einfriert, nutzt die Applikation zwei Threads. 
Der Controller (`main.py`) startet die UI und den Hardware-Manager in separaten Threads.

Ein Blick in die `main.py`:
```python
# Instanziierung des State-Models
self.state = RobotState(config.motor_ids)

# Starten des Hardware-Threads im Hintergrund
self.hardware = HardwareManager(self.state)
self.hardware.start()

# Starten der GUI im Haupt-Thread
self.ui = RobotHandUI(self.root, self)
```

### 3. Serielle Kommunikation (`hardware.py`)
Der `HardwareManager` läuft in einer Endlosschleife und verarbeitet Befehle asynchron. Er nutzt das Dynamixel SDK, um Register auf den Servomotoren zu lesen und zu beschreiben.

Beispiel für das Ausschalten des Drehmoments (Torque OFF) vor dem Beenden der Verbindung:
```python
def disconnect_port(self):
    # Torque bei allen Motoren deaktivieren
    for dxl_id in config.motor_ids:
        motor = self.state.motors[dxl_id]
        self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 0)
        motor.set_torque(False)
        
    self.portHandler.closePort()
```

### 4. Automatisierte Abläufe (`sequences.py`)
Gespeicherte Positionen (Posen) werden als JSON-Datei (`poses.json`) abgelegt. Der Sequenz-Player iteriert durch diese Posen, sendet Zielpositionen an die Hardware-Queue und wartet das definierte Zeitintervall ab.

---

## Ausrichtung auf das Robotik-Projekt (SoSe 2026)

* **Opponierbarkeit:** Steuerung von bis zu 5 Motoren (IDs `0` bis `4`), konzipiert für vier Finger und einen Daumen.
* **Passive Nachgiebigkeit:** Ermöglicht das Greifen empfindlicher Objekte ohne Beschädigung.
* **Vordefinierte Griffe:** Die erforderlichen Demonstrationsgriffe (**Edge-Grasp**, **Top-Grasp**, **Wall-Grasp**) sind als Posen-Vorlagen implementiert.
* **Wiederholbarkeit:** Der Sequenz-Player garantiert eine exakte Reproduktion der Greifabläufe für Vorführungen.

---

## Hardware-Verkabelung

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

## Installation & Setup

1. **Python 3** installieren.
2. Benötigte Bibliotheken (Dynamixel SDK und Pillow) via pip installieren:
   ```bash
   pip install dynamixel-sdk pillow
   ```
3. COM-Port und Motor-IDs in der Datei `config.json` entsprechend dem System anpassen:
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

## Kurzanleitung zur Bedienung

### 1. Verbindung herstellen
* Führe das Hauptskript aus: `python main.py`
* Betätige die Schaltfläche **"Connect"**. Der Statusindikator wechselt bei Erfolg auf ● **ONLINE**.

### 2. Kalibrierung
Die Software muss die minimalen und maximalen Motor-Ticks erfassen:
* Überführe einen Finger in die geöffnete Position (manuell oder im Wheel-Modus) und klicke auf **"Set Zero"**.
* Überführe denselben Finger in die geschlossene Greifposition und klicke auf **"Set Limit"**.
* Speichere die Kalibrierung über das Diskettensymbol. Der Positionsregler des Motors ist fortan auf 0 % bis 100 % linearisiert.

### 3. Posen und Sequenzen verwalten
* **Pose erstellen:** Bringe die Finger in die gewünschte Position, vergib einen Namen und speichere die Pose ab.
* **Sequenz erstellen:** Füge gespeicherte Posen nacheinander zur Sequenzliste hinzu und definiere pro Schritt eine Wartezeit (in Millisekunden).
* **Ausführung:** Starte die Sequenz mit dem **"Start"**-Button. Das System arbeitet die Liste automatisch ab.

---

## Projektstruktur

* **`main.py`**: Applikations-Controller (Initialisierung von UI und Threads).
* **`ui.py`**: Tkinter-Benutzeroberfläche und Event-Bindings.
* **`hardware.py`**: Serielle Kommunikation via Dynamixel SDK in einem separaten Thread.
* **`models.py`**: Thread-sichere Datenmodelle (`RobotState`, `MotorState`).
* **`calibration.py`**: Umrechnung der Encoder-Ticks in Prozentwerte und Nullpunktverwaltung.
* **`sequences.py`**: Sequenzer-Logik zum zeitgesteuerten Abspielen von Posen.
* **`test_app.py`**: Unit-Tests (Aufruf mit `python -m unittest test_app.py`).

Konfigurationsdateien:
* **`config.json`**: Hardware-Parameter (Baudrate, Port, IDs).
* **`calibration.json`**: Kalibrierte Endanschläge der Motoren.
* **`motor_names.json`**: GUI-Bezeichner der Motoren.
* **`poses.json`**: Gespeicherte Handpositionen.
* **`sequences.json`**: Konfigurierte Bewegungsabläufe.
