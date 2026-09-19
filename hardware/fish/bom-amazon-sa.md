# Fish v1: what to buy, Amazon.sa

Prices as shown on 19 September 2026, delivering to Riyadh. Search terms are
the ones that found the item, so the listing can be found again when the
seller changes. The vehicle is a tethered OpenFish (TU Delft, CC BY 4.0,
https://doi.org/10.17605/OSF.IO/FB5VH) with our own electronics: a Pi Zero 2
W and camera in the head, control and video over Ethernet to the DGX Spark on
the surface.

| # | Item | Pick | SAR | Search on Amazon.sa | Why this one |
| --- | --- | --- | --- | --- | --- |
| 1 | Tail motor | 25GA-370 12 V 500 rpm metal gearmotor, 25 mm | 65 | `12V DC gear motor 25GA 370 500rpm` | OpenFish beats 5.5 Hz at top speed; 500 rpm is 8.3 Hz unloaded. Weaker than OpenFish's Pololu 25D HP; if it bogs under load the fallback is a 37GB-520 12 V 300 rpm |
| 2 | Motor driver | HiLetgo BTS7960 43 A H-bridge | 33 | `BTS7960 43A motor driver` | 5.5–27 V, PWM both directions, far more current than needed, current sense |
| 3 | Computer | Raspberry Pi Zero 2 W | 468 | `Raspberry Pi Zero 2 W` | smallest board that runs the camera and ROS 2 nodes; overpriced here, Jarir may be cheaper |
| 4 | Camera | Raspberry Pi Camera Module 3 Wide (official) | 276 | `Raspberry Pi Camera Module 3 Wide` | 120°, autofocus, 1080p50 |
| 5 | Camera cable | GeeekPi 15-pin to 22-pin FFC, 16 + 30 cm | 53 | `raspberry pi zero camera cable 22 pin` | the Zero's CSI connector is 22-pin; the camera ships with a 15-pin cable |
| 6 | Ethernet | Micro-USB to RJ45 adapter for Pi Zero | 21 | `micro usb ethernet adapter raspberry pi zero` | Wi-Fi does not pass through water; the tether is Ethernet |
| 7 | IMU | Adafruit BNO055 (ADA2472) | 222 | `BNO055 IMU` | on-chip fusion, gives orientation directly over I²C |
| 8 | 5 V for the Pi | LM2596S buck converter with display | 23 | `LM2596 buck converter 12V to 5V` | 12 V tether down to 5 V, 2 A |
| 9 | Surface power | 12 V 5 A 60 W adapter, 5.5 mm plug | 48 | `12V 5A DC power supply 5.5mm LED strip` | motor 2 A peak plus Pi; no battery in the fish |
| 10 | Tether, data | UGREEN Cat6 flat 15 m | 78 | `cat6 flat ethernet cable 15m` | flat cable drags less; two pairs unused |
| 11 | Tether, power | 15 m of 2 × 1.0 mm² flexible cable | ~25 | any electrical shop or SACO | taped to the Cat6 every 30 cm; Ethernet pairs are too thin for 2 A over 15 m |
| 12 | Tether seal | PG7 nylon cable glands, IP68, 10 pcs | 50 | `PG7 cable gland waterproof` | one for the head; 3–6.5 mm cable |
| 13 | Tail silicone | BBDINO Super Elastic mould silicone, 600 g, 1:1 | 116 | `liquid silicone rubber mold making 1kg` | about Shore A 15, what OpenFish specifies; 600 g casts the tail cover twice |
| 14 | Tail cables | 7-strand coated steel fishing wire, 0.5 mm, 100 m | 44 | `steel braided fishing line leader wire` | OpenFish drives the tail with two of these |
| 15 | Trim weights | adhesive wheel weights 5 g strips, 25 | 94 | `adhesive wheel balance weights 5g` | OpenFish trims to 1370 g with these |
| 16 | Thrust and mass | kitchen scale, 3 kg, 0.1 g | ~70 | `digital kitchen scale 0.1g 3kg` | every measurement the simulator needs |
| 17 | Gasket | cut from item 13 poured 1 mm thick in a printed tray | 0 | | OpenFish uses a nitrile sheet; Amazon.sa does not sell it |
| 18 | Sealant, epoxy, waterproof tape, M3 screws | | ~60 | SACO | |
| 19 | Printing | head halves, ribs, moulds, PETG at Sketchat | ~250 | sketchat.sa | PLA in the paper; PETG because the tank is warm |

**Total: about 2,000 SAR**, of which the Pi and camera are a third.

## Not on Amazon.sa

- Depth sensor (MS5837). Not needed in a tank with an overhead camera. AliExpress when the fish leaves the tank.
- Bearings and the motor shaft coupling. Sizes follow from our redesign of the head around the 25GA-370, so they are picked when that CAD exists.

## The design work this implies

OpenFish's head is built around a Pololu 25D motor, a 20:50 spur pair and a Huco right-angle gearbox. Ours drops the gears and the gearbox: the 25GA-370 turns the crank directly. So the head is redrawn, in build123d beside the nano, keeping OpenFish's tail, ribs and moulds unchanged. The Tunabot's files were never published; the OpenFish files were, which is why this is the fish.
