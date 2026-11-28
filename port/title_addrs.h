/* Guest addresses and structure offsets that differ between the two executables of the title:
 *   - the disc EBOOT (BCES00484, work/BCES00484/recomp)            default
 *   - the 1.06 update EBOOT (BCES00484_106, work/BCES00484_106/)   -DPORT_V106=1
 * The two are different builds (docs/PROGRESS.md "Port de l'EBOOT 1.06"): every function moved and
 * some structures changed. scripts/addr_map.py maps the functions, scripts/addr_cand.py shows the
 * candidates; each entry below was checked by comparing the disassembly of both.
 *
 * A port hook is defined as port_hook_<disc address>; the 1.06 build renames it to the address of the
 * same function in 1.06 (scripts/func_hooks.py puts the call in the lifted function of that address,
 * from port/func_hooks_106.txt). */
#pragma once

#ifdef PORT_V106

/* hooks (disc address -> 1.06 address) */
#define port_hook_00B229CC port_hook_00AE0E68   /* the debug printf stub                          */
#define port_hook_0038A8D0 port_hook_0037CB28   /* NetGlobalData::SetLanOrWan                     */
#define port_hook_002EC270 port_hook_002C90FC   /* CommunityAction::Succeeded                     */
#define port_hook_002EC280 port_hook_002C910C   /* CommunityAction::HasError                      */
#define port_hook_003B5948 port_hook_003A7CA0   /* "logged into OTG"                              */
#define port_hook_002BD2D8 port_hook_0029D6D8   /* XpManager::AddChips                            */

/* guest functions the port calls */
#define func_002D932C func_002B878C             /* profile of a player: (manager, player)         */
#define func_0028FEB8 func_002728B8             /* profile: start the save                        */

/* NetGlobalData */
#define T_NGD_NETMODE    0xD6Cu                 /* disc 0xC40 : LanOrWan word                     */
#define T_NGD_GUARD_IDX  0xE78u                 /* disc 0xD48                                     */
#define T_NGD_GUARD_OFS  0xE6Bu                 /* disc 0xD3B                                     */
#define T_OTG_LOGGED_ADDR 0x01318ACAu           /* disc 0x014D9F66, byte: "logged into OTG"       */
#define T_APP_GLOBAL_ADDR 0x012ECE5Cu           /* disc 0x0144FB4C, pointer to the application    */
#define T_SPURS_KICK_LR   0x007E8A44u           /* disc 0x00857F9C                                */

/* manager = [[[global] + 0x298] + 0xD8] (disc: [[[[global] + 0x29C] + 0x294] + 0x84]) */
#define T_PROFILE_MANAGER_CHAIN(rd, g) \
    (((g) ? rd((g) + 0x298u) : 0u) ? rd(rd((g) + 0x298u) + 0xD8u) : 0u)

#else

#define T_NGD_NETMODE    0xC40u
#define T_NGD_GUARD_IDX  0xD48u
#define T_NGD_GUARD_OFS  0xD3Bu
#define T_OTG_LOGGED_ADDR 0x014D9F66u
#define T_APP_GLOBAL_ADDR 0x0144FB4Cu
#define T_SPURS_KICK_LR   0x00857F9Cu

#define T_PROFILE_MANAGER_CHAIN(rd, g) \
    ((((g) ? rd((g) + 0x29Cu) : 0u) ? rd(rd((g) + 0x29Cu) + 0x294u) : 0u) ? \
        rd(rd(rd((g) + 0x29Cu) + 0x294u) + 0x84u) : 0u)

#endif
