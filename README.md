<p align="center">
  <img src="assets/logo.png" alt="MotorStorm: Apocalypse" width="512">
</p>

# MotorStorm: Apocalypse on PC, by static recompilation

A native Windows port of **MotorStorm: Apocalypse** (PS3, BCES00484 v02.00, and its 1.06 update). The
game's PowerPC code is translated to C++ with [ps3recomp](https://github.com/sp00nznet/ps3recomp),
then compiled with a runtime that stands in for the console (Direct3D 12, sound, controller, local
network).

**This repository contains neither the game nor the firmware.** It only holds our own work: the
port's sources, the launcher, the scripts and our changes to ps3recomp. You need your own disc of
the game and the firmware of your own console to use it.

## Status (28 November 2026)

- The game boots, the menus work, and races run to the end with a correct picture on the two
  tracks tried so far (the bridge and the pier).
- **The 1.06 update is the version the project is moving to** (more circuits and modes, "Alcatraz",
  special events). It is a second translation of the game (the update's executable is a different
  build, not a patch of the disc's), built with `PORT_V106=1`; it runs at the same speed as the disc
  version, and the local-network multiplayer works on it (tried with two instances on one machine).
  The disc-only build stays in the tree for comparisons.
- A steady 30 frames per second (the game's own cap) on an i7-10700F and an RTX 4070 SUPER.
- The lens flares are dimmed (they were far too bright): `FLARE_SCALE`, 0.2 by default (toolkit
  patch #77).
- Renders at 720p by default; true 1080p and 1440p are available (`PORT_RES=1920x1080`).
- Sound and music work.
- The game's movies play, picture and sound, when FFmpeg's DLLs are beside the exe (see
  "Movies, and a smaller copy of the game"); without them every movie is a short clip.
- Multiplayer on a local network with no server, using the LAN mode the game already contains;
  played between two PCs, and tried with up to four instances on one machine.
- The dark squares that used to surround the vehicles at the start of a race are gone: each vehicle's
  contact shadow is a 3D texture that the renderer sampled as a flat one (toolkit patch #67).
- Known defect: in the game's photo mode, the "Preview" button does nothing (the same on the disc
  build).

## What is in the repository

| Folder | Contents |
|---|---|
| [port/](port/) | the port's CMake project: `main.cpp`, answers to the console's libraries (`hle_overrides.cpp`), network (`net_hooks.cpp`), build and run scripts |
| [launcher/](launcher/) | `Launcher.exe` (Tauri 2): settings, LAN games, starting the game from its own folder |
| [scripts/](scripts/) | translating the game (`lift_title.py`), measurements, captures, debugging tools; each script says what it does in its header |
| [toolkit/](toolkit/) | our changes to ps3recomp: a diff to apply on the commit named in `BASE.txt`, plus the files we added |

What is not here, and never will be: the decrypted `EBOOT`, the translated code (`work/`), the
SPU images, extracted or modified game files, firmware files, the compiled exe.

## What you need to rebuild it

- Windows 10 or 11, 64-bit, a Direct3D 12 graphics card, a CPU with AVX2 and FMA.
- Visual Studio with clang-cl, CMake, Ninja, Python 3; Rust and WebView2 for the launcher.
- The game disc (BCES00484, v02.00), copied to the PC.
- [RPCS3](https://rpcs3.net/) to decrypt `EBOOT.BIN`, and the PS3 firmware (`libsre.prx`,
  `dev_flash`).

The folders are expected side by side:

```
Recomp\
├── ps3recomp\     the toolkit, with our changes
├── .venv\         the Python environment of the tools
├── tools\rpcs3\   RPCS3 portable
└── MotorStorm\    this repository
```

The steps, in order:

1. **The toolkit**: clone ps3recomp, check out the commit named in
   [toolkit/BASE.txt](toolkit/BASE.txt), `git apply` `toolkit\ps3recomp_local.diff`, then copy
   `toolkit\new_files\` over it.
2. **The game**: decrypt `EBOOT.BIN` (`rpcs3.exe --decrypt`) and put the result in
   `game\BCES00484\`.
3. **The translation**: `python scripts\lift_title.py BCES00484 --spu`, then
   `python scripts\func_hooks.py`. The full procedure (firmware, SPU modules, order of the
   steps) is in `.claude\skills\ps3-lift\SKILL.md`.
4. **The build**: `port\build.bat configure`, then `port\build.bat` (about twenty minutes for a
   full build).
5. **Running it**: `port\run.bat` (development), or the player's folder with the launcher
   (`launcher\build.bat`, then `scripts\deploy_game.ps1`).

**The 1.06 update build** (the one the launcher and `scripts\deploy_game.ps1` now put in the player's
folder) needs, besides the above:

- the six update packages of the game (`DATA000-005.PKG`, in the disc's `INSDIR`), installed once
  with RPCS3, which gives `EBOOT.BIN` (1.06) and `ms3patchv0101..0106.psarc`;
- its own translation: decrypt that `EBOOT.BIN` into `game\BCES00484_106\`, then
  `python scripts\lift_title.py BCES00484_106 --spu`, `MS_TITLE=BCES00484_106 python
  scripts\func_hooks.py`, and the SPU job modules chain of `scripts\jobmods_v106.py`;
- `scripts\psarc_patch.py --v106 --edits port\psarc_edits_106.json` for the menu changes;
- `PORT_V106=1 port\build.bat configure`, then `PORT_V106=1 port\build.bat` (own build tree, the
  profile-guided build of the disc is reused for the shared code), and `PORT_V106=1 port\run.bat`
  (`port\run_lan_106.bat` for multiplayer).

The addresses and structure offsets that differ from the disc build are in `port\title_addrs.h`.
Many scripts and the `.bat` files still carry the paths of the machine the project was born on
(`I:\Projets\Recomp`, `F:\Jeux\PS3`, `E:\ms_perf`): adapt them to yours.

## Movies, and a smaller copy of the game

**Playing the movies.** The game decodes its movies (XVID picture, AC-3 sound) through the
console's decoders; the port hands that work to FFmpeg, loaded at run time. Get an LGPL "shared"
build of FFmpeg 8 (for instance from [BtbN's builds](https://github.com/BtbN/FFmpeg-Builds)),
give its `include` folder to the build (`port\build.bat` says where it looks) and put
`avcodec-62.dll`, `avutil-60.dll` and `swresample-6.dll` beside the game's exe. FFmpeg is not part
of this repository. `PORT_PLAY_VIDEOS=0` goes back to the short clip; START skips a movie.

**Why the game is so big.** Of the ~21 GB of the disc, 16 GB are the folder
`PS3_GAME\USRDIR\ui\video`: 56 movies, each in three variants (`_60`, `_50`, `_3d`) at 13 to
20 Mbit/s. The port only ever reads the `_60` one.

**Making it smaller**, in three steps. You need `ffmpeg.exe` (same FFmpeg build) and a graphics
card with an H.264 encoder (NVIDIA by default: `--encoder` picks another one).

1. Re-encode the 56 `_60` movies to H.264 (about six minutes; 5.6 GB become 2.8 GB):

   ```
   python scripts\video_convert.py "<game>\PS3_GAME\USRDIR\ui\video" "<game>\recomp\video" --ffmpeg <path to ffmpeg.exe>
   ```

   Only the picture is re-encoded. Each result is an AVI of the same structure as the original:
   the sound tracks (up to nine languages), the subtitles and the chunk order are copied as they
   are, which is why the script writes the file itself instead of letting FFmpeg do it. `--cq`
   sets the quality (default 24, lower = bigger and closer to the original).
2. Check that the game plays them: the port uses `<game>\recomp\video\<name>.avi` instead of the
   disc's file whenever it exists (the log says `[port] video: ... -> /dev_bdvd/recomp/video/...`).
   `PORT_VIDEO_CONVERTED=0` ignores them.
3. Move `PS3_GAME\USRDIR\ui\video` out of the game folder, to a backup you keep: the game no
   longer needs it. The folder then weighs about 8.6 GB instead of 24.

`scripts\slim_copy.ps1 -Out <new folder>` does the same for a second copy (another PC of a LAN
game): it copies the game folder without `ui\video` and adds the re-encoded movies, leaving the
source untouched. `scripts\vfs_link_copy.ps1` builds such a copy out of links, in a second, to
try the result before moving anything.

Keep the original movies somewhere: the re-encoded ones are a lossy copy, and a later, better
conversion can only start from the originals.

## Credits

- [ps3recomp](https://github.com/sp00nznet/ps3recomp) (Ned Heller / sp00nznet, MIT): the
  recompilation toolkit and its runtime.
- [motorstorm-apocalypse-pc](https://github.com/millennium-h4x0r/motorstorm-apocalypse-pc)
  (MIT): another port of the same game, where the local-register lifter comes from.
- [RPCS3](https://rpcs3.net/): decryption and behaviour reference.

What we took from them is listed in [toolkit/NOTICE.md](toolkit/NOTICE.md).

## License

Our code is under the MIT License ([LICENSE](LICENSE)). The project's working notes (journal,
per-topic docs) are not published: code comments that point to `docs\` or `CLAUDE.md` refer to
them.

MotorStorm and the MotorStorm: Apocalypse logo are trademarks of Sony Interactive Entertainment;
the logo is shown here only to identify the game and is not covered by the MIT License. This
project is not affiliated with Sony or Evolution Studios.
