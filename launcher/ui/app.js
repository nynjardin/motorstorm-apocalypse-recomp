// The launcher's page. The Rust side (src-tauri/src/main.rs) owns the settings and the game
// process; this page shows them and sends every change back (command "save").
const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const $ = (id) => document.getElementById(id);
let settings = null;
let running = [];
let playable = false;
let checks = [];
let saveTimer = null;

// The page's text in its two languages (settings.lang: "en", the default, or "fr"). A key is
// used by an element of index.html through data-i18n (plain text), data-i18n-html (text with
// <em> / <b>), data-i18n-title or data-i18n-placeholder, or from this file through t(). The
// messages that come from the Rust side are translated there. The Dev settings carry their own
// two texts (DEV below).
const TEXT = {
  en: {
    title: "MotorStorm: Apocalypse — Launcher",
    brand: "PC version — launcher",
    nav_player: "Player",
    nav_multi: "Multiplayer",
    nav_display: "Display",
    nav_files: "Files",
    nav_dev: "Dev",
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
    lan_title: "Multiplayer",
    lan: "Multiplayer on the local network (no server)",
    net_ip: "Network card",
    net_ip_help: "Every PC must be on the same network. A virtual network (ZeroTier, Radmin VPN) = playing over the Internet.",
    peers: "Addresses of the other PCs <em>(optional)</em>",
    peers_example: "e.g. 192.168.1.20, 192.168.1.21",
    peers_help: "Only if the others' games do not show up in the game's search (a network without broadcast).",
    lan_hint: "In the game: open the multiplayer menu, then <b>host a private game</b> or <b>search for a game</b> to join. Firewall: UDP 3658 and 3659.",
    local_test_note: "The two-player test on this PC is on (Dev section): the card and the addresses above are not used.",
    picture_title: "Display",
    res: "Picture resolution",
    res_720: "1280 × 720 (HD, as on PS3)",
    res_help: "The size the game computes its picture at: the larger, the finer the picture (and the more work for the graphics card).",
    window: "Game window",
    window_size: "A window the size of the picture",
    window_full: "Full screen (borderless)",
    window_help: "In full screen the picture keeps its shape (16:9): black bars on the sides of a wider screen.",
    window_custom: "Window",
    fps_title: "Frame rate",
    fps30: "30 frames per second (as on PS3)",
    fps60: "Up to 60 frames per second <em>(experimental)</em>",
    dev_title: "Dev",
    dev_lead: "Settings to find the cause of a problem or to measure. Leave them as they are to play: each one shows its default, and a changed one is marked.",
    dev_cat_more: "More variables",
    extra: "More variables <em>(one per line: NAME=value)</em>",
    extra_help: "They come last: a variable written here wins over the same one above.",
    dev_reset: "Put every Dev setting back to its default",
    dev_changed: "changed",
    dev_default: "default",
    dev_badge_tip: (n) => `${n} Dev setting${n > 1 ? "s" : ""} not at the default`,
    files_bad: (n) => `⚠ ${n} missing file${n > 1 ? "s" : ""}`,
    files_warn: (n) => `! ${n} optional file${n > 1 ? "s" : ""} missing`,
    files_tip: "Click to see what is wrong",
    stop: "Stop the game",
    play: "▶ Play",
    play2: "▶ Player 2",
    playing: "The game is running…",
    automatic: "Automatic",
    playtime: (time, n) => `Play time: ${time} (${n} session${n > 1 ? "s" : ""})`,
    missing: "Something is missing in the game folder: see the Files section.",
    starting: "The game is starting: the window takes a moment to appear, the title screen comes after about a minute.",
    starting2: (name) => `The second game is starting (player ${name}).`,
    ended: (game, time) => `Game ${game}ended after ${time}.`,
    stopped: (game, time, code) => `Game ${game}stopped (code ${code}) after ${time}.`,
  },
  fr: {
    title: "MotorStorm: Apocalypse — Lanceur",
    brand: "Version PC — lanceur",
    nav_player: "Joueur",
    nav_multi: "Multijoueur",
    nav_display: "Affichage",
    nav_files: "Fichiers",
    nav_dev: "Dev",
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
    lan_title: "Multijoueur",
    lan: "Multijoueur en réseau local (sans serveur)",
    net_ip: "Carte réseau",
    net_ip_help: "Tous les PC doivent être sur le même réseau. Un réseau virtuel (ZeroTier, Radmin VPN) = jouer par Internet.",
    peers: "Adresses des autres PC <em>(facultatif)</em>",
    peers_example: "ex. 192.168.1.20, 192.168.1.21",
    peers_help: "Seulement si les parties des autres n'apparaissent pas dans « Trouver une partie » (réseau sans diffusion).",
    lan_hint: "En jeu : <b>Pour le fun → Multijoueur → Partie privée</b> pour héberger, <b>Trouver une partie</b> pour rejoindre. Pare-feu : UDP 3658 et 3659.",
    local_test_note: "Le test à deux sur ce PC est activé (section Dev) : la carte et les adresses ci-dessus ne servent pas.",
    picture_title: "Affichage",
    res: "Résolution de l'image",
    res_720: "1280 × 720 (HD, comme sur PS3)",
    res_help: "La taille à laquelle le jeu calcule son image : plus elle est grande, plus l'image est fine (et plus la carte graphique travaille).",
    window: "Fenêtre du jeu",
    window_size: "Fenêtre à la taille de l'image",
    window_full: "Plein écran (sans bordure)",
    window_help: "En plein écran l'image garde ses proportions (16:9) : bandes noires sur les côtés d'un écran plus large.",
    window_custom: "Fenêtre",
    fps_title: "Images par seconde",
    fps30: "30 images par seconde (comme sur PS3)",
    fps60: "Jusqu'à 60 images par seconde <em>(expérimental)</em>",
    dev_title: "Dev",
    dev_lead: "Des réglages pour trouver la cause d'un problème ou pour mesurer. Pour jouer, les laisser tels quels : chacun montre sa valeur par défaut, et un réglage changé est signalé.",
    dev_cat_more: "Variables supplémentaires",
    extra: "Variables supplémentaires <em>(une par ligne : NOM=valeur)</em>",
    extra_help: "Elles passent en dernier : une variable écrite ici l'emporte sur la même plus haut.",
    dev_reset: "Remettre tous les réglages Dev par défaut",
    dev_changed: "changé",
    dev_default: "par défaut",
    dev_badge_tip: (n) => `${n} réglage${n > 1 ? "s" : ""} Dev pas à sa valeur par défaut`,
    files_bad: (n) => `⚠ ${n} fichier${n > 1 ? "s" : ""} manquant${n > 1 ? "s" : ""}`,
    files_warn: (n) => `! ${n} fichier${n > 1 ? "s" : ""} facultatif${n > 1 ? "s" : ""} manquant${n > 1 ? "s" : ""}`,
    files_tip: "Cliquer pour voir ce qui ne va pas",
    stop: "Arrêter le jeu",
    play: "▶ Jouer",
    play2: "▶ Joueur 2",
    playing: "Le jeu tourne…",
    automatic: "Automatique",
    playtime: (time, n) => `Temps de jeu : ${time} (${n} partie${n > 1 ? "s" : ""})`,
    missing: "Il manque quelque chose dans le dossier du jeu : voir la section Fichiers.",
    starting: "Le jeu démarre : la fenêtre met un moment à s'afficher, l'écran titre arrive après environ une minute.",
    starting2: (name) => `Le deuxième jeu démarre (joueur ${name}).`,
    ended: (game, time) => `Jeu ${game}terminé après ${time}.`,
    stopped: (game, time, code) => `Jeu ${game}arrêté (code ${code}) après ${time}.`,
  },
};

// The Dev section: the game's variables worth changing by hand, by category. Every one of them
// is a variable of the game (port\run.bat and port\portable.cpp say what they do; the toolkit
// patches in docs\toolkit-patches.md). settings.dev holds only the ones that are NOT at their
// default ({NAME: value}): a setting back at its default is removed, so the game's own default
// applies.
//   toggle: on = the value when ticked, off = when unticked (null = the variable is not set);
//           def = ticked or not by default.
//   choice: options [value, en, fr]; "" = the default (not set).
//   setting: a launcher setting of its own (settings[key], a boolean), not a variable.
const DEV = [
  {
    en: "Freezes", fr: "Gels",
    items: [
      { env: "RSX_ASYNC", type: "toggle", def: true, on: null, off: "0",
        en: ["Rendering on its own thread", "+10 to 15 % frames per second. Untick after a freeze or a picture defect."],
        fr: ["Rendu sur un thread à part", "+10 à 15 % d'images par seconde. Décocher en cas de gel ou de défaut d'image."] },
      { env: "SPU_ASYNC_POOL", type: "toggle", def: true, on: null, off: "0",
        en: ["SPU tasks on reused threads", "The game's SPU tasks run on threads kept from one task to the next. Untick after a freeze (the first thing to try)."],
        fr: ["Tâches SPU sur des threads réutilisés", "Les tâches SPU du jeu tournent sur des threads gardés d'une tâche à l'autre. Décocher en cas de gel (la première chose à essayer)."] },
      { env: "PS3RECOMP_SPURS_WORKER_WAKE", type: "toggle", def: true, on: null, off: "0",
        en: ["Wake only the SPU worker that has work", "Faster when the car stands still. Untick after a freeze that the two settings above do not cure."],
        fr: ["Ne réveiller que le worker SPU qui a du travail", "Plus rapide à l'arrêt. Décocher en cas de gel que les deux réglages ci-dessus ne guérissent pas."] },
      { env: "SPURS_MAXCONT", type: "choice",
        options: [
          ["", "4 SPUs for the game's jobs (default)", "4 SPU pour les tâches du jeu (par défaut)"],
          ["EvoDefault:2", "2 SPUs (the earlier setting)", "2 SPU (l'ancien réglage)"],
          ["none", "The game's own values: 1 SPU (very slow)", "Les valeurs du jeu : 1 SPU (très lent)"],
        ],
        en: ["SPUs given to the game's jobs", "How many SPUs run the physics and animation jobs at the same time. Try 2 if the physics or the animations look wrong, or after a freeze."],
        fr: ["SPU donnés aux tâches du jeu", "Combien de SPU font tourner en même temps les tâches de physique et d'animation. Essayer 2 si la physique ou les animations semblent fausses, ou après un gel."] },
    ],
  },
  {
    en: "Picture", fr: "Image",
    items: [
      { env: "GEO_CACHE", type: "toggle", def: true, on: null, off: "0",
        en: ["Geometry cache", "Keeps the converted 3D models from one frame to the next (+1 to +3 frames per second). Untick if objects are missing or wrong."],
        fr: ["Cache de géométrie", "Garde d'une image à l'autre les modèles 3D déjà convertis (+1 à +3 images par seconde). Décocher si des objets manquent ou sont faux."] },
      { env: "TEX3D", type: "toggle", def: true, on: null, off: "0",
        en: ["3D textures", "The soft contact shadows under the vehicles. Unticked: the old dark squares come back (to compare)."],
        fr: ["Textures 3D", "Les ombres douces sous les véhicules. Décoché : les anciens carrés sombres reviennent (pour comparer)."] },
    ],
  },
  {
    en: "Display and latency", fr: "Affichage et latence",
    items: [
      { env: "D3D12_FRAME_LATENCY", type: "toggle", def: true, on: null, off: "0",
        en: ["One frame at most waiting to be shown", "Less delay between the pad and the screen. Unticked: Windows queues up to 3 frames (as before)."],
        fr: ["Une image au plus en attente d'affichage", "Moins de délai entre la manette et l'écran. Décoché : Windows garde jusqu'à 3 images en file (comme avant)."] },
      { env: "D3D12_VSYNC", type: "toggle", def: true, on: null, off: "0",
        en: ["Vertical sync", "Each frame waits for the screen's refresh. Unticked: tearing, but frames show at once (to measure the latency or the frame rate past the screen's)."],
        fr: ["Synchronisation verticale", "Chaque image attend le rafraîchissement de l'écran. Décoché : déchirures, mais les images s'affichent aussitôt (pour mesurer la latence ou dépasser la fréquence de l'écran)."] },
    ],
  },
  {
    en: "Speed and measurement", fr: "Vitesse et mesure",
    items: [
      { env: "PS3_USLEEP_SPIN", type: "toggle", def: true, on: null, off: "0",
        en: ["Short waits without a system call", "Waits under 1 ms spin on the processor: +2 to 5 %. Untick on a laptop on battery or to compare."],
        fr: ["Attentes courtes sans appel système", "Les attentes de moins d'1 ms tournent sur le processeur : +2 à 5 %. Décocher sur un portable sur batterie ou pour comparer."] },
      { env: "SPU_MFC_LOOKUP_CACHE", type: "toggle", def: true, on: null, off: "0",
        en: ["SPU channel cache", "Each SPU memory transfer finds its engine without a lock. Untick only to compare."],
        fr: ["Cache des canaux SPU", "Chaque transfert mémoire d'un SPU retrouve son moteur sans verrou. Décocher seulement pour comparer."] },
      { env: "PORT_JOBMODS", type: "toggle", def: true, on: null, off: "0",
        en: ["Recompiled SPU jobs", "Unticked: the SPU jobs run on the interpreter, about 25 times slower. Only to tell a recompilation bug from a game bug."],
        fr: ["Tâches SPU recompilées", "Décoché : les tâches SPU passent par l'interpréteur, environ 25 fois plus lent. Seulement pour distinguer un bug de recompilation d'un bug du jeu."] },
      { env: "GCM_SEMA_ACQUIRE", type: "toggle", def: true, on: null, off: "0",
        en: ["The game's 30 FPS limiter", "Unticked: no cap, the game runs too fast above 30 FPS (with 30 frames per second). Only to measure what the PC can do."],
        fr: ["Limiteur à 30 FPS du jeu", "Décoché : plus de plafond, le jeu va trop vite au-dessus de 30 FPS (en mode 30 images par seconde). Seulement pour mesurer ce que le PC peut faire."] },
    ],
  },
  {
    en: "Log", fr: "Journal",
    items: [
      { env: "PORT_GAME_LOG", type: "toggle", def: false, on: "1", off: null,
        en: ["The game's debug messages", "What the game itself prints (\"[game]\" lines of the log): useful to understand an error or a network problem."],
        fr: ["Messages de débogage du jeu", "Ce que le jeu écrit lui-même (lignes « [game] » du journal) : utile pour comprendre une erreur ou un problème réseau."] },
      { env: "RSX_HITCH", type: "toggle", def: false, on: "45", off: null,
        en: ["Note the long frames", "One \"[HITCH]\" line in the log for every frame longer than 45 ms, with where the time went: for stutters."],
        fr: ["Noter les images longues", "Une ligne « [HITCH] » dans le journal pour chaque image de plus de 45 ms, avec où le temps est passé : pour les saccades."] },
    ],
  },
  {
    en: "Network and menus", fr: "Réseau et menus",
    items: [
      { key: "local_test", type: "setting",
        en: ["Two-player test on this PC", "Two games on this PC, each with its own save (a \"Player 2\" button appears). Not for playing between PCs."],
        fr: ["Test à deux sur ce PC", "Deux jeux sur ce PC, chacun avec sa sauvegarde (un bouton « Joueur 2 » apparaît). Pas pour jouer entre PC."] },
      { env: "PORT_PSARC_PATCHES", type: "toggle", def: true, on: null, off: "0",
        en: ["The port's menus (recomp\\psarc_patches.bin)", "The menus changed for the LAN games and the results. Unticked: the disc's menus as they are."],
        fr: ["Les menus du portage (recomp\\psarc_patches.bin)", "Les menus modifiés pour les parties en réseau local et les résultats. Décoché : les menus du disque tels quels."] },
    ],
  },
];

function lang() {
  return settings && settings.lang === "fr" ? "fr" : "en";
}

function t(key, ...args) {
  const text = TEXT[lang()][key] ?? TEXT.en[key] ?? key;
  return typeof text === "function" ? text(...args) : text;
}

// Puts the chosen language in every element that names a key. The strings of data-i18n-html
// are the constants of TEXT above, never something read from a file or typed by the player.
function showLanguage() {
  document.documentElement.lang = lang();
  document.title = t("title");
  for (const e of document.querySelectorAll("[data-i18n]")) e.textContent = t(e.dataset.i18n);
  for (const e of document.querySelectorAll("[data-i18n-html]")) e.innerHTML = t(e.dataset.i18nHtml);
  for (const e of document.querySelectorAll("[data-i18n-title]")) e.title = t(e.dataset.i18nTitle);
  for (const e of document.querySelectorAll("[data-i18n-placeholder]")) e.placeholder = t(e.dataset.i18nPlaceholder);
  $("lang").value = lang();
}

function message(text, error = false) {
  $("message").textContent = text || "";
  $("message").classList.toggle("error", error);
}

function duration(seconds) {
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60);
  return h ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`;
}

// --- sections ---

function go(page) {
  for (const s of document.querySelectorAll("[data-page]")) s.hidden = s.dataset.page !== page;
  for (const b of document.querySelectorAll(".nav")) b.classList.toggle("active", b.dataset.go === page);
  try { sessionStorage.setItem("page", page); } catch {}
}

// --- files ---

function showChecks() {
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
  // The indicator in the top bar and the badge of the Files section: red for a missing piece the
  // game needs, orange for an optional one.
  const bad = checks.filter((c) => !c.ok && c.needed).length;
  const warn = checks.filter((c) => !c.ok && !c.needed).length;
  const alert = $("files-alert"), badge = $("files-badge");
  alert.hidden = badge.hidden = !(bad || warn);
  alert.classList.toggle("bad", bad > 0);
  badge.classList.toggle("bad", bad > 0);
  alert.textContent = bad ? t("files_bad", bad) : t("files_warn", warn);
  alert.title = t("files_tip");
  badge.textContent = String(bad || warn);
}

// --- Dev settings ---

function devValue(item) {
  return Object.prototype.hasOwnProperty.call(settings.dev, item.env) ? settings.dev[item.env] : undefined;
}

function devTicked(item) {
  if (item.type === "setting") return !!settings[item.key];
  const v = devValue(item);
  if (v === undefined) return item.def;
  return item.on === null ? v !== item.off : v === item.on;
}

function devChanged(item) {
  if (item.type === "setting") return !!settings[item.key];
  return devValue(item) !== undefined;
}

function setDev(item, value) {
  if (value === null || value === "") delete settings.dev[item.env];
  else settings.dev[item.env] = value;
}

function devChangedCount() {
  let n = 0;
  for (const cat of DEV) for (const item of cat.items) if (devChanged(item)) n++;
  if (settings.extra.trim()) n++;
  return n;
}

function showDevBadge() {
  const n = devChangedCount();
  $("dev-badge").hidden = n === 0;
  $("dev-badge").textContent = String(n);
  $("dev-badge").title = t("dev_badge_tip", n);
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

// The Dev list, built from DEV in the page's language (plain text only: textContent).
function showDev() {
  const box = $("dev-list");
  box.replaceChildren();
  const l = lang();
  for (const cat of DEV) {
    const card = el("div", "card");
    card.append(el("h2", "", cat[l]));
    for (const item of cat.items) {
      const [label, help] = item[l];
      const row = el("div", "dev-item");
      row.classList.toggle("changed", devChanged(item));
      const head = el("div", "dev-head");
      let input;
      if (item.type === "choice") {
        head.append(el("span", "dev-label", label));
        input = el("select");
        for (const [value, en, fr] of item.options) {
          const o = el("option", "", l === "fr" ? fr : en);
          o.value = value;
          input.append(o);
        }
        const v = devValue(item);
        if (v !== undefined && !item.options.some(([value]) => value === v)) {
          const o = el("option", "", v);       // a value written by hand in lanceur.json
          o.value = v;
          input.append(o);
        }
        input.value = v ?? "";
        input.addEventListener("change", () => { setDev(item, input.value); afterDevChange(); });
      } else {
        const sw = el("label", "switch");
        input = el("input");
        input.type = "checkbox";
        input.setAttribute("aria-label", label);
        input.checked = devTicked(item);
        input.addEventListener("change", () => {
          if (item.type === "setting") settings[item.key] = input.checked;
          else if (input.checked === item.def) setDev(item, null);
          else setDev(item, input.checked ? item.on : item.off);
          afterDevChange();
        });
        sw.append(input, el("span", "slider"));
        const name = el("label", "dev-label", label);
        name.addEventListener("click", () => input.click());
        head.append(sw, name);
      }
      const tags = el("span", "dev-tags");
      if (item.env) tags.append(el("code", "", item.env));
      if (devChanged(item)) tags.append(el("span", "tag-changed", t("dev_changed")));
      head.append(tags);
      if (item.type === "choice") head.append(input);
      row.append(head, el("small", "", help));
      card.append(row);
    }
    box.append(card);
  }
  showDevBadge();
}

function afterDevChange() {
  showDev();
  saveNow();
}

// --- the page ---

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
  $("local-test-note").hidden = !(settings.lan && settings.local_test);
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
  $("extra").value = settings.extra;
  showDev();
  $("playtime").textContent = settings.sessions ? t("playtime", duration(settings.seconds), settings.sessions) : "";
}

async function refresh() {
  const s = await invoke("state");
  settings = s.settings;
  settings.dev = settings.dev || {};
  running = s.running;
  playable = s.playable;
  checks = s.checks;
  showLanguage();
  $("launcher-version").textContent = s.launcher_version;
  $("folder").textContent = s.folder;
  showChecks();
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
  settings.extra = $("extra").value;
  // settings.dev and settings.local_test are kept up to date by the Dev section itself.
}

async function saveNow() {
  clearTimeout(saveTimer);
  saveTimer = null;
  readPage();
  showButtons();
  showDevBadge();
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
for (const id of ["game-lang", "lan", "net-ip", "window", "res", "fps30", "fps60"])
  $(id).addEventListener("change", saveNow);
// The language: saved like any setting, then the whole page is shown again (the Rust side
// answers in the new language too).
$("lang").addEventListener("change", async () => {
  if (await saveNow()) await refresh();
  else { showLanguage(); showChecks(); showDev(); }   // not saved (e.g. a name to correct): the page changes all the same
});
$("dev-reset").addEventListener("click", () => {
  settings.dev = {};
  settings.local_test = false;
  settings.extra = "";
  $("extra").value = "";
  afterDevChange();
});
for (const b of document.querySelectorAll("[data-go]")) b.addEventListener("click", () => go(b.dataset.go));
$("message").addEventListener("click", () => { if (!playable) go("files"); });
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

// The logo: the game's own emblem (PS3_GAME\ICON0.PNG, read from the game folder); "MS" without it.
invoke("game_picture")
  .then((bytes) => {
    const logo = document.querySelector(".logo");
    logo.style.backgroundImage = `url(${URL.createObjectURL(new Blob([bytes], { type: "image/png" }))})`;
    logo.textContent = "";
    logo.classList.add("picture");
  })
  .catch(() => {});

document.addEventListener("contextmenu", (e) => e.preventDefault());
let firstPage = "player";
try { firstPage = sessionStorage.getItem("page") || firstPage; } catch {}
go(firstPage);
refresh()
  .then(() => { if (!playable) go("files"); })
  .catch((e) => message(String(e), true));
