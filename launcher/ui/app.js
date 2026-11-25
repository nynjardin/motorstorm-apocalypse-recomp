// The launcher's page. The Rust side (src-tauri/src/main.rs) owns the settings and the game
// process; this page shows them and sends every change back (command "save").
const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const $ = (id) => document.getElementById(id);
let settings = null;
let running = [];
let playable = false;
let saveTimer = null;

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
  auto.textContent = defaultIp ? `Automatique (${defaultIp})` : "Automatique";
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
  $("play").textContent = one ? "Le jeu tourne…" : "▶ Jouer";
  $("play2").hidden = !(settings.lan && settings.local_test);
  $("play2").disabled = !playable || two;
  $("stop").hidden = running.length === 0;
  $("lan-box").classList.toggle("off", !settings.lan || settings.local_test);
}

function showSettings() {
  $("pseudo").value = settings.pseudo;
  $("lan").checked = settings.lan;
  $("peers").value = settings.peers;
  $("fps60").checked = settings.fps60;
  $("fps30").checked = !settings.fps60;
  if (settings.window && ![...$("window").options].some((o) => o.value === settings.window)) {
    const o = document.createElement("option");      // a size written by hand in lanceur.json
    o.value = settings.window;
    o.textContent = `Fenêtre ${settings.window.replace("x", " × ")}`;
    $("window").append(o);
  }
  $("window").value = settings.window;
  if (settings.res && ![...$("res").options].some((o) => o.value === settings.res)) {
    const o = document.createElement("option");      // a size written by hand in lanceur.json
    o.value = settings.res;
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
  $("playtime").textContent = settings.sessions
    ? `Temps de jeu : ${duration(settings.seconds)} (${settings.sessions} partie${settings.sessions > 1 ? "s" : ""})`
    : "";
}

async function refresh() {
  const s = await invoke("state");
  settings = s.settings;
  running = s.running;
  playable = s.playable;
  $("launcher-version").textContent = s.launcher_version;
  $("folder").textContent = s.folder;
  showChecks(s.checks);
  showSettings();
  showAddresses(s.addresses, s.default_ip);
  showButtons();
  if (!playable) message("Il manque quelque chose dans le dossier du jeu (voir à gauche).", true);
}

function readPage() {
  settings.pseudo = $("pseudo").value.trim();
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
    $("pseudo").classList.toggle("invalid", String(e).startsWith("Pseudo"));
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
    message(instance === 1
      ? "Le jeu démarre : la fenêtre met un moment à s'afficher, l'écran titre arrive après environ une minute."
      : "Le deuxième jeu démarre (joueur " + settings.pseudo.slice(0, 15) + "2).");
  } catch (e) {
    message(String(e), true);
  }
}

for (const id of ["pseudo", "peers", "extra"]) $(id).addEventListener("input", saveSoon);
for (const id of ["lan", "net-ip", "window", "res", "fps30", "fps60", "rsx-async", "spu-async-pool", "geo-cache", "game-log", "local-test"])
  $(id).addEventListener("change", saveNow);
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
  const ended = code === 0 || code === null ? "terminé" : `arrêté (code ${code})`;
  message(`Jeu ${instance > 1 ? instance + " " : ""}${ended} après ${duration(seconds)}.`, !(code === 0 || code === null));
});

document.addEventListener("contextmenu", (e) => e.preventDefault());
refresh().catch((e) => message(String(e), true));
