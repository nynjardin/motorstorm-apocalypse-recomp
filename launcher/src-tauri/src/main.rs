//! Lanceur MotorStorm: Apocalypse -- a portable launcher for the PC port.
//!
//! It sits at the root of the game folder, beside MotorStormApocalypse.exe and PS3_GAME, and
//! writes nothing outside that folder: its settings (recomp/lanceur.json), the web view's data
//! (recomp/.lanceur-webview) and what it hands to the game (recomp/settings.ini).
//!
//! The contract with the game (port/portable.cpp, docs/lanceur.md): the exe started without
//! arguments finds everything relative to itself; its settings are environment variables, taken
//! from its environment first, then from recomp/settings.ini (NAME=value lines), then from its
//! own defaults. The launcher writes that file (so a double click on the exe plays with the
//! same settings) and passes the same variables to the game it starts.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::net::{ToSocketAddrs, UdpSocket};
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{Emitter, Manager, State, WebviewUrl, WebviewWindowBuilder};

const GAME_EXE: &str = "MotorStormApocalypse.exe";
const DATA: &str = "recomp";
const VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Clone, Serialize, Deserialize)]
#[serde(default)]
struct Settings {
    /// The player's name on the network: 3-16 letters, digits, '-' or '_'.
    pseudo: String,
    /// The title's LAN mode (multiplayer without a server).
    lan: bool,
    /// The network card's address; empty = the one of the default route.
    net_ip: String,
    /// Addresses that also get the LAN search (a network without broadcast: VPN), comma separated.
    peers: String,
    /// Up to 60 FPS (the title's real-time clock, interval 1); false = 30 FPS.
    fps60: bool,
    /// The size the picture is rendered at: "" = 1280x720 (as on a PS3), "<w>x<h>" (PORT_RES).
    res: String,
    /// The game window: "" = the size of the picture, "<w>x<h>" (its inner size) or "fullscreen" (borderless).
    window: String,
    /// Two games on this PC (tests): each is its own loopback address.
    local_test: bool,
    rsx_async: bool,
    spu_async_pool: bool,
    geo_cache: bool,
    /// The title's own debug messages in the log.
    game_log: bool,
    /// More NAME=value lines, as they are.
    extra: String,
    seconds: u64,
    sessions: u32,
}

impl Default for Settings {
    fn default() -> Self {
        let user: String = std::env::var("USERNAME")
            .unwrap_or_default()
            .chars()
            .filter(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_')
            .take(16)
            .collect();
        Settings {
            pseudo: if user.len() >= 3 { user } else { "Pilote".into() },
            lan: true,
            net_ip: String::new(),
            peers: String::new(),
            fps60: false,
            res: String::new(),
            window: String::new(),
            local_test: false,
            rsx_async: true,
            spu_async_pool: true,
            geo_cache: true,
            game_log: false,
            extra: String::new(),
            seconds: 0,
            sessions: 0,
        }
    }
}

fn valid_pseudo(p: &str) -> bool {
    (3..=16).contains(&p.len()) && p.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
}

fn valid_ips(list: &str) -> bool {
    list.split(',').map(str::trim).filter(|s| !s.is_empty()).all(|s| s.parse::<std::net::Ipv4Addr>().is_ok())
}

impl Settings {
    fn load(folder: &Path) -> Settings {
        std::fs::read_to_string(folder.join(DATA).join("lanceur.json"))
            .ok()
            .and_then(|text| serde_json::from_str(text.trim_start_matches('\u{feff}')).ok())
            .unwrap_or_default()
    }

    fn save(&self, folder: &Path) -> Result<(), String> {
        let data = folder.join(DATA);
        std::fs::create_dir_all(&data).map_err(|e| e.to_string())?;
        let text = serde_json::to_string_pretty(self).expect("settings as JSON");
        std::fs::write(data.join("lanceur.json"), text).map_err(|e| e.to_string())?;
        let mut ini = String::from(
            "# Written by Lanceur.exe: change the settings in the launcher, this file is rewritten.\r\n\
             # NAME=value lines, read by MotorStormApocalypse.exe started without arguments.\r\n",
        );
        for (name, value) in self.variables(1) {
            ini.push_str(&format!("{name}={value}\r\n"));
        }
        std::fs::write(data.join("settings.ini"), ini).map_err(|e| e.to_string())
    }

    fn check(&self) -> Result<(), String> {
        if !valid_pseudo(&self.pseudo) {
            return Err("Pseudo : 3 à 16 caractères, lettres sans accent, chiffres, - ou _.".into());
        }
        if !valid_ips(&self.net_ip) || !valid_ips(&self.peers) {
            return Err("Adresse réseau invalide (attendu : a.b.c.d).".into());
        }
        let size_ok = |s: &str| {
            s.split_once('x').is_some_and(|(w, h)| {
                w.parse::<u32>().is_ok_and(|w| (320..=16384).contains(&w)) && h.parse::<u32>().is_ok_and(|h| (180..=16384).contains(&h))
            })
        };
        if !(self.res.is_empty() || size_ok(&self.res)) {
            return Err(format!("Résolution inattendue : {}", self.res));
        }
        if !(self.window.is_empty() || self.window == "fullscreen" || size_ok(&self.window)) {
            return Err(format!("Taille de fenêtre inattendue : {}", self.window));
        }
        Ok(())
    }

    /// What the game is told, for that instance (1 = the player's game, 2 = the second game
    /// of a test on one PC).
    fn variables(&self, instance: u32) -> Vec<(String, String)> {
        let mut v: Vec<(String, String)> = Vec::new();
        let mut set = |name: &str, value: &str| v.push((name.to_string(), value.to_string()));
        let pseudo = if instance >= 2 {
            let base: String = self.pseudo.chars().take(15).collect();
            format!("{base}{instance}")
        } else {
            self.pseudo.clone()
        };
        set("PS3_NP_ONLINE_ID", &pseudo);
        if self.lan {
            set("PORT_NET_LAN", "1");
            if self.local_test {
                set("PORT_LAN_LOCAL", "1");
            } else {
                if !self.net_ip.trim().is_empty() {
                    set("PS3_NET_IP", self.net_ip.trim());
                }
                if !self.peers.trim().is_empty() {
                    set("PS3_NET_PEERS", &self.peers.replace(' ', ""));
                }
            }
        }
        if instance >= 2 {
            set("PORT_INSTANCE", &instance.to_string());
        }
        if self.fps60 {
            set("PORT_SIM_RT", "1");
            set("PORT_SIM_INTERVAL", "1");
        }
        if !self.res.is_empty() {
            set("PORT_RES", &self.res);
        }
        if !self.window.is_empty() {
            set("PORT_WINDOW", &self.window);
        }
        if !self.rsx_async {
            set("RSX_ASYNC", "0");
        }
        if !self.spu_async_pool {
            set("SPU_ASYNC_POOL", "0");
        }
        if !self.geo_cache {
            set("GEO_CACHE", "0");
        }
        if self.game_log {
            set("PORT_GAME_LOG", "1");
        }
        for line in self.extra.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            if let Some((name, value)) = line.split_once('=') {
                let name = name.trim();
                if !name.is_empty() && name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') {
                    set(name, value.trim());
                }
            }
        }
        v
    }
}

struct Launcher {
    folder: PathBuf,
    settings: Mutex<Settings>,
    /// Instance -> its running game, started from here.
    games: Mutex<HashMap<u32, Child>>,
}

#[derive(Serialize)]
struct Check {
    ok: bool,
    /// A missing optional piece does not prevent playing.
    needed: bool,
    name: &'static str,
    detail: String,
}

#[derive(Serialize)]
struct LauncherState {
    folder: String,
    launcher_version: &'static str,
    checks: Vec<Check>,
    playable: bool,
    settings: Settings,
    /// This PC's IPv4 addresses; default_ip is the one of the default route.
    addresses: Vec<String>,
    default_ip: String,
    running: Vec<u32>,
}

#[derive(Clone, Serialize)]
struct SessionEnd {
    instance: u32,
    seconds: u64,
    code: Option<i32>,
}

/// The address of the card of the default route. Nothing is sent: connecting a UDP socket
/// only picks a route.
fn default_ip() -> String {
    UdpSocket::bind("0.0.0.0:0")
        .and_then(|s| s.connect("8.8.8.8:53").and_then(|_| s.local_addr()))
        .map(|a| a.ip().to_string())
        .unwrap_or_default()
}

fn addresses() -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    if let Ok(name) = std::env::var("COMPUTERNAME") {
        if let Ok(list) = (name.as_str(), 0u16).to_socket_addrs() {
            for a in list {
                if a.is_ipv4() && !a.ip().is_loopback() {
                    let ip = a.ip().to_string();
                    if !out.contains(&ip) {
                        out.push(ip);
                    }
                }
            }
        }
    }
    let d = default_ip();
    if !d.is_empty() && !out.contains(&d) {
        out.insert(0, d);
    }
    out
}

fn checks(folder: &Path) -> Vec<Check> {
    let data = folder.join(DATA);
    let has = |p: PathBuf| p.exists();
    let mut list = Vec::new();
    let mut add = |ok: bool, needed: bool, name: &'static str, missing: &str| {
        list.push(Check { ok, needed, name, detail: if ok { String::new() } else { missing.to_string() } })
    };
    add(
        has(folder.join("PS3_GAME").join("USRDIR").join("ms3.psarc")),
        true,
        "Le jeu (PS3_GAME)",
        "Le lanceur doit être à la racine du dossier du jeu, à côté de PS3_GAME.",
    );
    add(has(folder.join(GAME_EXE)), true, GAME_EXE, "À poser à côté du lanceur.");
    add(
        has(data.join("EBOOT.elf")),
        true,
        "recomp\\EBOOT.elf",
        "L'exécutable du jeu déchiffré : rpcs3.exe --decrypt PS3_GAME\\USRDIR\\EBOOT.BIN, puis le copier ici.",
    );
    add(
        has(data.join("psarc_patches.bin")),
        false,
        "recomp\\psarc_patches.bin",
        "Sans lui : « Trouver une partie » reste grisé, retour au menu après une course en réseau.",
    );
    add(
        has(data.join("dev_flash")),
        false,
        "recomp\\dev_flash",
        "Fichiers du firmware (dev_flash de RPCS3) : sans eux, pas de musique MP3.",
    );
    add(has(data.join("libsre_image.bin")), false, "recomp\\libsre_image.bin", "Optionnel.");
    list
}

#[tauri::command]
fn state(launcher: State<Launcher>) -> LauncherState {
    let checks = checks(&launcher.folder);
    let mut running: Vec<u32> = launcher.games.lock().unwrap().keys().copied().collect();
    running.sort();
    LauncherState {
        playable: checks.iter().all(|c| c.ok || !c.needed),
        checks,
        folder: launcher.folder.display().to_string(),
        launcher_version: VERSION,
        settings: launcher.settings.lock().unwrap().clone(),
        addresses: addresses(),
        default_ip: default_ip(),
        running,
    }
}

/// Keeps the page's settings (the play time stays the launcher's).
#[tauri::command]
fn save(launcher: State<Launcher>, settings: Settings) -> Result<(), String> {
    settings.check()?;
    let mut current = launcher.settings.lock().unwrap();
    let (seconds, sessions) = (current.seconds, current.sessions);
    *current = Settings { seconds, sessions, ..settings };
    if launcher.folder.join(DATA).exists() {
        current.save(&launcher.folder)?;
    }
    Ok(())
}

/// Starts the game (instance 1) or the second game of a test on this PC (instance 2). When it
/// ends, a "partie" event tells the page.
#[tauri::command]
fn play(app: tauri::AppHandle, launcher: State<Launcher>, instance: u32) -> Result<(), String> {
    if let Some(c) = checks(&launcher.folder).iter().find(|c| c.needed && !c.ok) {
        return Err(format!("{} : {}", c.name, c.detail));
    }
    let settings = launcher.settings.lock().unwrap().clone();
    settings.check()?;
    if instance >= 2 && !(settings.lan && settings.local_test) {
        return Err("Le deuxième jeu sert au test à deux sur ce PC (à cocher dans Dépannage).".into());
    }
    if launcher.games.lock().unwrap().contains_key(&instance) {
        return Err("Ce jeu tourne déjà.".into());
    }
    settings.save(&launcher.folder)?;
    // The game's log: its stdout and stderr, as port\run.bat's redirection. Opened here (shared:
    // it can be read while the game runs) and handed over; the previous one is kept once.
    let data = launcher.folder.join(DATA);
    let stem = if instance >= 2 { format!("run_p{instance}") } else { "run".to_string() };
    let log_path = data.join(format!("{stem}.log"));
    let _ = std::fs::rename(&log_path, data.join(format!("{stem}.prev.log")));
    let log = std::fs::File::create(&log_path).map_err(|e| format!("{} : {e}", log_path.display()))?;
    let log_err = log.try_clone().map_err(|e| e.to_string())?;
    let mut command = Command::new(launcher.folder.join(GAME_EXE));
    command
        .current_dir(&launcher.folder)
        .envs(settings.variables(instance))
        .stdin(std::process::Stdio::null())
        .stdout(log)
        .stderr(log_err);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: the game logs to recomp\run.log
    }
    let child = command.spawn().map_err(|e| format!("{GAME_EXE} : {e}"))?;
    launcher.games.lock().unwrap().insert(instance, child);
    std::thread::spawn(move || {
        let clock = std::time::Instant::now();
        let launcher = app.state::<Launcher>();
        let code = loop {
            std::thread::sleep(std::time::Duration::from_millis(500));
            let mut games = launcher.games.lock().unwrap();
            let Some(child) = games.get_mut(&instance) else { break None };
            match child.try_wait() {
                Ok(None) => continue,
                Ok(Some(status)) => {
                    games.remove(&instance);
                    break status.code();
                }
                Err(_) => {
                    games.remove(&instance);
                    break None;
                }
            }
        };
        let seconds = clock.elapsed().as_secs();
        if instance == 1 {
            let mut settings = launcher.settings.lock().unwrap();
            settings.seconds += seconds;
            settings.sessions += 1;
            let _ = settings.save(&launcher.folder);
        }
        let _ = app.emit("partie", SessionEnd { instance, seconds, code });
    });
    Ok(())
}

/// Stops a game started from here (a frozen game: nothing else of the PC is touched).
#[tauri::command]
fn stop(launcher: State<Launcher>, instance: u32) -> Result<(), String> {
    match launcher.games.lock().unwrap().get_mut(&instance) {
        Some(child) => child.kill().map_err(|e| e.to_string()),
        None => Ok(()),
    }
}

/// Shows a place of the game folder: "dossier", "sauvegarde", "journal".
#[tauri::command]
fn open(launcher: State<Launcher>, what: String) -> Result<(), String> {
    let data = launcher.folder.join(DATA);
    let (program, path) = match what.as_str() {
        "dossier" => ("explorer", launcher.folder.clone()),
        "sauvegarde" => {
            let save = data.join("save");
            std::fs::create_dir_all(&save).map_err(|e| e.to_string())?;
            ("explorer", save)
        }
        "journal" => {
            let log = data.join("run.log");
            if !log.exists() {
                return Err("Pas encore de journal : le jeu n'a pas été lancé d'ici.".into());
            }
            ("notepad", log)
        }
        _ => return Err(format!("Lieu inconnu : {what}")),
    };
    Command::new(program).arg(path).spawn().map(|_| ()).map_err(|e| e.to_string())
}

fn main() {
    let folder = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from("."));
    // The web view's data beside the game (portable); in a folder that is not a game's, in the
    // temporary directory, so that a misplaced launcher leaves nothing behind.
    let webview = if folder.join("PS3_GAME").exists() || folder.join(DATA).exists() {
        folder.join(DATA).join(".lanceur-webview")
    } else {
        std::env::temp_dir().join("lanceur-motorstorm-webview")
    };
    let launcher = Launcher {
        settings: Mutex::new(Settings::load(&folder)),
        games: Mutex::new(HashMap::new()),
        folder,
    };
    tauri::Builder::default()
        .manage(launcher)
        .invoke_handler(tauri::generate_handler![state, save, play, stop, open])
        .setup(move |app| {
            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("MotorStorm: Apocalypse — Lanceur")
                .inner_size(900.0, 660.0)
                .min_inner_size(760.0, 520.0)
                .data_directory(webview)
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("the launcher's window");
}
