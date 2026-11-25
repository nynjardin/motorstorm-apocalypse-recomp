/* MotorStorm: Apocalypse port -- portable mode: the exe at the root of the game folder.
 *
 *   <game>\PS3_GAME\...              the dump, read in place, never written
 *   <game>\MotorStormApocalypse.exe  this exe, started WITHOUT ARGUMENTS (double click, Launcher.exe)
 *   <game>\Launcher.exe               the launcher (launcher\, docs\lanceur.md)
 *   <game>\recomp\EBOOT.elf          the decrypted EBOOT (rpcs3.exe --decrypt PS3_GAME\USRDIR\EBOOT.BIN)
 *   <game>\recomp\settings.ini       NAME=value lines written by the launcher (optional)
 *   <game>\recomp\psarc_patches.bin, libsre_image.bin, dev_flash\   what port\run.bat points at
 *   <game>\recomp\save\, dev_hdd0\, dev_hdd1\, shader_cache\, run.log   what the game writes
 *
 * Every path is relative to the exe: the folder can be moved or copied to another PC as it is.
 * With arguments (port\run.bat: <ELF> <VFS root>) nothing here applies.
 *
 * The settings are environment variables, the port's and the toolkit's only interface. Order:
 * what the process environment already holds wins, then recomp\settings.ini, then the defaults
 * below (the same as port\run.bat and port\run_lan.bat: keep the three in step). They are set in
 * an early static initializer (init_seg(lib)): some readers cache their variable in a static.
 *
 *   PORT_INSTANCE=<n>   n >= 2: another copy of the game on the same PC (LAN tests): its own save
 *                       (recomp\save_p<n>), HDD (recomp\p<n>\, copied from instance 1 the first
 *                       time), log (run_p<n>.log), pad file and window title.
 *   PORT_LAN_LOCAL=<n>  with PORT_NET_LAN=1: n instances on this machine (1 = 2), instance k is
 *                       127.0.0.k and talks to all the others.
 */
#ifdef _WIN32
#define _CRT_SECURE_NO_WARNINGS     /* freopen: see the log redirection */
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fcntl.h>
#include <fstream>
#include <io.h>
#include <string>

#pragma warning(disable : 4073)     /* initializers put in the library initialization area */
#pragma init_seg(lib)

namespace {

std::string g_elf;                  /* empty: not in portable mode */

bool env_has(const char* name)
{
    char buf[4];
    size_t n = 0;
    return getenv_s(&n, buf, sizeof buf, name) != EINVAL && n > 0;
}
void env_default(const char* name, const std::string& value)
{
    if (!env_has(name)) _putenv_s(name, value.c_str());
}
std::string env_get(const char* name)
{
    const char* v = std::getenv(name);
    return v ? v : "";
}

[[noreturn]] void fail(const wchar_t* text)
{
    MessageBoxW(nullptr, text, L"MotorStorm: Apocalypse", MB_OK | MB_ICONERROR);
    ExitProcess(2);
}

bool exists(const std::string& p)
{
    const DWORD a = GetFileAttributesA(p.c_str());
    return a != INVALID_FILE_ATTRIBUTES;
}

/* The address of the card of the default route (not the first address of the host name: on a PC
 * with VPN adapters that one was a VPN). No packet is sent: connect() on UDP only picks a route. */
std::string default_route_ip()
{
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa)) return "";
    std::string out;
    const SOCKET s = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (s != INVALID_SOCKET) {
        sockaddr_in to{};
        to.sin_family = AF_INET;
        to.sin_port = htons(53);
        inet_pton(AF_INET, "8.8.8.8", &to.sin_addr);
        sockaddr_in me{};
        int len = sizeof me;
        if (!connect(s, (sockaddr*)&to, sizeof to) && !getsockname(s, (sockaddr*)&me, &len)) {
            char buf[32] = "";
            if (inet_ntop(AF_INET, &me.sin_addr, buf, sizeof buf)) out = buf;
        }
        closesocket(s);
    }
    WSACleanup();
    return out;
}

void read_settings(const std::string& path)
{
    std::ifstream f(path);
    std::string line;
    while (std::getline(f, line)) {
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
        if (line.empty() || line[0] == '#' || line[0] == ';') continue;
        const size_t eq = line.find('=');
        if (eq == std::string::npos || eq == 0) continue;
        env_default(line.substr(0, eq).c_str(), line.substr(eq + 1));
    }
}

struct Portable {
    Portable()
    {
        int argc = 0;
        if (LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc)) LocalFree(argv);
        if (argc >= 2) return;                      /* port\run.bat: <ELF> <VFS root> */

        char exe[MAX_PATH * 2] = "";
        GetModuleFileNameA(nullptr, exe, sizeof exe);
        std::string root(exe);
        root.erase(root.find_last_of("\\/"));
        const std::string data = root + "\\recomp";

        if (!exists(root + "\\PS3_GAME\\USRDIR\\ms3.psarc"))
            /* Both languages, English first: the launcher's language setting is not read yet. */
            fail(L"The game was not found.\n\nMotorStormApocalypse.exe must be at the root of the "
                 L"game folder, beside the PS3_GAME folder (MotorStorm: Apocalypse, BCES00484).\n\n"
                 L"————\n\n"
                 L"Le jeu est introuvable.\n\nMotorStormApocalypse.exe doit être posé à la racine du "
                 L"dossier du jeu, à côté du dossier PS3_GAME (MotorStorm: Apocalypse, BCES00484).");
        g_elf = data + "\\EBOOT.elf";
        if (!exists(g_elf))
            fail(L"recomp\\EBOOT.elf was not found.\n\nIt is the game's decrypted executable: "
                 L"rpcs3.exe --decrypt PS3_GAME\\USRDIR\\EBOOT.BIN, then copy the resulting file "
                 L"as recomp\\EBOOT.elf.\n\n"
                 L"————\n\n"
                 L"recomp\\EBOOT.elf est introuvable.\n\nC'est l'exécutable du jeu déchiffré : "
                 L"rpcs3.exe --decrypt PS3_GAME\\USRDIR\\EBOOT.BIN, puis copier le fichier obtenu "
                 L"sous le nom recomp\\EBOOT.elf.");

        read_settings(data + "\\settings.ini");

        const int inst = std::atoi(env_get("PORT_INSTANCE").c_str());
        std::string hdd = data, save = data + "\\save", log = data + "\\run.log";
        if (inst >= 2) {
            const std::string n = std::to_string(inst);
            hdd = data + "\\p" + n;
            save = data + "\\save_p" + n;
            log = data + "\\run_p" + n + ".log";
            env_default("PS3_TITLE", "ps3recomp P" + n);
            env_default("PAD_FILE", env_get("TEMP") + "\\motorstorm_pad" + n + ".txt");
            std::error_code ec;                     /* first use: start from instance 1's save and cache */
            namespace fs = std::filesystem;
            if (!fs::exists(save, ec) && fs::exists(data + "\\save", ec))
                fs::copy(data + "\\save", save, fs::copy_options::recursive, ec);
            if (!fs::exists(hdd, ec)) {
                fs::create_directories(hdd, ec);
                for (const char* d : { "\\dev_hdd0", "\\dev_hdd1" })
                    if (fs::exists(data + d, ec)) fs::copy(data + d, hdd + d, fs::copy_options::recursive, ec);
            }
        }
        for (const std::string& d : { data + "\\shader_cache", hdd + "\\dev_hdd0", hdd + "\\dev_hdd1", save }) {
            std::error_code ec;
            std::filesystem::create_directories(d, ec);
        }

        /* Where things are. */
        env_default("PS3_VFS_ROOT", root);
        env_default("PS3_HDD0_ROOT", hdd + "\\dev_hdd0");
        env_default("PS3_HDD1_ROOT", hdd + "\\dev_hdd1");
        env_default("PS3_GAMEDATA_ROOT", save);
        env_default("RSX_SHADER_CACHE", data + "\\shader_cache");
        env_default("PS3_DEV_FLASH", data + "\\dev_flash");
        if (exists(data + "\\psarc_patches.bin")) env_default("PORT_PSARC_PATCHES", data + "\\psarc_patches.bin");
        if (exists(data + "\\libsre_image.bin")) env_default("PORT_LIBSRE_IMAGE", data + "\\libsre_image.bin");

        /* The title's LAN mode (port\run_lan.bat, docs\reseau.md). */
        if (env_get("PORT_NET_LAN") == "1") {
            env_default("PS3_NET_ONLINE", "1");
            env_default("PSNR_SERVER", "127.0.0.1");
            env_default("PORT_NETCTL_TOOLKIT", "1");
            env_default("PS3_HTTP_BLOCK", "online.scee.com");
            env_default("PS3_NET_P2P_PORT", "3659");
            env_default("PORT_SIM_RT", "1");
            env_default("PORT_SIM_INTERVAL", "2");
            if (env_has("PORT_LAN_LOCAL")) {        /* = how many instances on this machine (1 = 2) */
                const int me = inst >= 2 ? inst : 1;
                int n = std::atoi(env_get("PORT_LAN_LOCAL").c_str());
                if (n < 2) n = 2;
                if (n > 16) n = 16;
                std::string peers;
                for (int k = 1; k <= n; k++)
                    if (k != me) peers += (peers.empty() ? "" : ",") + ("127.0.0." + std::to_string(k));
                env_default("PS3_NET_IP", "127.0.0." + std::to_string(me));
                env_default("PS3_NET_PEERS", peers);
            }
            if (!env_has("PS3_NET_IP")) {
                const std::string ip = default_route_ip();
                if (!ip.empty()) env_default("PS3_NET_IP", ip);
            }
        }

        /* The port's defaults (port\run.bat explains each). */
        static const char* const kDefaults[][2] = {
            { "SPU_INTERP_UNLIFTED", "1" }, { "PORT_JOBMODS", "1" },
            { "SPURS_MAXCONT", "EvoDefault:4,EvoHigh:2" }, { "SPU_MFC_LOOKUP_CACHE", "1" },
            { "PORT_FIFO_WAIT", "0" }, { "RSX_ASYNC", "1" }, { "PS3_USLEEP_SPIN", "8" },
            { "PS3RECOMP_PPU_RESV_OPEN_COUNT", "1" }, { "PS3RECOMP_SPURS_WORKER_WAKE", "1" },
            { "SPU_FLOAT_RZ", "1" }, { "GEO_CACHE", "1" }, { "PORT_SIM_RT", "0" },
            { "GCM_SEMA_ACQUIRE", "1" }, { "GCM_SEMA_ACQUIRE_MS", "250" },
            { "RSX_MAX_VERTICES", "3145728" }, { "VP_NOFIXPROJ", "1" },
        };
        for (const auto& d : kDefaults) env_default(d[0], d[1]);

        /* The log. Started by the launcher, stdout and stderr already ARE the log file (it opens
         * recomp\run.log and hands it over, as run.bat's redirection does): nothing to do.
         * Started by a double click, they are a console made for us: the log is put under them
         * and that console window is hidden. (FreeConsole instead of hiding left the log EMPTY
         * for the whole run, 2026-11-24: do not detach.) The previous log is kept once. */
        const DWORD kind = GetFileType(GetStdHandle(STD_OUTPUT_HANDLE));
        if (kind == FILE_TYPE_DISK || kind == FILE_TYPE_PIPE) {
            std::printf("[portable] root %s, instance %d, name %s, address %s\n", root.c_str(),
                        inst >= 2 ? inst : 1, env_get("PS3_NP_ONLINE_ID").c_str(), env_get("PS3_NET_IP").c_str());
            return;
        }
        const std::string prev = log.substr(0, log.size() - 4) + ".prev.log";
        MoveFileExA(log.c_str(), prev.c_str(), MOVEFILE_REPLACE_EXISTING);
        /* Opened by Win32 with full sharing (freopen_s opens unshared: the log could not be read
         * while the game runs), then put under stdout and stderr. Started without a console,
         * the two streams have no descriptor yet: NUL gives them one first. */
        const HANDLE h = CreateFileA(log.c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                     nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        const int fd = h != INVALID_HANDLE_VALUE ? _open_osfhandle((intptr_t)h, _O_WRONLY | _O_TEXT) : -1;
        if (fd >= 0) {
            if (_fileno(stdout) < 0) (void)freopen("NUL", "w", stdout);
            if (_fileno(stderr) < 0) (void)freopen("NUL", "w", stderr);
            if (_fileno(stdout) >= 0) _dup2(fd, _fileno(stdout));
            if (_fileno(stderr) >= 0) _dup2(fd, _fileno(stderr));
        }
        DWORD owners[2];
        if (GetConsoleProcessList(owners, 2) == 1)                  /* a console made for us alone */
            if (const HWND con = GetConsoleWindow()) ShowWindow(con, SW_HIDE);
        std::printf("[portable] root %s, instance %d, name %s, address %s\n", root.c_str(),
                    inst >= 2 ? inst : 1, env_get("PS3_NP_ONLINE_ID").c_str(), env_get("PS3_NET_IP").c_str());
    }
};
Portable g_portable;

}   // namespace

/* The ELF to load when the exe was started without arguments, or nullptr. */
const char* port_portable_elf(void) { return g_elf.empty() ? nullptr : g_elf.c_str(); }

#else
const char* port_portable_elf(void) { return nullptr; }
#endif
