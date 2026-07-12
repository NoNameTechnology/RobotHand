# 🤖 RobotHand – Dynamixel XL330-M288 Hand-Controller

[![Python Version](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![GUI Framework](https://img.shields.io/badge/GUI-Tkinter-lightgrey.svg)](https://docs.python.org/3/library/tkinter.html)
[![Dynamixel SDK](https://img.shields.io/badge/SDK-Dynamixel_Protocol_2.0-red.svg)](https://emanual.robotis.com/docs/en/software/dynamixel/dynamixel_sdk/overview/)
[![Platform Support](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-brightgreen.svg)](https://github.com/Robotis-GIT/DynamixelSDK)

Diese Software bietet eine moderne, intuitive Benutzeroberfläche zur präzisen Steuerung einer robotergestützten Hand (**RobotHand**). Sie wurde speziell für das Projekt "Soft!-robotic Hands" (SoSe 2026) konzipiert und ermöglicht eine elastische, kraftgesteuerte Seilzug- und Fingersteuerung basierend auf **Dynamixel XL330-M288** Servomotoren.

---

## 🚀 Hauptmerkmale

### 1. Betriebsmodi
* **Position Mode (Joint Mode)**: Klassische Winkelregelung der Servos.
* **Velocity Mode (Wheel Mode / Endlos-Rotation)**: Endlose Drehung mit kontinuierlicher Geschwindigkeitsregelung (z. B. für Spindeln oder Seilwickler).
* **Current-Based Position Mode (Soft-Robotic Mode)**: Positionsregelung mit aktiver Strombegrenzung. Ermöglicht ein nachgiebiges Greifen und schützt die mechanischen Seilzüge vor dem Reißen.

### 2. Live-Telemetrie & Überlastungsschutz
* **Live-Stromaufzeichnung**: Grafische Echtzeitüberwachung des Motorstroms (mA) aller 5 Kanäle im unteren Plot-Bereich.
* **Temperatur-Wächter**: Permanent überwachte Motortemperaturen. Überschreitet ein Motor $55\text{ }^\circ\text{C}$, färbt sich die Anzeige rot und ein Warnbanner wird eingeblendet.
* **Hardware-Diagnose**: Direktes Auslesen des EEPROM-Fehlerregisters der XL330-Servos (z. B. Overload, Overheating) mit optischem Statussymbol ($\checkmark$ oder $\text{Warning}$).
* **EMERGENCY STOP**: Sofortige Deaktivierung des Drehmoments (Torque OFF) für alle Motoren über eine dedizierte Taste.

### 3. Kontakt- & Greiferkennung
* **Flankenerkennung (Rate-of-Change)**: Erkennt plötzliche Strompeaks bei physischem Widerstand.
* **Gleitender Durchschnitt**: Rauschfreie Berechnung über ein konfigurierbares Messfenster (`CONTACT_AVG_WINDOW = 5`), um Fehlauslösungen zu vermeiden.
* **Indikatoren**: Dreistufiger Status pro Motor (● `No Contact` / ● `Approaching` (Annäherung) / ● `Contact!` (Kontakt)).

---

## 📸 Benutzeroberfläche

Die GUI folgt einem aufgeräumten, minimalistischen Design, um den Fokus auf die Steuerung zu legen:
* **Dark & Light Mode**: Ein augenfreundliches Dark Theme (`#0c0c14` Hintergrund) sowie ein sauberer Light Mode (`#f8fafc` Slate-Hintergrund) mit Farbakzenten zur klaren Unterscheidung der Motorkanäle.
* **Zweisprachiges Design**: Die Benutzeroberfläche ist auf Englisch gehalten (Industriestandard), während detaillierte Tooltips (Hover-Erklärungen) auf Deutsch eine schnelle Einarbeitung im Labor gewährleisten.
* **Übersichtliches Layout**: Klar strukturierte Motorkarten mit abgerundeten Abständen, frei von störenden Rahmenlinien.
* **Intuitive Bedienung**: Alle Regler (Positionen, Strombegrenzungen, Geschwindigkeiten, Master-Werte) können präzise mit dem Mausrad verstellt werden. Das Scrollen des Hauptfensters wird währenddessen intelligent blockiert.

---

## 🎓 Ausrichtung auf das Robotik-Projekt (SoSe 2026)

* **Opponierbarkeit**: Unterstützung von bis zu 5 Motoren (IDs `0` bis `4`). Perfekt ausgelegt für vier Finger und einen opponierbaren Daumen.
* **Passive Nachgiebigkeit**: Durch den Current-Based Position Mode geben die Finger bei mechanischem Widerstand elastisch nach, was ein feinfühliges Greifen zerbrechlicher Objekte ermöglicht.
* **Pflicht-Grasps**: Die geforderten Demogriffe (**Edge-Grasp**, **Top-Grasp** und **Wall-Grasp**) sowie die Grundstellung **Hand Open** sind direkt im System als Vorlagen integriert.
* **Wiederholbarkeit (Ablaufsteuerung)**: Der integrierte Sequenz-Player ermöglicht die automatische, fehlerfreie Wiederholung von Greif- und Ablagevorgängen (z. B. exakt 3 Durchläufe für die Projektdemonstration).

---

## 🛠 Hardware-Verkabelung

```text
+------------+     USB     +----------------+   Half-Duplex   +----------+
|  Steuer-   | <=========> |  Robotis U2D2  | <-------------> | Motor #0 | (Daumen-MCP)
|    PC      |             |   Konverter    |   TTL-Bus       +----------+
+------------+             +----------------+                      |
                                   ^                               V
                                   | External Power           +----------+
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

1. **Python 3** herunterladen und installieren.
2. Das offizielle **Robotis Dynamixel SDK** installieren:
   ```bash
   pip install dynamixel-sdk
   ```
3. *(Optional)* **Pillow** für den PNG-Export der Live-Graphen installieren:
   ```bash
   pip install pillow
   ```
4. Die Konfigurationen am Dateianfang von `motor_control.py` anpassen (COM-Port, Baudrate und verwendete Motor-IDs):
   ```python
   COM_PORT = "COM10"
   BAUDRATE = 115200
   MOTOR_IDS = [0, 1, 2, 3, 4]
   ```

---

## 📖 Kurzanleitung zur Bedienung

### 1. Verbindung herstellen
* Wähle den korrekten COM-Port im Code.
* Starte die GUI mit `python motor_control.py`.
* Klicke oben links auf **"Connect"**. Der Status wechselt auf ● **ONLINE**.

### 2. Finger kalibrieren
* Fahre einen Finger manuell (oder bei ausgeschaltetem Torque von Hand) in die offene Position. Klicke auf **"Set Zero"**.
* Fahre denselben Finger in die voll geschlossene Greifposition. Klicke auf **"Set Limit"**.
* Drücke auf das Speichern-Symbol, um die Kalibrierung in die `calibration.json` zu schreiben.
* *Hinweis*: Nach der Kalibrierung wechselt der Motor automatisch in den sicheren *Current-Based Position* Modus. Der Slider skaliert nun linear zwischen 0 % (Zero) und 100 % (Limit).

### 3. Posen speichern und Sequenzen abspielen
* **Pose anlegen**: Bringe die Finger in Position, vergib oben rechts einen Namen (z. B. "Greif-Bereit") und klicke auf das Disketten-Symbol.
* **Schritt hinzufügen**: Wähle eine Pose im Dropdown, stelle die Wartebedingung ein (`ms` für Zeitdauer) und klicke auf **"+ Sequence"**.
* **Sequenz bearbeiten**: Klicke doppelt auf einen Eintrag in der Liste der Ablaufsteuerung, um den Schritt-Editor zu öffnen. Hier können Geschwindigkeiten und Greifkräfte pro Finger separat justiert werden.
* **Ablauf starten**: Klicke auf den blauen **"Start"**-Button.

---

## 📂 Projektdateien & Datenformate

Die Steuerungssoftware speichert alle Konfigurationen automatisch im Projektordner als strukturierte JSON-Dateien:

### ⚙️ `calibration.json`
Speichert die kalibrierten Ticks für den Nullpunkt (geöffnet) und das Limit (geschlossen):
```json
{
  "calib_zero":  { "0": null, "1": 2383, "2": -3898, "3": null, "4": null },
  "calib_limit": { "0": null, "1": 5103, "2": 1133,  "3": null, "4": null }
}
```

### 🏷️ `motor_names.json`
Ordnet den Motor-IDs lesbare Namen für das Dashboard und die Legenden zu:
```json
{
  "0": "Motor 0",
  "1": "Daumen-MCP",
  "2": "Daumen-ALL",
  "3": "Motor 3",
  "4": "Motor 4"
}
```

### 💾 `poses.json`
Enthält abgespeicherte statische Handstellungen samt Positionen, individueller Kraftgrenzen (mA) und aktivierter Soft-Grip Toggles:
```json
{
  "Hand Open": {
    "pose": { "1": 2383, "2": -3898 },
    "limits": { "1": 1750, "2": 1750 },
    "velocities": { "1": 100, "2": 100 },
    "soft_grip_global": false,
    "soft_grip_motors": { "0": false, "1": false, "2": false, "3": false, "4": false }
  }
}
```

### 🎬 `sequences.json`
Beinhaltet verkettete Bewegungsabläufe. Jeder Schritt kann entweder eine feste Wartezeit (`Time`) oder eine sensorische Bedingung (`Grasp` - warten auf Kontakt) besitzen:
```json
{
  "MeinAblauf": {
    "frames": [
      {
        "name": "Hand Open",
        "state": {
          "pose": { "1": 2383, "2": -3898 },
          "limits": { "0": "default", "1": "default", "2": "default" },
          "velocities": { "1": 100, "2": 100 }
        },
        "wait_type": "Time",
        "wait_val": 50
      }
    ],
    "default_sg": { "0": false, "1": true, "2": true, "3": false, "4": false },
    "default_ma": { "0": 1750, "1": 353, "2": 556 }
  }
}
```
