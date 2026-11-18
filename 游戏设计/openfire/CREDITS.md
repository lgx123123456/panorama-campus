# Credits

## Code
OpenFire game code © the project authors, released under the MIT License (see `LICENSE`).

## Engine
[Godot Engine](https://godotengine.org) 4.6 — MIT License.

## Kenney art assets (CC0 1.0 — public domain)
By **Kenney** — <https://kenney.nl> — licensed [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/).
No attribution is required for CC0, but credit is given gratefully.

| Pack | Used for | Location |
| --- | --- | --- |
| [Blaster Kit](https://kenney.nl/assets/blaster-kit) | Weapon & crate models | `assets/kenney/blaster-kit/`, `assets/models/weapons/` |
| [Blocky Characters](https://kenney.nl/assets/blocky-characters) | Player & bot models | `assets/kenney/blocky-characters/`, `assets/models/characters/` |
| [Prototype Textures](https://kenney.nl/assets/prototype-textures) | Level/greybox textures | `assets/kenney/prototype-textures/` |
| [Car Kit](https://kenney.nl/assets/car-kit) | Drivable vehicle models | `assets/kenney/car-kit/`, `assets/models/vehicles/` |
| [Sci-Fi Sounds](https://kenney.nl/assets/sci-fi-sounds) | Weapon fire, reload, hurt, death | `assets/audio/` |
| [Impact Sounds](https://kenney.nl/assets/impact-sounds) | Bullet impacts | `assets/audio/` |
| [Interface Sounds](https://kenney.nl/assets/interface-sounds) | UI clicks | `assets/audio/` |

A curated subset of the audio packs is committed under `assets/audio/` (the full
300+ file packs are not committed; re-download from kenney.nl if you want them).

The `assets/models/` folders contain the GLB files (with their `Textures/`) copied from the
Kenney packs into clean, space-free paths for engine import. The original packs are kept
under `assets/kenney/` for reference.

## Campus characters

[Zombie Apocalypse Kit by Quaternius](https://quaternius.com/packs/zombieapocalypsekit.html),
March 2024, [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).
The campus trial uses Matt, Sam, Shaun, Zombie Basic and Zombie Chubby, including their
original skeletons and animation clips. The imported copies omit weapon props and clips
unused by the trial. The campus palettes and clothing color assignments are local edits.
Source glTF files from [the asset mirror at db3df04](https://github.com/agentkaerf/FreeModels/tree/db3df04d1e4714298a09510b26fb6de6645138a2/Zombie%20Apocalypse%20Kit%20-%20March%202024)
were repacked as GLB under `assets/campus/characters/`.

The realistic campus trial uses the five project character samples and their
infected appearances, exported under `assets/campus/characters/realistic/`.
Its body motion retargets the same Quaternius clips to the campus skeletons.

## Campus free tour
- Rider walk and run reuse the campus retargeted Quaternius CC0 clips.
- [Scooter model and wheel roll clip](https://3dassets.dev/assets/car-park-and-road-vehicle-fleet-scooter-2e680ced) by 3D Assets, CC0 1.0.
- Turn-dependent motorcycle lean adapted from [Starter Kit Racing by Kenney](https://github.com/maawy-games/Godot-Starter-Kit-Racing), MIT. The notice is also in `assets/campus/tour/LICENSE-kenney-racing.txt`.

## Campus firearms and movement

[GodotFPS-Template by bukkbeek](https://github.com/bukkbeek/GodotFPS-Template),
commit `11619794d644e7933f87caa6099f3acc1f085f5d`, supplies
`resources/player/fps_demo_arms.glb`, including the rifle, shotgun, pistol,
first-person arms, firing and reload animations. The repository LICENSE states
MIT. Its README additionally prohibits reselling assets originating from the
project. Both original notices are preserved in `assets/campus/weapons/`.
The campus integration adds local materials, weapon handling and third-person
two-hand IK. Weapon sounds come from the existing Kenney CC0 packs.

The campus finale uses the `blaster-p` rotary blaster from
[Kenney Blaster Kit 2.1](https://kenney.nl/assets/blaster-kit), CC0 1.0 Universal.
The original model is retained under `assets/models/weapons/`. The local
`assets/campus/weapons/minigun_rotary.glb` separates the barrel assembly,
adds barrel copies and applies a darker material. The campus adaptation
reuses the existing FPS rig's two-hand animation and Kenney sound.

[Expresso Character Controller](https://github.com/expressobits/character-controller),
commit `ec8c43c3c46a610cdc9b4f96404e9149e7ff4100`, MIT, provided the movement
reference for acceleration, deceleration, air control and smooth crouching.
Its original license is `assets/campus/weapons/LICENSE-expressobits.txt`.
Jump buffering, overhead checks and the campus stair adaptation are local code.
