# Wiring

Every wire in SlabRail, plus how power is laid out and how to check it before power-up. The block
diagram is [img/wiring.svg](img/wiring.svg). Firmware set-up is in [FIRMWARE.md](FIRMWARE.md),
and pin numbers come from [CONTRACT.md](CONTRACT.md).

Confidence tags: **[Certain]** = primary source (datasheet, schematic, FluidNC source),
**[Likely]** = strong inference or several secondary sources, **[Guessing]** = a gap I filled.
Vendor product pages could not be opened from this session. The module facts come from
search-engine extracts of the listings, and every "measure" step below exists because of that.

**Safety rules.**
- Have a mechatronics instructor check the mains side (§1.1) before the first power-up.
- Never plug or unplug a stepper motor while the Rodent has 24 V.
- Everything after the 24 V supply is SELV (safe extra-low voltage). Most of the work is there.

## Contents

1. [Power architecture](#1-power-architecture)
2. [Board jumpers](#2-rodent-jumpers)
3. [Wire tables](#3-wire-tables)
4. [MOSFET modules](#4-mosfet-modules)
5. [Vacuum sensor](#5-vacuum-sensor-xgzp6847a--ads1115)
6. [Contact probe](#6-contact-probe-fail-safe-optical-endstop)
   - [6a. Carry-height sensor](#6a-carry-height-sensor-z-stall-guard)
7. [Limit switches](#7-limit-switches-nc)
8. [Overfill laser gate](#8-overfill-laser-gate)
9. [LED rings](#9-led-rings)
10. [Cameras](#10-cameras)
11. [Drag chain and Z loop](#11-cable-routing-drag-chain-and-z-service-loop)
12. [Grounding and shielding](#12-grounding-and-shielding)
13. [Strain relief and connectors](#13-strain-relief-and-connectors)
14. [Pre-power checklist](#14-pre-power-checklist-multimeter)
15. [First power-up](#15-first-power-up)
16. [Open risks](#16-open-risks)

## 1. Power architecture

```
 wall ──C13 cord──► IEC C14 inlet (fuse T3.15A + rocker) ──L,N,PE──► Mean Well LRS-150-24
                    in the closed ABS mains box, gland ──►              │ +V 24.5 V      │ −V
                                                                        ▼                ▼
                                                 E-STOP (2 NC blocks in series, latching) 0 V bus (Wago)
                                                                        │                ├─ bond to FG/PE (one point)
                                                                  24 V switched bus      │
                         ┌──────────────────┬──────────────────────────┤
                         F1 5 A             F2 3 A                     F3 1 A
                         │                  │                          │
                   Rodent VIN         24 V load bus              24→12 V buck
                   (motors+logic)     Q1 pump, Q2 vac valve,      │
                                      Q3 vent valve               12 V bus: Q4 head LED, Q5 station LED

 wall ──► Raspberry Pi 27 W USB-C PSU ──► Pi 5 (own supply, never fed from the 24 V system)
            Pi 5 V / 3.3 V pins ──► vacuum sensor, ADS1115, Class 2 laser, laser receiver
```

### 1.1 Mains side (instructor check)

- **Inlet: an IEC C14 inlet with a built-in fuse holder and rocker switch** (BOM "Mains inlet").
  One part gives you the inlet, fuse and power switch.
- **It lives in the mains box, not on the plywood panel** (BOM "Mains box": a small ABS box, a cable
  gland and fully insulated 6.3 mm receptacles or tab boots). [Likely: snap-in IEC modules are made
  for 1–3 mm panel walls, so on 6 mm plywood they end up glued or hanging, with live tabs open.]
  - Cut the inlet's rectangular hole in the box wall and snap the inlet in.
  - Put fully insulated receptacles (or boots) on every inlet tab, including the fuse-holder side.
  - W2–W4 leave through the cable gland, tightened on the cable jacket, to the LRS terminal strip.
  - Close the lid with its screws. **With the cord plugged in, no metal at mains voltage may be
    exposed anywhere** (inlet back, fuse holder, LRS terminals). The instructor checks this (§14).
  - An ABS box needs no earth bond. A metal box (Hammond 1590 type) must be bonded to PE.
  - Fuse **T3.15A** slow-blow (5 × 20 mm), as in the BOM. [Likely: suits a 156 W supply on
    115 V. Check the LRS-150 datasheet's input current and inrush before final choice]
- **Mean Well LRS-150-24: 24 V, 6.5 A, 156 W, output adjustable 21.6–28.8 V.** [Certain from
  reseller copies of the datasheet]
  - **It has a 115/230 VAC selector switch.** [Certain, reseller listings] Set it to your mains
    (115 in the US) **before** the first power-up. On 115 V mains, the 230 position won't run
    properly. On 230 V mains, the 115 position destroys the supply.
- Wire L, N and PE with 18 AWG (0.75 mm²) mains-rated wire, using the colours in the wire table.
  - **Colour mapping** (the BOM line is the EU set; US 18 AWG MTW is easier to buy, and the
    instructor decides which): line = brown (EU) or black (US); neutral = blue (EU) or white (US);
    earth = green/yellow (EU) or green (US). W2–W6 below accept either set. [Certain, IEC 60445 and
    US NEC conventions]
  - Keep the mains wire inside the mains box and the LRS terminals. On the low-voltage side black
    means 0 V and white +5 V (the colour table in §3), so never reuse leftover mains wire there.
  - The terminal labels are printed on the supply's terminal strip. Follow them.
  - Fit the supply's terminal cover.
- The Pi's 27 W USB-C supply plugs into its own wall socket, or into the same power strip as the
  machine cord. **It is never fed from the 24 V system.** That is what keeps the Pi alive when the
  machine power is cut.

### 1.2 Why one 24 V supply, and why this one

- **Every motor-side load is a 24 V part.** The Rodent's driver input, the BOM's pump and both
  Clippard EV-2-24 valves all run on 24 V. Only the LED rings need 12 V, from one small buck.
- **The Rodent's input range starts at 24 V.** The manual says "DC24V to DC56V". [Certain] So 24 V
  is the bottom of its range. **Set the LRS to 24.5 V** with its V.ADJ trimmer (no load). That
  leaves margin for wire drop while staying inside the pump and valve ratings (24 V ± 10 % is
  normal for solenoids [Likely]).
- **The load budget is under 4 A peak against a 6.5 A rating.** [Guessing, before parts are
  measured]

| Load | Typical | Peak | Note |
|---|---:|---:|---|
| X motor (1.0 A phase, through the TMC2160) | 0.3 A | 1.0 A | supply current is lower than phase current |
| Z motor (0.8 A phase) | 0.2 A | 0.8 A | |
| Rodent logic | 0.1 A | 0.1 A | |
| Vacuum pump (24 V diaphragm) | 0.4 A | 1.2 A at start | measure yours |
| 2 × valve | 0.05 A | 0.1 A | about 1 W coils [Guessing] |
| 12 V buck for 2 LED rings | 0.1 A | 0.2 A | at 24 V |
| **Total** | **≈1.2 A** | **≈3.4 A** | LRS-150-24 = 6.5 A |

The smaller LRS-100-24 (4.5 A) would also carry it. The 150 W model costs a few dollars more and
copes better with the capacitor inrush every time the E-stop is released. [Likely]

### 1.3 E-stop

**What it is:** a 22 mm latching mushroom E-stop with NC contacts, in its own box (BOM item). It
sits **in the +24 V line straight after the supply**. Pressing it cuts:
- the Rodent (both motors and the controller's logic);
- the pump and both valves;
- the LED buck.

**What it doesn't cut:** the Pi, which stays alive on its own supply, and the sensors it powers.

**What happens on E-stop**
- **Motors go limp.** DESIGN.md estimates the Z head holds on detent torque. The test is in
  FIRMWARE.md's open issues. [Likely]
- **Both valves are normally closed, so both close.** The cup line stays sealed, and a held slab
  stays on the cup for a while. Acceptance test 13.4 in the build guide checks this.
- **The Rodent switches off**, and its USB-serial chip with it. The Pi sees `/dev/ttyUSB0` vanish.
  - The software must stop and tell you "controller lost power".
  - After you twist the E-stop to release it, run `home` before anything else.

**Contact rating and the two contact blocks (required)**
- **Use two NC contact blocks wired in series** (BOM: a box with two NC blocks, or add a clip-on
  22 mm NC block, about $3). Why: the contact switches 24 V DC straight into the Rodent's and the
  buck's input capacitors. Every release charges them through nothing but wire and contact
  resistance, and that inrush can weld a small contact closed. [Likely] A welded NC E-stop is
  invisible: the button is down and the machine is still live. With two blocks in series, one
  welded block still leaves the other to open.
- Use blocks rated for **at least 5 A at 24 V DC** if you can find the rating. Many 22 mm blocks
  only list AC ratings. [Guessing on what you'll receive]
- **Do not "fix" this with an ordinary 24 V relay** switched by the E-stop: its contacts see the
  same inrush and can weld the same way. Only a force-guided safety relay would help.
- The alternative is to put the E-stop in the supply's mains feed (AC-rated contacts, and the LRS's
  own soft start removes the DC inrush). That means mains wiring in the E-stop box: instructor only.
- **Check it monthly** (OPERATING.md §7): with the machine idle, press the E-stop. The software must
  report the controller lost, and the 24 V switched bus must read 0 V on a meter.
- Only if F3 actually blows when you release the E-stop, change it to 2 A (the ring wiring takes
  it).

**Mounting:** at the front of the machine, where you can hit it without reaching over the bed.

### 1.4 Branch fuses (ATC blade, inline holders)

| Fuse | Feeds | Rating | Why |
|---|---|---|---|
| F1 | Rodent VIN | 5 A | Above 3.4 A peak, below the 18 AWG wire limit |
| F2 | Pump + both valves (24 V load bus) | 3 A | Pump start current. Protects the 22 AWG load wiring. |
| F3 | 24→12 V buck (LED rings) | 1 A | Protects the 22/24 AWG ring wiring |

The BOM's "Branch fuses" line has three inline holders with 1 A, 3 A and 5 A fuses. [Certain,
BOM.csv]

### 1.5 12 V buck for the LED rings

- Use the BOM's 24→12 V 3 A buck module. The Pololu D36V28F12 (12 V, 2.4 A, 12.9–50 V input) is a
  documented alternative. [Certain, Pololu specs]
- Set or check 12.0 V before connecting the rings.
- Its ground goes to the 0 V bus.

## 2. Rodent jumpers

| Jumper | Setting | Why |
|---|---|---|
| SW_VCC (limit-input voltage) | **5V** | The optical probe is powered from V-Lim, and its output stage only works if V-Lim matches its 5 V supply (§6). |
| V-Probe | **5V** | The Probe connector is unused. 5 V is the safe choice. |
| NPN EN | **off** | Not needed |
| VUSB | **off** | BTT: "Do not insert the jumper when the device is in use." [Certain] |
| DIAG X/Y/Z/E | **none** | They connect driver stall outputs to the limit pins. |

## 3. Wire tables

**Wire gauge**
- 18 AWG for mains and the 24 V trunk.
- 22 AWG for motors and 24 V/12 V loads.
- 24–26 AWG for signals.

**Colours**

| Colour | Use |
|---|---|
| red | +24 V |
| orange or yellow | +12 V |
| white | +5 V (Pi side) |
| black | 0 V |
| blue | switched minus (load return through a MOSFET) |
| green/yellow | protective earth only |
| other | signals |

**Labelling:** write the W-number on both ends of every cable.

Connector types on the Rodent are 2.54 mm pitch 3-pin (limits, probe) and 4-pin (motors) headers.
They look like JST-XH in BTT's renders. [Likely] **Check against your board before you crimp.**
Power is on screw terminals. [Certain]

### 3.1 Mains and 24 V / 12 V power

| W | From | To | Wire | Ends | Notes |
|---|---|---|---|---|---|
| W1 | Wall socket | IEC C14 inlet | C13 cord | moulded | BOM power cord |
| W2 | Inlet L (after fuse and switch) | LRS L | 18 AWG brown/black, 300 V | fork crimp or ferrule | **mains** |
| W3 | Inlet N | LRS N | 18 AWG blue/white, 300 V | fork or ferrule | **mains** |
| W4 | Inlet PE | LRS FG (⏚) | 18 AWG green/yellow (US: green) | fork or ferrule | earth |
| W5 | LRS FG | Frame bond point on the base 2040 | 18 AWG green/yellow (US: green) | M5 ring + serrated washer into a T-nut | §12 |
| W6 | LRS −V | LRS FG | 18 AWG green/yellow (US: green), short | ferrules | the **only** 0 V-to-earth bond |
| W7 | LRS +V | E-stop box contact IN | 18 AWG red (one core of a 2-core cable, about 1.5 m) | ferrule / contact screw | |
| W8 | E-stop contact OUT | 24 V switched bus (Wago 221-415) | 18 AWG red (other core of W7's cable) | ferrule / lever | |
| W9 | LRS −V | 0 V bus (Wago 221-415, two joined if needed) | 18 AWG black | ferrule / lever | |
| W10 | 24 V switched bus | F1 5 A holder → Rodent VIN "VCC" | 18 AWG red | lever / ferrule into the screw terminal | |
| W11 | 0 V bus | Rodent VIN "GND" | 18 AWG black | ferrule | |
| W12 | 24 V switched bus | F2 3 A holder → 24 V load bus (Wago) | 20–22 AWG red | lever | |
| W13 | 24 V switched bus | F3 1 A holder → buck VIN+ | 22 AWG red | lever / solder or screw | |
| W14 | 0 V bus | buck GND (input side) | 22 AWG black | | |
| W15 | Buck VOUT 12 V | 12 V bus (Wago 221-413) | 22 AWG orange | | |

### 3.2 MOSFET modules and loads (Q1–Q5, Adafruit #5648, see §4)

Each module has an input header (load supply **V+**, **GND**, **SIG**) and two output terminals
(**+**, which is tied to V+, and **−**, which the MOSFET switches to GND). Use the silkscreen names
on your board.

| W | From | To | Wire | Ends | Notes |
|---|---|---|---|---|---|
| W20 | 24 V load bus | Q1, Q2, Q3 V+ | 22 AWG red | JST PH or 0.1" pad | The module V+ **must** be the load's own supply, or the flyback diode can't clamp. |
| W21 | 12 V bus | Q4, Q5 V+ | 22 AWG orange | JST PH or pad | |
| W22 | 0 V bus | Q1–Q5 GND | 22 AWG black | JST PH or pad | |
| W23 | Q1 out + / − | Pump + / − | 22 AWG red / blue, ≤ 0.5 m | screw terminal, ferrules | Check pump polarity: DC diaphragm pumps are polarised. |
| W24 | Q2 out + / − | Vacuum valve coil (EV-2-24 leads) | 22–24 AWG | screw terminal; solder + heat-shrink at the valve | Coil polarity doesn't matter for an EV-2 [Likely] |
| W25 | Q3 out + / − | Vent valve coil | 22–24 AWG | as W24 | |
| W26 | Q4 out + / − | Head LED ring (through the 8-core, cores 6 and 7, §11) | 24 AWG | screw terminal / solder at the ring | |
| W27 | Q5 out + / − | Station LED ring | 22 AWG 2-core, about 0.8 m | screw terminal / solder | Runs beside the CSI ribbon through the bed slot |

### 3.3 Raspberry Pi 5 header and the I/O board

**What the I/O board is:** a small perfboard, about 70 × 50 mm, next to the Pi. It carries the
ADS1115, the XGZP6847A, the three dividers (vacuum sensor, laser gate, carry-height sensor) and
screw terminals. It connects to the
Pi header with female Dupont leads.

**Physical pin numbers** are the standard 40-pin layout. [Certain]

| W | Pi pin | Signal | To | Wire | Notes |
|---|---|---|---|---|---|
| W30 | 1 | 3.3 V | ADS1115 VDD | 26 AWG Dupont | Gives the ADS 3.3 V I2C pull-ups |
| W31 | 2 | 5 V | I/O board 5 V rail: sensor VDD, laser, receiver | 24 AWG | about 50 mA total |
| W32 | 6 | GND | I/O board GND rail | 24 AWG | |
| W33 | 3 | GPIO2 SDA | ADS1115 SDA | 26 AWG, < 20 cm | |
| W34 | 5 | GPIO3 SCL | ADS1115 SCL | 26 AWG, < 20 cm | ADS ADDR → GND gives 0x48 [Certain, TI datasheet] |
| W35 | 11 | GPIO17 | Q1 SIG (pump) | 24 AWG | |
| W36 | 13 | GPIO27 | Q2 SIG (vacuum valve) | 24 AWG | |
| W37 | 15 | GPIO22 | Q3 SIG (vent valve) | 24 AWG | |
| W38 | 16 | GPIO23 | Q4 SIG (head LED) | 24 AWG | |
| W39 | 18 | GPIO24 | Q5 SIG (station LED) | 24 AWG | |
| W40 | 22 | GPIO25 | Lid switch C (switch NO → GND, pin 20) | 24 AWG 2-core | Optional. Closed = lid shut. |
| W41 | 29 | GPIO5 | Gate divider midpoint (§8) | 24 AWG | |
| W48 | 31 | GPIO6 | Carry-height sensor divider midpoint (§6a) | 24 AWG | GPIO 6 is used by nothing else [Certain, docs, software and firmware searched] |
| W42 | 9 | GND | **0 V bus** (one wire) | 22 AWG black | Common reference for the MOSFET inputs. Keep it even though USB also joins the grounds. |
| W43 | USB 2.0 (black) port | | Rodent USB-C | USB-A → USB-C **data** cable, 1 m | Serial to FluidNC |
| W44 | USB 2.0 (black) port | | Head-camera extension (§10) | | |
| W45 | CAM/DISP 0 | | Station camera | 500 mm Pi 5 camera cable | §10 |

### 3.4 Rodent inputs and motors

| W | From | To (Rodent) | Wire | Ends | Notes |
|---|---|---|---|---|---|
| W50 | X motor (right end of beam) | Socket **X** | 22 AWG 4-core, about 1.3 m, static | 4-pin 2.54 mm housing | Along the beam's back slot to the middle, then down with the bundle. The BOM's extension is needed if the motor lead is 1 m. |
| W51 | Z motor (top of Z spine) | Socket **Z** | 4-core 22 AWG shielded high-flex, about 2.5 m, through the chain | 4-pin housing; shield → Rodent GND at board end only | |
| W52 | X home switch (left end of beam): **C** and **NC** tabs | **X-MAX**: signal and GND | 24 AWG 2-core, about 1.3 m, static | 3-pin housing (V-Lim pin empty) | §7. Not "X-MIN": the board's names don't matter, the config does. |
| W53 | Z top switch on the spine: **C** and **NC** | **Z-MAX**: signal and GND | 8-core cores 4 and 5, through the chain | 3-pin housing | §7 |
| W54 | Optical probe board: VCC, GND, OUT | **Y-MAX**: V-Lim, GND, signal | 8-core cores 1, 2 and 3, through the chain | 3-pin housing | §6. Yes, Y-MAX: there is no Y axis. |
| W55 | Carry-height sensor board (Z spine): VCC, GND, OUT | VCC and GND: spliced into cores 1 and 2 at the spine top (the probe's 5 V and GND). OUT: core 8 → **I/O board divider → Pi GPIO 6** (not the Rodent) | the board's 3-pin cable, about 0.2 m, then the 8-core through the chain | solder + heat-shrink at the splice; screw terminal at the I/O board | §6a |
| — | nothing | Sockets **Y** and **E** | — | — | Spare drivers (FIRMWARE.md). Leave them empty. |
| — | nothing | Probe, E0-MAX, E1-MAX, V-MOS, RS485, spindle | — | — | unused |

### 3.5 Overfill gate (Pi side)

| W | From | To | Wire | Ends | Notes |
|---|---|---|---|---|---|
| W46 | I/O board 5 V and GND | Class 2 (≤ 1 mW) laser module + and − (left gate post) | 24 AWG 2-core, about 1.2 m | Dupont / solder + heat-shrink | §8. Along the bed's front edge in clips. |
| W47 | I/O board 5 V, GND, divider input | Receiver VCC, GND, OUT (right gate post) | 24 AWG 3-core, about 1.2 m | Dupont / solder | 2.2 kΩ OUT-to-VCC pull-up soldered **at the receiver** (§8) |

## 4. MOSFET modules

**Pick: Adafruit MOSFET Driver, product #5648, ×5.** It switches the pump, the vacuum valve, the
vent valve and both LED rings, all low-side. [Certain for the specs below, from Adafruit's listing
as quoted by several resellers]

**Why this module**
- **It is specified for 3 V logic.** The listing says "signal (3V to 20V logic level)". It uses an
  AO3406 N-MOSFET (30 V, 70 mΩ). A 3.3 V Pi pin turns it fully on, with no guessing about gate
  threshold.
- **The flyback diode is on the board** (1N4007). The pump and valve coils need one, and an
  on-board diode can't be soldered in backwards or forgotten.
- **Its current rating covers every load here:** 1.5 A continuous, 3 A peak. The JST PH input is
  rated 2 A.
- **The 30 V rating is enough on a 24.5 V bus**, because the diode clamps coil spikes to about
  25.5 V. [Likely]

**If you substitute "D4184" (AOD4184) modules** (the BOM keeps 1N5819 diodes as a qty-0
conditional line for this case): those modules switch more current, but they have no flyback
diode. Their makers also give no 3.3 V drive figure, so whether they switch fully at 3.3 V is
unconfirmed. [Likely] If you use them:
- solder a diode across each pump and valve coil, cathode (stripe) to +;
- with the load on, check that the voltage across the module's output is under 0.2 V.

Don't use IRF520 modules: they aren't logic-level.

**Rules for all five modules**
- **Module V+ must be the load's supply:** 24 V for Q1–Q3, 12 V for Q4–Q5. The diode returns the
  coil current to V+.
- **Add a 10 kΩ resistor from SIG to GND on each module** unless you measured one already there.
  Power off and measure SIG to GND **before the first power-up** (§14 step 13). [Guessing whether
  #5648 has one; Adafruit's listing does not mention one] The Pi's GPIOs float while it boots or is
  off, and the pull-down keeps the pump and valves off. Without it, a floating vent gate can open
  the vent and drop a held slab.
- **If your pump draws more than 1.2 A running or 3 A at start, use a bigger module for Q1 only.**
  Measure it on the bench with a meter in series.

## 5. Vacuum sensor (XGZP6847A + ADS1115)

**Part: CFSensor XGZP6847A100KPGN.** Analog, 5 V supply, −100…0 kPa ("GN" = negative gauge),
0.5–4.5 V out. [Certain, CFSensor ordering code via distributor extracts] **A part number ending
in "33" is the 3.3 V version. Don't buy that one.**

**Pins** (DIP-6) [Certain, CFSensor datasheet as quoted]:

| Pin | Name | Connect to |
|---|---|---|
| 1 | N/C | nothing. The datasheet says leave it floating. |
| 2 | VDD | I/O board 5 V rail |
| 3 | GND | I/O board GND |
| 4 | VDD | 5 V (duplicate of pin 2; connect it too) |
| 5 | OUT | 10 kΩ → node A |
| 6 | GND | GND (duplicate of pin 3; connect it too) |

**Circuit**
```
 5V ─┬─ XGZP pin 2 & 4          node A ── ADS1115 A0
     └─ 100 nF ─ GND             │
 XGZP pin 5 (OUT) ── 10 kΩ ──────┤
                                 ├── 20 kΩ ── GND
                                 └── 100 nF ── GND   (optional filter)
 ADS1115: VDD 3.3 V (Pi pin 1), GND, SDA/SCL to Pi, ADDR to GND (0x48)
 optional: 5V ── 10 kΩ ── node B ── 20 kΩ ── GND ; node B ── ADS1115 A1  (supply monitor)
```

**Why the divider**
- The ADS1115 runs on 3.3 V, so that its I2C pull-ups match the Pi. Its inputs must stay within
  GND − 0.3 V to VDD + 0.3 V = 3.6 V. [Certain, TI datasheet]
- The sensor's 4.5 V output × 20/(10+20) = **3.0 V**. Even a sensor stuck at its 5.1 V rail gives
  3.4 V.
- `hw.py` already uses `DIVIDER = 2/3` and the ±4.096 V range. [Certain]

**Expected readings**
- **At atmosphere: about 4.5 V at pin 5 and about 3.0 V at A0, so hw.py shows about 0 kPa.**
  - This assumes the standard direction: 0.5 V at −100 kPa, 4.5 V at 0 kPa, as `hw.py` expects.
    [Likely; CFSensor can calibrate either direction]
  - If you read about 0.5 V at atmosphere, your sensor is reversed. Tell the software owner to flip
    the formula. Don't rewire.
- **Optional supply monitor on A1:** the output is ratiometric to the 5 V supply, and the Pi's 5 V
  can sit anywhere from 4.9 to 5.2 V. That error is ±3 kPa, which is fine for the −35 kPa seal
  threshold. Wiring A1 lets the software correct it later. [Likely]

**Tubing:** the sensor has a 3 mm barb. Use 2 mm ID silicone tube (BOM) from the barb to a tee on
the **cup side** of the vacuum valve, so it reads the cup line, not the reservoir. Mount the I/O
board near the valves so this tube stays short.

## 6. Contact probe (fail-safe optical endstop)

**Part:** a slotted optical endstop board with a TCST2103 sensor (BOM), on the head foot's sensor
post. A 1 mm aluminium flag, clamped under the vacuum elbow on top of the spring buffer, rises
through the slot as the cup is pushed up (BUILD_GUIDE §7.6; it is in the CAD as `probe_flag`).

**Wiring (W54):**
- board **VCC** → Rodent Y-MAX **V-Lim**, which is 5 V with the SW_VCC jumper on 5 V;
- board **GND** → Y-MAX **GND**;
- board **OUT/SIG** → Y-MAX **signal**.

**How the Rodent's limit input works** [Certain, V1.0.2 schematic]
- The signal pin is the cathode of an opto LED, fed from V-Lim through 1 kΩ.
- **When the sensor output pulls low (sinks about 4 mA), the input reads LOW = "not touching".**
- When the output is high or disconnected, the opto is off and the input reads HIGH =
  **triggered**. The config uses `pin: gpio.34`, active high.

**Mechanical rule (this is what makes it fail-safe)**
- **At rest, the slot must be clear**, so the light reaches the detector and the output is LOW.
- **Contact pushes the flag into the slot.** The output goes HIGH, which reads as triggered.
- Set the board in its slots so the flag blocks the beam after 2.0 ± 0.5 mm of buffer travel
  (BUILD_GUIDE §7.6). The sim assumes 2 mm.

**Why this way round:** every failure lands on "triggered", and FluidNC then refuses to probe
(ALARM:4).

| Failure | Input reads | Result |
|---|---|---|
| Signal wire cut | open = HIGH | triggered → safe |
| Sensor GND or VCC cut | output can't sink = HIGH | triggered → safe |
| Emitter LED dead, or dirt in the slot | dark = output HIGH | triggered → safe |
| Rodent loses 24 V | everything off | machine stopped anyway |

**Check your board's polarity first.** Most of these boards output HIGH when the slot is blocked,
which is what you want. [Likely]
1. Power it from 5 V on the bench.
2. Measure OUT to GND: about 0–0.4 V with the slot clear, about 5 V with a card in the slot.
3. If yours is the other way round, don't use it. Inverting the logic would turn a cut wire into
   "not touching".

**Hysteresis (only if needed):** the firmware's `probe_hard_limit` alarms on any probe edge outside
a `G38` move. If the flag chatters at the slot edge during the slow peel, BUILD_GUIDE §13.2's
300 cycles will show "Probe Hard Limit" alarms. Then add hysteresis to the sensor output, keeping
the fail-safe rule (a cut wire must still read triggered): for example a 74HC14 Schmitt inverter
pair powered from V-Lim, with a 10 kΩ pull-up on its input [Guessing; have the instructor check it],
and repeat FIRMWARE.md step 5's fail-safe rows. Or set `probe_hard_limit: false` and live without it.

**Indicator LED caution:** some boards have an indicator LED arranged so that it holds OUT at mid
voltage when "high". The Rodent's opto then stays half on, and the input never reads triggered.
FIRMWARE.md Step 5 catches this.
- **Fallback:** wire a bare TCST2103 directly. Detector collector to signal, detector emitter to
  GND. Emitter LED anode to V-Lim through 220 Ω, cathode to GND. [Likely, standard TCST2103 use]

**Why not the board's Probe connector:** its opto input is the other way round. The sensor would
need to source current at rest, and an emitter failure would read "not touching". (Explained in
config.yaml.)

## 6a. Carry-height sensor (Z stall guard)

**Part:** the second optical endstop board from the BOM's packs (the same TCST2103 board as the
probe), on `carry_sensor_mount` on the Z spine's left face. A flat 1 mm aluminium flag on
`carry_flag_arm` (on the `z_plate`) enters its slot from below once the cup is at least 246.5 mm
above the pad, and stays in it up to the top stop (BUILD_GUIDE §7.4a). [Certain, CAD]

**What reads it:** the Pi, not the Rodent: FluidNC knows nothing about it. The runner reads it
before every sideways move (it must read blocked), before every grip (it must read clear), and on
every Z move with a slab in the cup. [Certain, `runner._carry_check`, `hw.PiCarry`: majority of
three reads 1 ms apart]

**Wiring (W55, W48):**
- At the top of the Z spine, where the 8-core's jacket is already opened for the Z switch (§11):
  board **VCC → core 1** (+5 V, shared with the probe), **GND → core 2**, **OUT → core 8**. Solder
  and heat-shrink each splice. The board is fixed to the X carriage, so its lead runs only in the X
  drag chain and never enters the Z service loop. At the head end, core 8 is cut back and insulated.
- At the panel end: core 8 to the I/O board:

```
  core 8 (OUT) ── 10 kΩ ──┬── GPIO 6 (pin 31)
                          └── 20 kΩ ── GND
```

- 5 V × 20/(10 + 20) = 3.3 V at GPIO 6 with a push-pull output, and the 20 kΩ pulls GPIO 6 LOW
  when the lead is cut. [Certain, arithmetic]
- The board's 5 V comes from the Rodent's V-Lim (core 1). The Pi and the Rodent share a ground
  through W42 and the USB cable. [Certain, §3.3]

**Polarity: HIGH = the flag is in the beam = the head is at carry height.** Check it on the bench
first, as for the probe (§6): OUT about 0–0.4 V with the slot clear, about 5 V with a card in it.
Don't use a board that is the other way round.

**Check the level at GPIO 6 once it is wired** [Likely: many of these boards pull OUT up through
about 10 kΩ, and the 30 kΩ divider then gives only about 2.5 V]: with a card in the slot, GPIO 6
must read at least 2.5 V. If it is lower, solder a 2.2 kΩ pull-up from OUT to VCC **at the board**,
as on the laser receiver (§8). At the board end a cut wire still reads LOW.

| Failure | GPIO 6 reads | Result |
|---|---|---|
| OUT wire (core 8) cut | LOW (the 20 kΩ) | "clear" at travel height: sideways moves are refused ("Z stall suspected … right after homing this is most likely the sensor itself") → safe |
| Board VCC cut, or the Rodent unpowered | LOW | the same → safe |
| Board GND cut | HIGH (OUT floats up to VCC) [Likely] | "blocked" everywhere: **not safe by itself**; caught at the next grip, where it must read clear ("Carry-height sensor fault …") |
| Emitter LED dead, or dirt or a card in the slot | HIGH | the same: **not safe by itself**, caught at the next grip |
| Flag bent away, or the mount slid down | wrong trip height | `selftest --motion` measures the trip; outside 246.5 ± 1 mm it fails |

**Why a dead emitter is not simply fail-safe here:** the flag blocks the beam at carry height, so
"dark" is the "OK to move" reading. The grip rule (the cup is far below the trip at every pick, so
the sensor must read clear there) is what turns a dark sensor into a stop. [Certain, the CAD
report's own warning, implemented in `runner._carry_check`]

## 7. Limit switches (NC)

**Use bare SPDT hinge-lever microswitches with C / NO / NC solder tabs** (the Omron SS-5GL size:
19.8 × 10.2 × 6.4 mm body, holes 9.5 mm apart). The printed mounts take a flat lever that ends at
most 23 mm from the hinge end; cut a longer one back to 20 mm (BUILD_GUIDE §6.8).
- Solder the cable to **C** and **NC**: closed at rest, open when pressed.
- C goes to the connector's GND pin and NC to its signal pin. Leave V-Lim empty.

**Don't use the 3D-printer "mechanical endstop" boards as they come.** (The BOM lists bare lever
microswitches for this reason.) Their LED-and-resistor circuit differs between makers. On some, it feeds the Rodent's opto LED and hides
a pressed switch. [Likely: forum reports]
- If you only have those boards, desolder the switch, or cut the traces and wire straight to its
  C and NC tabs. Check C, NO and NC with a meter.

**How it reads** [Certain, schematic + config]
- At rest: switch closed → opto on → LOW → OK.
- Pressed, or a wire broken: open → HIGH → triggered. Outside homing that is ALARM:1, so a broken
  switch wire stops the machine instead of letting it crash.

**Where the switches go** [Certain, CAD `x_switch_mount`, `z_switch_mount`, `checks.txt`]
- **X home switch:** on the printed `x_switch_mount`, under the beam's left end, on the front faces
  of the beam and the left upright (2 × M5×10 button heads into T-nuts in the beam's lower front
  slot, left of `x_bumper_L`). Lever up, hinge end toward the back. A finger on the `x_bracket`'s
  left edge slides across the lever (a 45° lead-in, then a flat). It must click when the cup axis
  is at layout X ≈ 19 mm, about 23 mm left of pocket 0's centre, **± 2 mm**.
  - The printed `x_bumper_L` is the hard stop at cup X 15, so the switch must trip at least 2 mm
    before the `x_bracket` reaches it. The carriage still has 2.3 mm of rail there. The finger's
    flat holds the lever 0.6 mm past its click point (at the lever tip) all the way to the bumper.
  - **Lead (W52):** from the terminals straight down to about 50 mm below the beam (below the
    corner brackets), back under the beam, then up behind it into the beam's **lower rear** slot,
    and along that slot to the middle (§11). At the left joint, keep the flat joining plate's beam
    leg on the upper rear slot so it does not cover the spot where the lead enters (BUILD_GUIDE
    §4.3). [Certain, CAD lead path; Guessing on the brackets and plate, which are not in the CAD]
- **Z top switch:** on the printed `z_switch_mount`, on the Z spine's right (+X) face near the top
  (2 × M5×10 button heads into T-nuts in that face's slot), fixed to the X carriage. The switch
  lies on the mount's shelf, lever toward the `z_plate`. A 45° chamfer along the `z_plate`'s top
  back edge slides across the lever, and the plate's back face then holds it. It must click at
  c ≈ 258 mm (the cup face 258 mm above the pad top), ± 2 mm. That is 4 mm before the `z_plate`
  meets the `z_motor_mount` (the top hard stop at c = 262).
  - **Lead:** cores 4 and 5 of the 8-core (§11), back past the spine, then up behind the
    `z_motor_mount` to the spine top, where the 8-core's jacket is opened.
- Setting each click point (the switch in its M2 slots, the mount in its M5 slot) is in BUILD_GUIDE
  §6.8 and §7.4. Exact positions are checked in FIRMWARE.md Step 6.

**Lid switch (optional, GPIO25):** use **C and NO**, closed when the lid presses it, so a shut lid
reads LOW (`Button.is_pressed`). A cut wire then reads "lid open", which is safe.

## 8. Overfill laser gate

**Parts (BOM): a ≤ 1 mW (Class 2) 650 nm laser module with a 6 mm barrel, and a non-modulated
laser receiver module.** Both are 5 V parts.
- **Do not use the KY-008 laser that comes in the receiver kit.** KY-008 modules are usually sold
  as 5 mW (Class 3R). [Likely] The laser is on whenever the Pi is on (W46 is the Pi's 5 V), and the
  beam runs along the open row at about 214 mm, the height of a face bent over the stacks while
  loading. A Class 2 beam is protected by the blink reflex; a 3R beam is not. The listing must say
  "≤ 1 mW" or "Class 2 / Class II". Keep the kit's receiver.
- The laser sits in the left gate post and the receiver in the right post, with the beam 4 mm
  above the MAX line. An M3 set screw in each post locks the barrel.
- Stick a "LASER - do not stare into the beam - Class 2" label on both posts.
- **Never look into the beam.** Aim it so it always ends on the receiver.
- [Guessing] If you want the laser off between runs as well, switch its 5 V with a small low-side
  MOSFET from a spare GPIO, on only during the start-up check. The software does not do this yet.
  With the laser off the gate reads "blocked", so it stays fail-safe.

**Laser wiring (W46):**
- 5 V → the module's + (red) lead; GND → − (black). Confirm with a meter that it lights.
- 24 AWG 2-core, about 1.2 m.

**Receiver wiring (W47):**
- VCC → 5 V, GND → GND, OUT → I/O board.
- 24 AWG 3-core, about 1.2 m.

**Level shift and fail-safe**
```
  at the receiver:  OUT ── 2.2 kΩ ── VCC        (solder it on the module's header)
  on the I/O board: OUT ── 10 kΩ ──┬── GPIO5 (pin 29)
                                   └── 20 kΩ ── GND
```
- Most of these receivers are LM393 boards with an open-collector output and a 10 kΩ pull-up.
  [Likely] A bare 10k/20k divider on a 10 kΩ pull-up gives only about 2.5 V, which is marginal for
  a 3.3 V input.
- The extra 2.2 kΩ pull-up raises "high" to about 2.7–3.1 V, and a push-pull output gives 3.3 V.
  Both are inside the Pi's safe range. [Certain, arithmetic]
- The 2.2 kΩ **must sit at the receiver end**. Then a cut OUT wire leaves only the 20 kΩ, which
  pulls GPIO5 LOW = "blocked", and the run won't start.

| Condition | GPIO5 | Meaning |
|---|---|---|
| Beam received | about 3 V, HIGH | clear |
| Beam blocked (stack too tall, or the head is down in the beam plane) | LOW | blocked |
| OUT wire cut, receiver unpowered, laser dead | LOW | blocked → safe |
| Receiver GND wire cut | HIGH | **false "clear"**: the selftest must block the beam and see LOW |

**Check before wiring:** measure the receiver's OUT with the beam on and with it blocked. It must
be **high when the beam is received**. If your module is the other way round, swap it. Don't
invert in software, because a cut wire would then read "clear".

**Room light:** non-modulated receivers can be held HIGH by bright room light. Adjust the module's
trimmer (under the light roof, if you fitted the optional roof) until a blocked beam reads LOW
with the room lights on.

## 9. LED rings

**Parts (BOM):** two 12 V COB "angel eye" white rings: **40 mm** for the head (a 60 mm ring would
cut into the drop arm; the seat in `camera_bracket` and `phase0_top` is a 42.8 mm bore with three
centring ribs and a 33 mm lip: it takes a ring of 39.5–42.5 mm OD, up to 5 mm thick, and the ribs
are shaved for a ring over 40 mm) and 60 or 63 mm for the station (a 64 mm bore on a shelf in
`station_mount` and `phase0_base`). Measure OD, ID and thickness before printing the ring seats
(BUILD_GUIDE §3.3). If no 40 mm COB ring can be found, a 40 mm 12-SMD ring that fits the seat is
the fallback. **Leads:** the head ring's pads and leads leave through the notch in its seat's lip;
the station ring's drop through the shelf slot into the camera ribbon's slot and leave with it.
[Certain, CAD]

**Switching**
- Low side, from GPIO23 (head ring, Q4) and GPIO24 (station ring, Q5).
- Ring + to the 12 V bus through the module's "+" terminal, ring − to the module's "−" terminal.
- If the ring came with a small inline driver box, keep it. Wire the 12 V and module side to its
  input. [Likely: many angel-eye rings must use their driver]

**No dimming by PWM**
- Pi 5 GPIO23 and 24 only have software PWM. The rolling-shutter cameras would show dark bands.
  [Likely]
- Switch the rings fully on and set brightness with camera exposure and gain.
- If a ring is still too bright at minimum exposure, measure its current at 12 V. Then add a
  series resistor that halves it, rated for at least 4 × the power it burns.

**Turn-on time:** the ring drivers may soft-start, and camera auto exposure needs time to adapt.
`hw.py` already waits 0.3 s after switching a ring on (`PiLights.settle_s`) before the first frame.
[Certain, code] If the first frame of each slab still looks dark, raise it.

## 10. Cameras

**Station camera: Camera Module 3 on CAM/DISP 0**
- Use the 500 mm Pi 5 camera cable (22-pin 0.5 mm to 15-pin 1 mm, BOM: Raspberry Pi SC1130).
  **Don't go longer.**
- Mount the Pi on the electronics panel **behind the bed, centred near X ≈ 690** (the station is
  at X = 686). The ribbon then runs from the station mount's rear slot along the bed and down to
  the Pi in about 350 mm.
- Fit the ribbon with the power off. Lift the connector latch, insert, and close it. Follow the
  Raspberry Pi camera guide for which way the contacts face.
- Keep the ribbon away from the motor cables. Cross them at right angles if you have to.

**Head camera: ELP 8 MP USB, IMX179**
- Its own USB lead joins the BOM's 3 m USB 2.0 extension, which runs through the chain and the Z
  loop to a **black USB 2.0 port** on the Pi.
- Total length is about 4 m. USB 2.0 allows 5 m [Certain], so add nothing more. If the camera
  drops out, the first fix is a true drag-chain-rated USB cable (BOM note).

## 11. Cable routing: drag chain and Z service loop

### X drag chain

**Part (BOM):** an openable chain, 15 × 30 mm inside, 1 m long. Openable links let the USB plug
go in. Buy the R38 bend radius or larger if you have the choice. Don't go below R28. [Guessing on
the sizes sold]

**Fixed end:** on the top-back of the X beam, at the **middle of travel, X ≈ 640**.

**Moving end:** on the X bracket's top tab, with a printed adapter.

**Length check** [Certain, chain geometry]
- With the fixed end at mid-travel, the chain needs travel/2 + π·R + margin = 1231/2 + π·38 + 100
  ≈ 0.84 m, so 1 m is enough.
- With the fixed end at a beam end, it needs travel + π·R ≈ 1.35 m. Buy 1.5 m in that case.

**What goes inside**

| # | Item | About | Carries |
|---|---|---|---|
| 1 | 4-core 22 AWG shielded high-flex | Ø 5.5 mm | Z motor (W51) |
| 2 | 8-core 24 AWG shielded high-flex | Ø 6 mm | see below |
| 3 | USB 2.0 extension | Ø 5 mm | head camera |
| 4 | PU tube, 4 mm OD | Ø 4 mm | cup vacuum line |

That fills about 30 % of the chain. Lay the items side by side, untwisted, with nothing crossing.
Don't tie anything inside the chain.

**8-core assignment.** Record your cable's real colours here.

| Core | Use | Rodent end | Head end |
|---|---|---|---|
| 1 | +5 V probe and carry sensor | Y-MAX V-Lim | optical board VCC; carry board VCC (spliced at the spine top) |
| 2 | probe and carry sensor GND | Y-MAX GND | optical board GND; carry board GND (spliced at the spine top) |
| 3 | probe signal | Y-MAX signal | optical board OUT |
| 4 | Z switch signal | Z-MAX signal | Z switch NC |
| 5 | Z switch GND | Z-MAX GND | Z switch C |
| 6 | +12 V head ring | Q4 "+" | ring + |
| 7 | head ring return | Q4 "−" | ring − |
| 8 | carry sensor OUT | I/O board: 10 kΩ / 20 kΩ divider → Pi GPIO 6 (§6a) | carry board OUT, spliced at the spine top; insulated past the splice |
| shield | drain | Rodent GND, board end only | cut back, heat-shrink |

**Off the fixed end:**
- The bundle drops behind the beam to the electronics panel.
- Tie it every 100 mm to the rear brace or to printed clips.
- Keep it more than 100 mm behind the head's path.
- The static X motor cable (W50) and X switch cable (W52) run in the beam's back slot from their
  ends to the middle, then join this bundle. The X switch lead comes up into the lower back slot
  just right of the left upright (§7).

### Z service loop (head moves 263 mm relative to the carriage)

**What's in it:**
- the 8-core carries on past the carriage to the head;
- at the top of the Z spine, open the jacket over about 40 mm and take cores 4 and 5 out to the
  Z switch;
- in the same opening, splice the carry-height sensor's lead to cores 1, 2 and 8 (§6a); core 8
  ends there;
- heat-shrink over the opening.

The 8-core, the USB extension and the vacuum tube then form one loop wrapped in the BOM's 10 mm
spiral wrap.

**Loop path:** from a tie point at the top of the spine down to the top of the drop arm. Then tie
the bundle along the drop arm every 50 mm down to the head.

**Loop size:**
- Make it about 350 mm long, with no bend tighter than 40 mm radius.
- Check by hand at c = 0 and c = 255. The loop must never hang lower than the top of the drop arm.
  At c = 0, that point is 350 mm above the pads (`model.ARM_Z`: the Z carriage 295 mm above the cup
  face, plus 55), well above the 218 mm rod tops. [Certain, layout numbers]

**Tube slack:** leave 25 mm at the cup's `M-5ALU-4` barb elbow, which points to the back (+Y). The
buffer rod rises up to 20 mm on contact (SMC `ZPT25UUK20-B5-A10`, 20 mm stroke). Keep the tube off
the head lens and its LED ring: at full stroke it runs about 1 mm under the ring [Guessing; the
tube is not in the CAD].

## 12. Grounding and shielding

**Protective earth**
- Inlet PE → LRS FG (W4).
- LRS FG → frame (W5): an M5 ring terminal with a serrated washer into a T-nut on the base 2040.
  Scrape the anodising under it.
- Check that each extrusion joint conducts. Anodising insulates, so a joint may need a serrated
  washer. [Likely]

**0 V bond:** one short wire from LRS −V to FG (W6). Nowhere else.
- The Pi's ground joins the 0 V bus through W42 and the USB cable, so the whole low-voltage side
  has one ground.
- The Pi's own USB-C supply is floating (2-pin), so this creates no mains ground loop. [Likely]

**Heavy current returns:** pump, valve and motor currents return to the 0 V bus through their own
black wires, never through the Pi.

**Shields:** connect them at the Rodent end only (its VIN GND terminal or any GND pin). Cut back
and insulate the far end.

**Separation:**
- Keep motor cables at least 50 mm from the CSI ribbon, the ADS1115 and the sensor leads.
- Keep the I2C leads under 20 cm.

## 13. Strain relief and connectors

- **Screw terminals:** use a ferrule on every stranded wire (PSU, Rodent VIN, MOSFET outputs,
  fuse holders, E-stop). **Never put solder-tinned wire in a screw terminal.** It creeps and goes
  loose.
- **Wago 221 lever connectors** take stranded wire directly. Use them for the 24 V, 12 V and 0 V
  buses.
- **Tie every cable to the panel within 50 mm of its connector.** No connector should carry cable
  weight.
- **Drag chain:** tie each cable to the tie-bar at both chain ends.
- **Head:** use P-clips or tie mounts on the drop arm.
- **Crimps:** crimp JST-XH and Dupont housings with the proper tool and pull-test each one. Or buy
  pre-crimped leads.
- **Solder joints:** heat-shrink every one (dividers, cable breakouts, LED ring leads).
- **Moving parts:** put the pump on rubber feet and don't hard-mount it to the panel. Fit a short
  silicone hose section at the pump so vibration doesn't fatigue the fittings.

## 14. Pre-power checklist (multimeter)

Do this with everything wired, **mains unplugged**, and the E-stop released.

**Mains (instructor)**
1. Inlet PE pin to the X beam, Z spine and base: **< 0.5 Ω**.
2. Inlet L to PE and N to PE, switch on: **open (> 1 MΩ)**.
3. Inlet L to N, switch on: **not a short (> 10 Ω)**. The supply's input circuit shows some
   reading.
4. Fuse fitted, T3.15A. **LRS 115/230 switch on your mains voltage.** Terminal cover on.
4a. **Mains box closed, gland tight, insulated receptacles on every inlet tab: no exposed mains
    metal anywhere with the cord plugged in** (§1.1). Not on the plywood panel.

**24 V side**

5. 24 V switched bus to 0 V bus: **> 1 kΩ**. It rises as the meter charges the capacitors. Under
   10 Ω is a short: find it.
6. E-stop pressed: LRS +V to 24 V switched bus **open**. Released: **< 0.5 Ω**. Check both NC
   blocks: each one alone must open the circuit when pressed (meter across each block).
7. F1 = 5 A, F2 = 3 A, F3 = 1 A fitted.
8. Rodent VIN polarity: red to "VCC", black to "GND". [Certain, terminal labels]
9. **24 V bus to Pi 5 V pin: open.** **0 V bus to Pi GND: < 1 Ω.**

**Motors, switches, probe**

10. Motor coils, at the motor plug:
    - each coil pair **1–4 Ω** (the 17HS19-2004S1 is about 1.4 Ω [Likely]);
    - coil to coil **open**.
    - X plugged into socket **X** and Z into **Z**. **Nothing in Y or E.**
11. Limit switches, at the unplugged board-end housing: signal to GND **≈ 0 Ω at rest, open when
    pressed**.

**Loads**

12. Each MOSFET output: "+" to "−" with the load connected:
    - pump: a few tens of ohms [Guessing];
    - valve coil: hundreds of ohms [Guessing];
    - **never close to 0 Ω**.
13. Divider resistors: measure each 10 kΩ, 20 kΩ and 2.2 kΩ (10k and 100k are easy to mix up),
    including the carry sensor's pair (§6a): its GPIO 6 node to GND, with the Pi lead and core 8 unplugged,
    about 20 kΩ.
    **MOSFET SIG pull-downs:** SIG to GND on each of Q1–Q5, Pi lead unplugged: **about 10 kΩ**. Open
    means the pull-down is missing: add it (§4) before any power-up.

**Board set-up**

14. Rodent jumpers as §2. `r_sense_ohms` matches the resistor marking (FIRMWARE.md Step 0).
15. Sensor: pin 1 not connected; pins 2 and 4 to 5 V; pins 3 and 6 to GND.

## 15. First power-up

1. **Pi only (machine cord unplugged).** Boot the Pi, then check:
   - `i2cdetect -y 1` shows **48**;
   - the sensor gives about 3.0 V at A0 (about 0 kPa);
   - the gate divider gives about 3 V with the beam received and under 0.4 V when blocked.
   The laser and receiver run from the Pi's 5 V, so this works without 24 V.
2. **Machine cord in, E-stop pressed, rocker on.** Measure the LRS output with no load and set
   **24.5 V** with V.ADJ.
3. **Release the E-stop.**
   - Rodent VIN ≈ 24.4 V and the Rodent LEDs light;
   - buck output 12.0 V;
   - nothing gets warm in the first minute: Rodent driver area, buck, modules.
4. **Test each load from the Pi** with Raspberry Pi OS's `pinctrl`: `pinctrl set 17 op dh` turns
   the pump on and `pinctrl set 17 op dl` turns it off. [Likely, Bookworm tool] Do the same for
   27, 22, 23 and 24, one at a time. Each output must drive only its own load.
4a. **Carry-height sensor** (it is powered from the Rodent, so the E-stop must be released):
   `pinctrl get 6` must read low with the slot clear and high with a card in it, and GPIO 6 must
   measure at least 2.5 V high (§6a). `python -m slabscan selftest` shows the same as its
   `carry sensor` line.
5. Now follow FIRMWARE.md from Step 1.
6. **After 10 minutes of motors holding:** the motor bodies may be warm but **below about 50 °C**
   (comfortable to hold a finger on). Hotter than that means the sense-resistor setting is wrong:
   power off (FIRMWARE.md step 0).

## 16. Open risks

1. **[Likely] Laser receiver output varies by maker.** The 2.2 kΩ pull-up and divider make both
   common output types safe, but measure before wiring.
2. **[Likely] Sensor output direction.** It is assumed to be 0.5 V at −100 kPa. Check about 4.5 V
   at atmosphere on first power-up.
3. **[Guessing] E-stop DC rating.** Two NC blocks in series are required anyway (§1.3); confirm
   ≥ 5 A at 24 V DC if the blocks list it, and do the monthly E-stop check.
4. **[Guessing] Head USB at about 4 m.** It works on paper. A cheap extension in a moving chain
   is the weakest cable in the machine. Watch for camera dropouts in the soak test.
5. **[Guessing] Whether Adafruit #5648 has a SIG pull-down.** Measured in §14 step 13 before the
   first power-up; add 10 kΩ if it reads open (§4). BUILD_GUIDE §13.4 ("unplug the Pi, the pump
   must stop") checks it again.
6. **[Guessing] Probe flag chatter** with `probe_hard_limit: true`: see §6 "Hysteresis".
7. **[Likely] The carry sensor's high level through the divider** may be only about 2.5 V with a
   10 kΩ on-board pull-up: measure it (§6a), add 2.2 kΩ at the board if low.
8. **[Certain] A dark carry sensor reads "OK to move".** A dead emitter, dirt or a cut GND is caught
   only at the next grip (§6a); until then it cannot see a stall. The run checks at every grip, so
   that window is at most one slab's moves.

**Resolved:** the BOM now lists Adafruit #5648 modules, bare microswitches, the 1/3/5 A fuses,
the mains box, a Class 2 laser and a two-block E-stop used on this page, and the 8-core's spare
core now carries the carry-height sensor (§6a). Both limit switches have printed mounts with
their lead paths in the CAD (§7). The CAD has printed hard
stops that keep both carriages on their rails (CONTRACT), so the old Z-rail margin issue is
closed.
