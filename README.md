# MotorStorm: Apocalypse sur PC, par recompilation statique

Portage natif Windows de **MotorStorm: Apocalypse** (PS3, BCES00484 v02.00) : le code PowerPC
du jeu est traduit en C++ avec [ps3recomp](https://github.com/sp00nznet/ps3recomp), puis
compilé avec un runtime qui remplace la console (Direct3D 12, son, manette, réseau local).

**Ce dépôt ne contient ni le jeu ni le firmware.** Il ne contient que notre travail : les
sources du port, le lanceur, les scripts et nos modifications de ps3recomp.
Il faut son propre disque du jeu et le firmware de sa propre console pour s'en servir.

## État (25 novembre 2026)

- Le jeu démarre, les menus fonctionnent, les courses vont au bout avec un rendu correct sur
  les deux circuits essayés (« Un pont vers nulle part », « Quai sous pression »).
- 30 images par seconde tenues (le plafond du jeu) sur un i7-10700F et une RTX 4070 SUPER.
- Rendu en 720p par défaut, vrai 1080p et 1440p possibles (`PORT_RES=1920x1080`).
- Son et musique en place. Les films sont remplacés par un clip court.
- Multijoueur en réseau local sans serveur, avec le mode LAN que le jeu contient déjà ;
  essayé à deux et trois instances sur une même machine, pas encore entre deux PC.
- Défaut connu : des carrés sombres autour des véhicules.

## Ce qu'il y a dans le dépôt

| Dossier | Contenu |
|---|---|
| [port/](port/) | le projet CMake du port : `main.cpp`, réponses aux bibliothèques de la console (`hle_overrides.cpp`), réseau (`net_hooks.cpp`), scripts de compilation et de lancement |
| [launcher/](launcher/) | `Lanceur.exe` (Tauri 2) : réglages, parties LAN, lancement du jeu depuis son dossier |
| [scripts/](scripts/) | traduction du jeu (`lift_title.py`), mesures, captures, outils de débogage ; chaque script dit ce qu'il fait dans son en-tête |
| [toolkit/](toolkit/) | nos modifications de ps3recomp : un diff à appliquer sur le commit noté dans `BASE.txt`, plus les fichiers ajoutés |

Ce qui n'y est pas, et n'y entrera pas : l'`EBOOT` déchiffré, le code traduit (`work/`), les
images SPU, les fichiers du jeu extraits ou modifiés, les fichiers du firmware, l'exe compilé.

## Ce qu'il faut pour reconstruire

- Windows 10 ou 11 64 bits, une carte Direct3D 12, un processeur AVX2 + FMA.
- Visual Studio avec clang-cl, CMake, Ninja, Python 3 ; Rust et WebView2 pour le lanceur.
- Le disque du jeu (BCES00484, v02.00), copié sur le PC.
- [RPCS3](https://rpcs3.net/) pour déchiffrer `EBOOT.BIN`, et le firmware PS3 (`libsre.prx`,
  `dev_flash`).

Les dossiers sont attendus côte à côte :

```
Recomp\
├── ps3recomp\     le toolkit, avec nos modifications
├── .venv\         l'environnement Python des outils
├── tools\rpcs3\   RPCS3 portable
└── MotorStorm\    ce dépôt
```

Les étapes, dans l'ordre :

1. **Le toolkit** : cloner ps3recomp, se placer sur le commit de
   [toolkit/BASE.txt](toolkit/BASE.txt), `git apply` de `toolkit\ps3recomp_local.diff`, puis
   copier `toolkit\new_files\` par-dessus.
2. **Le jeu** : déchiffrer `EBOOT.BIN` (`rpcs3.exe --decrypt`) et poser le résultat dans
   `game\BCES00484\`.
3. **La traduction** : `python scripts\lift_title.py BCES00484 --spu`, puis
   `python scripts\func_hooks.py`. La marche complète (firmware, modules SPU, ordre des
   étapes) est dans `.claude\skills\ps3-lift\SKILL.md`.
4. **La compilation** : `port\build.bat configure`, puis `port\build.bat` (une vingtaine de
   minutes pour une compilation complète).
5. **Le lancement** : `port\run.bat` (développement), ou le dossier du joueur avec le lanceur
   (`launcher\build.bat`, puis `scripts\deploy_game.ps1`).

Beaucoup de scripts et les fichiers `.bat` portent encore les chemins de la machine où le
projet est né (`I:\Projets\Recomp`, `F:\Jeux\PS3`, `E:\ms_perf`) : ils sont à adapter.

## Remerciements

- [ps3recomp](https://github.com/sp00nznet/ps3recomp) (Ned Heller / sp00nznet, MIT) : le
  toolkit de recompilation et son runtime.
- [motorstorm-apocalypse-pc](https://github.com/millennium-h4x0r/motorstorm-apocalypse-pc)
  (MIT) : un autre portage du même jeu, dont vient le lifter à registres locaux.
- [RPCS3](https://rpcs3.net/) : déchiffrement et référence de comportement.

Ce que nous leur avons repris est noté dans [toolkit/NOTICE.md](toolkit/NOTICE.md).

## Licence

Notre code est sous licence MIT ([LICENSE](LICENSE)). Les notes de travail du projet (journal,
docs par sujet) ne sont pas publiées : les commentaires du code qui renvoient à `docs\` ou à
`CLAUDE.md` pointent vers elles.

MotorStorm est une marque de Sony Interactive Entertainment. Ce projet n'a aucun lien avec
Sony ni avec Evolution Studios.
