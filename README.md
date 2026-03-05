# Trail Game (Oregon-ish) – Python Project

A small **Oregon Trail–inspired survival game** built with **Python and Pygame**.
The project focuses on learning game logic, UI systems, and event-driven programming while simulating a classic wagon trail journey.

---

# Features

## 🎮 Core Gameplay

* Travel along a **2000-mile trail**
* Manage wagon resources and party health
* Random trail events (weather, sickness, wagon damage, etc.)
* Seasonal weather system
* Morale and wagon condition tracking

## 👥 Party System

* Create a party of **five named travelers**
* Each member has:

  * Individual health
  * Status conditions
* Party health impacts survival events

## 💰 Starting Classes (Difficulty Levels)

Choose your starting wealth:

| Class        | Starting Money | Difficulty |
| ------------ | -------------- | ---------- |
| Rich         | $50,000        | Easy       |
| Middle Class | $10,000        | Normal     |
| Poor         | $500           | Hard       |

---

# 🦌 Hunting Mini-Game

Interactive hunting system:

* Click animals to shoot
* Each shot costs **1 ammo**
* Animals move across the screen
* Different animals provide different food amounts
* Missed shots still consume ammo

Successful hunting increases food supplies for the wagon.

---

# 🛒 Town Shop

At towns you can purchase supplies.

### Shop Items

| Item        | Effect                   |
| ----------- | ------------------------ |
| Food        | Restores food supply     |
| Ammo        | Used for hunting         |
| Medicine    | Used when illness occurs |
| Repair Kits | Restore wagon condition  |

The shop shows:

* Prices
* Projected cost
* Remaining cash

---

# 🌧 Dynamic Trail Events

Examples include:

* Party members getting sick
* Wagon damage
* Weather changes
* Hunting success or failure
* Morale changes

Events are logged in the **Trail Log panel**.

---

# 💾 Save / Load System

The game supports saving progress.

**Controls**

| Key | Action    |
| --- | --------- |
| S   | Save game |
| L   | Load game |

Save file created:

```text
trail_save.json
```

---

# 🖥 Interface

The interface includes:

* Party status panel
* Trail progress bar
* Event log
* Inventory display
* Action buttons

Actions available:

* Travel
* Rest
* Hunt
* Shop
* Toggle pace
* Toggle rations

---

# ▶ Running the Game

Install dependencies:

```bash
pip install pygame
```

Run the game:

```bash
python oregon_like_complete.py
```

---

# 🧪 Technologies Used

* Python
* Pygame
* JSON save system
* Event-driven UI

---

# 📌 Future Improvements

Possible future upgrades:

* More animal types in hunting
* River crossing mini-games
* Party skill system
* More town types
* Map visualization
* Sound effects and music
* Expanded random events

---

# Author

**Logan Garth Goodwin**

IT / Cybersecurity student focused on building practical projects and learning through hands-on experimentation.

LinkedIn
https://www.linkedin.com/in/logan-g-goodwin/

---
