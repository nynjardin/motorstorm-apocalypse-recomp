// The launcher's page. The Rust side (src-tauri/src/main.rs) owns the settings and the game
// process; this page shows them and sends every change back (command "save").
const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const $ = (id) => document.getElementById(id);
let settings = null;
let running = [];
let playable = false;
let saveTimer = null;

// The page's text in its two languages (settings.lang: "en", the default, or "fr"). A key is
// used by an element of index.html through data-i18n (plain text), data-i18n-html (text with
// <em> / <b>), data-i18n-title or data-i18n-placeholder, or from this file through t(). The
// messages that come from the Rust side are translated there.
const TEXT = {
  en: {
    title: "MotorStorm: Apocalypse — Launcher",
    brand: "PC version — launcher",
    folder_title: "The game folder",
    open_folder: "Folder",
    open_save: "Save",
    open_save_tip: "recomp\\save: the game's save",
    open_log: "Log",
    open_log_tip: "recomp\\run.log: what the game wrote the last time it ran",
    player_title: "Player",
    pseudo: "Player name",
    pseudo_help: "3 to 16 characters: unaccented letters, digits, - or _. This is the name the other players see.",
    game_lang: "Game language",
    game_lang_auto: "Automatic (the language of Windows)",
    game_lang_help: "The language of the game's menus and voices. It applies the next time the game starts.",
    lan_title: "Local network",
    lan: "Multiplayer on the local network (no server)",
    net_ip: "Network card",
    net_ip_help: "Every PC must be on the same network. A virtual network (ZeroTier, Radmin VPN) = playing over the Internet.",
    peers: "Addresses of the other PCs <em>(optional)</em>",
    peers_example: "e.g. 192.168.1.20, 192.168.1.21",
    peers_help: "Only if the others' games do not show up in the game's search (a network without broadcast).",
    lan_hint: "In the game: open the multiplayer menu, then <b>host a private game</b> or <b>search for a game</b> to join. Firewall: UDP 3658 and 3659.",
    picture_title: "Picture",
    res: "Picture resolution",
    res_720: "1280 × 720 (HD, as on PS3)",
    res_help: "The size the game computes its picture at: the larger, the finer the picture (and the more work for the graphics card).",
    window: "Game window",
    window_size: "A window the size of the picture",
    window_full: "Full screen (borderless)",
    window_help: "In full screen the picture keeps its shape (16:9): black bars on the sides of a wider screen.",
    window_custom: "Window",
    fps30: "30 frames per second (as on PS3)",
    fps60: "Up to 60 frames per second <em>(experimental)</em>",
    trouble_title: "Troubleshooting",
    rsx_async: "Rendering on its own thread <em>(untick after a freeze or a picture defect)</em>",
    spu_async_pool: "SPU tasks in parallel <em>(untick after a freeze)</em>",
    geo_cache: "Geometry cache <em>(untick if objects are missing)</em>",
    game_log: "The game's debug messages in the log",
    local_test: "Two-player test on this PC <em>(two games, each with its own save; not for playing between PCs)</em>",
    extra: "More variables <em>(one per line: NAME=value)</em>",
    stop: "Stop the game",
    play: "▶ Play",
    play2: "▶ Player 2",
    playing: "The game is running…",
    automatic: "Automatic",
    playtime: (time, n) => `Play time: ${time} (${n} session${n > 1 ? "s" : ""})`,
    missing: "Something is missing in the game folder (see on the left).",
    starting: "The game is starting: the window takes a moment to appear, the title screen comes after about a minute.",
    starting2: (name) => `The second game is starting (player ${name}).`,
    ended: (game, time) => `Game ${game}ended after ${time}.`,
    stopped: (game, time, code) => `Game ${game}stopped (code ${code}) after ${time}.`,
  },
  fr: {
    title: "MotorStorm: Apocalypse — Lanceur",
    brand: "Version PC — lanceur",
    folder_title: "Le dossier du jeu",
    open_folder: "Dossier",
    open_save: "Sauvegarde",
    open_save_tip: "recomp\\save : la sauvegarde du jeu",
    open_log: "Journal",
    open_log_tip: "recomp\\run.log : ce que le jeu a écrit à son dernier lancement",
    player_title: "Joueur",
    pseudo: "Pseudo",
    pseudo_help: "3 à 16 caractères : lettres sans accent, chiffres, - ou _. C'est le nom que voient les autres joueurs.",
    game_lang: "Langue du jeu",
    game_lang_auto: "Automatique (la langue de Windows)",
    game_lang_help: "La langue des menus et des voix du jeu. Elle s'applique au prochain lancement du jeu.",
    lan_title: "Réseau local",
    lan: "Multijoueur en réseau local (sans serveur)",
    net_ip: "Carte réseau",
    net_ip_help: "Tous les PC doivent être sur le même réseau. Un réseau virtuel (ZeroTier, Radmin VPN) = jouer par Internet.",
    peers: "Adresses des autres PC <em>(facultatif)</em>",
    peers_example: "ex. 192.168.1.20, 192.168.1.21",
    peers_help: "Seulement si les parties des autres n'apparaissent pas dans « Trouver une partie » (réseau sans diffusion).",
    lan_hint: "En jeu : <b>Pour le fun → Multijoueur → Partie privée</b> pour héberger, <b>Trouver une partie</b> pour rejoindre. Pare-feu : UDP 3658 et 3659.",
    picture_title: "Image",
    res: "Résolution de l'image",
    res_720: "1280 × 720 (HD, comme sur PS3)",
    res_help: "La taille à laquelle le jeu calcule son image : plus elle est grande, plus l'image est fine (et plus la carte graphique travaille).",
    window: "Fenêtre du jeu",
    window_size: "Fenêtre à la taille de l'image",
    window_full: "Plein écran (sans bordure)",
    window_help: "En plein écran l'image garde ses proportions (16:9) : bandes noires sur les côtés d'un écran plus large.",
    window_custom: "Fenêtre",
    fps30: "30 images par seconde (comme sur PS3)",
    fps60: "Jusqu'à 60 images par seconde <em>(expérimental)</em>",
    trouble_title: "Dépannage",
    rsx_async: "Rendu sur un thread à part <em>(décocher en cas de gel ou de défaut d'image)</em>",
    spu_async_pool: "Tâches SPU en parallèle <em>(décocher en cas de gel)</em>",
    geo_cache: "Cache de géométrie <em>(décocher si des objets manquent)</em>",
    game_log: "Messages de débogage du jeu dans le journal",
    local_test: "Test à deux sur ce PC <em>(deux jeux, chacun sa sauvegarde ; pas pour jouer entre PC)</em>",
    extra: "Variables supplémentaires <em>(une par ligne : NOM=valeur)</em>",
    stop: "Arrêter le jeu",
    play: "▶ Jouer",
    play2: "▶ Joueur 2",
    playing: "Le jeu tourne…",
    automatic: "Automatique",
    playtime: (time, n) => `Temps de jeu : ${time} (${n} partie${n > 1 ? "s" : ""})`,
    missing: "Il manque quelque chose dans le dossier du jeu (voir à gauche).",
    starting: "Le jeu démarre : la fenêtre met un moment à s'afficher, l'écran titre arrive après environ une minute.",
    starting2: (name) => `Le deuxième jeu démarre (joueur ${name}).`,
    ended: (game, time) => `Jeu ${game}terminé après ${time}.`,
    stopped: (game, time, code) => `Jeu ${game}arrêté (code ${code}) après ${time}.`,
  },
};

function t(key, ...args) {
  const table = TEXT[settings && settings.lang === "fr" ? "fr" : "en"];
  const text = table[key] ?? TEXT.en[key] ?? key;
  return typeof text === "function" ? text(...args) : text;
}

// Puts the chosen language in every element that names a key. The strings of data-i18n-html
// are the constants of TEXT above, never something read from a file or typed by the player.
function showLanguage() {
  document.documentElement.lang = settings.lang === "fr" ? "fr" : "en";
  document.title = t("title");
  for (const e of document.querySelectorAll("[data-i18n]")) e.textContent = t(e.dataset.i18n);
  for (const e of document.querySelectorAll("[data-i18n-html]")) e.innerHTML = t(e.dataset.i18nHtml);
  for (const e of document.querySelectorAll("[data-i18n-title]")) e.title = t(e.dataset.i18nTitle);
  for (const e of document.querySelectorAll("[data-i18n-placeholder]")) e.placeholder = t(e.dataset.i18nPlaceholder);
  $("lang").value = settings.lang === "fr" ? "fr" : "en";
}

function message(text, error = false) {
  $("message").textContent = text || "";
  $("message").classList.toggle("error", error);
}

function duration(seconds) {
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60);
  return h ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`;
}

function showChecks(checks) {
  const list = $("checks");
  list.replaceChildren();
  for (const c of checks) {
    const li = document.createElement("li");
    li.className = c.ok ? "ok" : c.needed ? "missing" : "optional";
    li.textContent = c.name;
    if (!c.ok) {
      const small = document.createElement("small");
      small.textContent = c.detail;
      li.append(small);
    }
    list.append(li);
  }
}

function showAddresses(addresses, defaultIp) {
  const select = $("net-ip");
  select.replaceChildren();
  const auto = document.createElement("option");
  auto.value = "";
  auto.textContent = defaultIp ? `${t("automatic")} (${defaultIp})` : t("automatic");
  select.append(auto);
  const all = [...addresses];
  if (settings.net_ip && !all.includes(settings.net_ip)) all.push(settings.net_ip);
  for (const ip of all) {
    const o = document.createElement("option");
    o.value = ip;
    o.textContent = ip;
    select.append(o);
  }
  select.value = settings.net_ip;
}

function showButtons() {
  const one = running.includes(1), two = running.includes(2);
  $("play").disabled = !playable || one;
  $("play").textContent = one ? t("playing") : t("play");
  $("play2").hidden = !(settings.lan && settings.local_test);
  $("play2").disabled = !playable || two;
  $("stop").hidden = running.length === 0;
  $("lan-box").classList.toggle("off", !settings.lan || settings.local_test);
}

function showSettings() {
  $("pseudo").value = settings.pseudo;
  $("game-lang").value = settings.game_lang;
  $("lan").checked = settings.lan;
  $("peers").value = settings.peers;
  $("fps60").checked = settings.fps60;
  $("fps30").checked = !settings.fps60;
  for (const o of document.querySelectorAll("option[data-custom]")) o.remove();
  if (settings.window && ![...$("window").options].some((o) => o.value === settings.window)) {
    const o = document.createElement("option");      // a size written by hand in lanceur.json
    o.value = settings.window;
    o.dataset.custom = "1";
    o.textContent = `${t("window_custom")} ${settings.window.replace("x", " × ")}`;
    $("window").append(o);
  }
  $("window").value = settings.window;
  if (settings.res && ![...$("res").options].some((o) => o.value === settings.res)) {
    const o = document.createElement("option");      // a size written by hand in lanceur.json
    o.value = settings.res;
    o.dataset.custom = "1";
    o.textContent = settings.res.replace("x", " × ");
    $("res").append(o);
  }
  $("res").value = settings.res;
  $("rsx-async").checked = settings.rsx_async;
  $("spu-async-pool").checked = settings.spu_async_pool;
  $("geo-cache").checked = settings.geo_cache;
  $("game-log").checked = settings.game_log;
  $("local-test").checked = settings.local_test;
  $("extra").value = settings.extra;
  if (settings.local_test || settings.extra || !settings.rsx_async || !settings.spu_async_pool || !settings.geo_cache || settings.game_log)
    $("advanced").open = true;
  $("playtime").textContent = settings.sessions ? t("playtime", duration(settings.seconds), settings.sessions) : "";
}

async function refresh() {
  const s = await invoke("state");
  settings = s.settings;
  running = s.running;
  playable = s.playable;
  showLanguage();
  $("launcher-version").textContent = s.launcher_version;
  $("folder").textContent = s.folder;
  showChecks(s.checks);
  showSettings();
  showAddresses(s.addresses, s.default_ip);
  showButtons();
  message(playable ? "" : t("missing"), !playable);
}

function readPage() {
  settings.lang = $("lang").value;
  settings.pseudo = $("pseudo").value.trim();
  settings.game_lang = $("game-lang").value;
  settings.lan = $("lan").checked;
  settings.net_ip = $("net-ip").value;
  settings.peers = $("peers").value.trim();
  settings.fps60 = $("fps60").checked;
  settings.window = $("window").value;
  settings.res = $("res").value;
  settings.rsx_async = $("rsx-async").checked;
  settings.spu_async_pool = $("spu-async-pool").checked;
  settings.geo_cache = $("geo-cache").checked;
  settings.game_log = $("game-log").checked;
  settings.local_test = $("local-test").checked;
  settings.extra = $("extra").value;
}

async function saveNow() {
  clearTimeout(saveTimer);
  saveTimer = null;
  readPage();
  showButtons();
  try {
    await invoke("save", { settings });
    $("pseudo").classList.remove("invalid");
    if (playable) message("");
    return true;
  } catch (e) {
    // The Rust side starts the message about the name with the field's label in either language.
    $("pseudo").classList.toggle("invalid", /^(Player name|Pseudo)/.test(String(e)));
    message(String(e), true);
    return false;
  }
}

function saveSoon() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveNow, 400);
}

async function play(instance) {
  if (!(await saveNow())) return;
  try {
    await invoke("play", { instance });
    running = [...new Set([...running, instance])];
    showButtons();
    message(instance === 1 ? t("starting") : t("starting2", settings.pseudo.slice(0, 15) + "2"));
  } catch (e) {
    message(String(e), true);
  }
}

for (const id of ["pseudo", "peers", "extra"]) $(id).addEventListener("input", saveSoon);
for (const id of ["game-lang", "lan", "net-ip", "window", "res", "fps30", "fps60", "rsx-async", "spu-async-pool", "geo-cache", "game-log", "local-test"])
  $(id).addEventListener("change", saveNow);
// The language: saved like any setting, then the whole page is shown again (the Rust side
// answers in the new language too).
$("lang").addEventListener("change", async () => {
  if (await saveNow()) await refresh();
  else showLanguage();          // not saved (e.g. a name to correct): the page changes all the same
});
$("play").addEventListener("click", () => play(1));
$("play2").addEventListener("click", () => play(2));
$("stop").addEventListener("click", async () => {
  for (const instance of running) await invoke("stop", { instance }).catch((e) => message(String(e), true));
});
for (const b of document.querySelectorAll("[data-open]"))
  b.addEventListener("click", () => invoke("open", { what: b.dataset.open }).catch((e) => message(String(e), true)));

listen("partie", async (event) => {
  const { instance, seconds, code } = event.payload;
  await refresh();
  const game = instance > 1 ? instance + " " : "";
  const clean = code === 0 || code === null;
  message(clean ? t("ended", game, duration(seconds)) : t("stopped", game, duration(seconds), code), !clean);
});

document.addEventListener("contextmenu", (e) => e.preventDefault());
refresh().catch((e) => message(String(e), true));
