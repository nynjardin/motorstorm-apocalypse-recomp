cmake_minimum_required(VERSION 3.20)
project(MotorStormApocalypse
    VERSION 0.1.0
    LANGUAGES C CXX
    DESCRIPTION "Recompiled PS3 game project (ps3recomp)"
)

# ---------------------------------------------------------------------------
# Standards
# ---------------------------------------------------------------------------
set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Prefer Ninja if available
if(NOT CMAKE_GENERATOR MATCHES "Ninja" AND NOT DEFINED ENV{CMAKE_GENERATOR})
    message(STATUS "Tip: use -G Ninja for faster builds")
endif()

# ---------------------------------------------------------------------------
# The two directories this project is built from
# ---------------------------------------------------------------------------
# PS3RECOMP_DIR is the toolkit checkout: include/, runtime/, libs/, tools/.
# RECOMP_DIR is where the lifter's output for THIS game lives. They are
# separate on purpose -- a port keeps its generated code in its own tree and
# points at whatever toolkit checkout it is building against:
#
#   cmake -B build -G Ninja \
#         -DPS3RECOMP_DIR=/path/to/ps3recomp \
#         -DRECOMP_DIR=/path/to/my_game/recompiled
#
if(NOT DEFINED PS3RECOMP_DIR)
    # Default: this project is still sitting inside ps3recomp/templates/project/
    get_filename_component(PS3RECOMP_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../" ABSOLUTE)
endif()
get_filename_component(PS3RECOMP_DIR "${PS3RECOMP_DIR}" ABSOLUTE)

set(RECOMP_DIR "${CMAKE_CURRENT_SOURCE_DIR}/recompiled" CACHE PATH
    "Directory holding the lifter's output: ppu_recomp.h and the lifted sources")
get_filename_component(RECOMP_DIR "${RECOMP_DIR}" ABSOLUTE)

message(STATUS "ps3recomp SDK:   ${PS3RECOMP_DIR}")
message(STATUS "Lifted output:   ${RECOMP_DIR}")

if(NOT EXISTS "${RECOMP_DIR}/ppu_recomp.h")
    message(FATAL_ERROR
        "No ppu_recomp.h in ${RECOMP_DIR}.\n"
        "That header and the lifted sources beside it are what "
        "tools/ppu_lifter.py writes. Run the lifter, drop its output there, "
        "or point -DRECOMP_DIR= at wherever it already is.")
endif()

# The lifted translation units. A game's lift is hundreds of generated files,
# so they are globbed rather than listed; re-run CMake after a fresh lift.
file(GLOB RECOMP_SOURCES CONFIGURE_DEPENDS
    "${RECOMP_DIR}/*.c"
    "${RECOMP_DIR}/*.cpp"
)
if(NOT RECOMP_SOURCES)
    message(FATAL_ERROR
        "${RECOMP_DIR} has a ppu_recomp.h but no .c or .cpp beside it. The "
        "lifted functions and the function table live in those; without them "
        "there is nothing to run.")
endif()
list(LENGTH RECOMP_SOURCES RECOMP_SOURCE_COUNT)
message(STATUS "Lifted sources:  ${RECOMP_SOURCE_COUNT} file(s)")

# ---------------------------------------------------------------------------
# ps3recomp runtime library
# ---------------------------------------------------------------------------
# Built from source as a subdirectory rather than imported as a prebuilt
# archive. A static library carries none of its own link requirements, so an
# imported one arrives without SDL2, pthreads, the Metal frameworks or the
# Winsock/XInput imports -- the link then fails on every platform for a
# different reason. add_subdirectory hands all of that over with the target.
add_subdirectory("${PS3RECOMP_DIR}" "${CMAKE_BINARY_DIR}/ps3recomp_sdk"
                 EXCLUDE_FROM_ALL)

# ---------------------------------------------------------------------------
# The HLE NID table
# ---------------------------------------------------------------------------
# Maps each firmware import NID onto the handler in the runtime that answers
# it. A port may keep a hand-curated one beside its lift; otherwise generate
# the canonical every-module table, which is what the toolkit's own boot
# harness uses.
if(EXISTS "${RECOMP_DIR}/ppu_hle_nids.cpp")
    set(HLE_NID_TABLE "${RECOMP_DIR}/ppu_hle_nids.cpp")
    message(STATUS "HLE NID table:   ${HLE_NID_TABLE}")
else()
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    set(HLE_NID_TABLE "${CMAKE_CURRENT_BINARY_DIR}/ppu_hle_nids.cpp")
    # The generator discovers handlers from library definitions. Rebuild when
    # an existing module changes, and reconfigure when a new module is added.
    file(GLOB_RECURSE HLE_NID_SOURCES CONFIGURE_DEPENDS
        "${PS3RECOMP_DIR}/libs/*.c")
    # A removed input cannot make the output older than a remaining dependency.
    # Track the list itself so deletions also remove stale handler references.
    set(HLE_NID_SOURCE_LIST "${CMAKE_CURRENT_BINARY_DIR}/hle_nid_sources.txt")
    file(GENERATE OUTPUT "${HLE_NID_SOURCE_LIST}" CONTENT "${HLE_NID_SOURCES}\n")
    add_custom_command(
        OUTPUT "${HLE_NID_TABLE}"
        COMMAND "${Python3_EXECUTABLE}"
                "${PS3RECOMP_DIR}/tools/gen_hle_nids.py"
                --out "${HLE_NID_TABLE}" --all
        DEPENDS "${PS3RECOMP_DIR}/tools/gen_hle_nids.py"
                "${PS3RECOMP_DIR}/tools/nid_database.py"
                ${HLE_NID_SOURCES} "${HLE_NID_SOURCE_LIST}"
        COMMENT "Generating the HLE NID -> handler table")
    message(STATUS "HLE NID table:   generated (every module)")
endif()

# ---------------------------------------------------------------------------
# The game executable
# ---------------------------------------------------------------------------
# The PPU boot scaffold is compiled here rather than taken from the runtime
# library: every one of these files #includes the lifter's per-game
# ppu_recomp.h, so they can only be built against a particular lift.
set(PS3RECOMP_SCAFFOLD
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_loader.cpp"
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_hle.cpp"
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_fs.cpp"
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_sysprx.cpp"
)

# ---------------------------------------------------------------------------
# Lifted SPU images (optional)
# ---------------------------------------------------------------------------
# A title that runs SPU work gets its images lifted into <SPU_DIR>/<image>/ by
# tools/spu_lifter.py, with a registration TU generated by
# tools/build_spu_workloads.py. cellSpurs dispatches them by content
# fingerprint, so the generated table is keyed to the images THIS build ships:
# a table generated from another release registers signatures that can never
# match, which is worse than shipping none. Both the table and the job-module
# registry self-register from constructors and are therefore optional -- a tree
# that has not lifted its SPU images yet configures and links without them.
set(SPU_DIR "${CMAKE_CURRENT_SOURCE_DIR}/spu" CACHE PATH
    "Directory holding the lifted SPU images (<SPU_DIR>/<image>/spu_recomp.c)")
option(PORT_ENABLE_SPU "Compile and register the title's lifted SPU images" ON)

set(PORT_SPU_INPUTS "" CACHE STRING
    "Input files to scan for all embedded SPU ELF programs (semicolon-separated decrypted ELF/PRX/data paths)")
set(SPU_SOURCES "")
if(PORT_ENABLE_SPU AND PORT_SPU_INPUTS)
    include("${PS3RECOMP_DIR}/cmake/PS3RecompSPU.cmake")
    ps3recomp_generate_spu("${CMAKE_CURRENT_BINARY_DIR}/generated_spu" ${PORT_SPU_INPUTS})
    list(APPEND SPU_SOURCES ${SPU_GENERATED_SOURCES}
         "${PS3RECOMP_DIR}/runtime/spu/spu_dispatch_mt.c")
elseif(PORT_ENABLE_SPU)
    file(GLOB SPU_LIFTED CONFIGURE_DEPENDS "${SPU_DIR}/*/spu_recomp.c")
    if(SPU_LIFTED)
        list(LENGTH SPU_LIFTED SPU_IMAGE_COUNT)
        message(STATUS "Lifted SPU:      ${SPU_IMAGE_COUNT} image(s)")
        # The musttail indirect-branch fast path. Excluded from the runtime
        # library on purpose (see the SDK root CMakeLists): it must be built
        # here, by clang, or the tail call degrades to a plain call and a guest
        # loop that branches indirectly walks the thread stack off its guard
        # page a few thousand iterations in.
        list(APPEND SPU_SOURCES ${SPU_LIFTED}
             "${PS3RECOMP_DIR}/runtime/spu/spu_dispatch_mt.c")
        # Generated beside the lift; each is present only once its generator
        # has been run, so each is included only if it is actually here.
        foreach(gen IN ITEMS spu_workloads.c jobmods_register.c taskset_policy_bytes.c)
            if(EXISTS "${SPU_DIR}/${gen}")
                list(APPEND SPU_SOURCES "${SPU_DIR}/${gen}")
            else()
                message(STATUS "  (no ${gen} -- not registered)")
            endif()
        endforeach()
    else()
        message(STATUS "Lifted SPU:      none found in ${SPU_DIR}")
    endif()
endif()

# ---------------------------------------------------------------------------
# Lifted firmware libsre (optional, local only: firmware-derived)
# ---------------------------------------------------------------------------
# scripts/lift_libsre.py writes it; libsre_lle.cpp loads the image and binds
# the SPURS LF queue imports to it. Absent -> those imports stay HLE.
set(LIBSRE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../work/firmware/libsre" CACHE PATH
    "Output of scripts/lift_libsre.py")
get_filename_component(LIBSRE_DIR "${LIBSRE_DIR}" ABSOLUTE)
set(LIBSRE_SOURCES "")
if(EXISTS "${LIBSRE_DIR}/recomp/libsre_recomp.c" AND EXISTS "${LIBSRE_DIR}/libsre_image.bin")
    set(LIBSRE_SOURCES "${LIBSRE_DIR}/recomp/libsre_recomp.c")
    set_source_files_properties(${LIBSRE_SOURCES} PROPERTIES LANGUAGE CXX)
    message(STATUS "libsre LLE:      ${LIBSRE_DIR}")
else()
    message(STATUS "libsre LLE:      not lifted (scripts/lift_libsre.py)")
endif()

add_executable(${PROJECT_NAME}
    main.cpp
    stubs.cpp
    hle_overrides.cpp
    port_hwwatch.cpp    # PORT_HWWATCH / PORT_LISTDUMP debugging aids
    net_hooks.cpp       # entry hooks on the title's online code (scripts/func_hooks.py, docs/reseau.md)
    psarc_patch.cpp     # replacement of files inside ms3.psarc at read time (scripts/psarc_patch.py)
    portable.cpp        # no argument = the exe at the root of the game folder (docs/lanceur.md)
    libsre_lle.cpp
    spu_ms_overlays.c   # scripts/lift_ms_plugins.py: Multistream plugin banks (LS 0x37000)
    ${PS3RECOMP_SCAFFOLD}
    ${HLE_NID_TABLE}
    ${RECOMP_SOURCES}
    ${SPU_SOURCES}
    ${LIBSRE_SOURCES}
)
# Linker map (host RVA -> symbol) for the PS3_SAMPLE "[samp] rva" histogram. No code change.
if(MSVC OR CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
    target_link_options(${PROJECT_NAME} PRIVATE "/MAP:${CMAKE_BINARY_DIR}/MotorStormApocalypse.map")
endif()
if(LIBSRE_SOURCES)
    set_source_files_properties(libsre_lle.cpp PROPERTIES COMPILE_DEFINITIONS
        "PORT_HAVE_LIBSRE;PORT_LIBSRE_IMAGE_DEFAULT=\"${LIBSRE_DIR}/libsre_image.bin\"")
endif()

# The lifted SPU sources use bare #include "spu_context.h". Scope that include
# directory (and their flags) to those TUs alone: adding it to the whole target
# changes the compile command of every lifted PPU TU, and those are large enough
# that the needless rebuild is measured in tens of minutes.
#   SPU_USE_DISPATCH_MT -- route SPU_IB_DISPATCH through the musttail path.
#   -O2                 -- the target-wide -O1 exists for the huge PPU TUs; the
#                          SPU sources are small and decode-hot, so they get
#                          full optimization. The last -O on the line wins.
if(SPU_SOURCES)
    set_source_files_properties(${SPU_SOURCES} PROPERTIES
        INCLUDE_DIRECTORIES "${PS3RECOMP_DIR}/runtime/spu"
        COMPILE_DEFINITIONS SPU_USE_DISPATCH_MT)
    if(NOT MSVC OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        # PORT_SPU_AVX2: spu_helpers.h's AVX2 path (one 256-bit double op per SPU
        # float op instead of two SSE halves) for the exact-SPU float emulation,
        # which dominates the float-heavy WWS jobs on the race's critical path.
        # The exe then needs an AVX2+FMA CPU (Haswell / Zen or later).
        option(PORT_SPU_AVX2 "Build the lifted SPU sources with AVX2+FMA" ON)
        if(PORT_SPU_AVX2)
            set_source_files_properties(${SPU_SOURCES} PROPERTIES COMPILE_OPTIONS "-O2;-mavx2;-mfma;/GS-")
        else()
            set_source_files_properties(${SPU_SOURCES} PROPERTIES COMPILE_OPTIONS "-O2")
        endif()
        # PORT_SPU_FLOAT_FAST=<0|1|2>: native single-precision SPU floats in the lifted SPU
        # sources (toolkit patch #40, spu_helpers.h SPU_FLOAT_FAST; needs PORT_SPU_AVX2 and
        # SPU_FLOAT_RZ=1 at run time). 0 = the exact emulation, 1 = RPCS3's "approximate"
        # (zero-product rule kept), 2 = "relaxed". build.bat forwards the environment
        # variable of the same name. Only the SPU sources are recompiled when it changes.
        # Default 1 since 2026-11-23: race driving 22 -> 25-26 FPS and the music no longer stutters.
        set(PORT_SPU_FLOAT_FAST "1" CACHE STRING "Native SPU single-precision floats (0, 1, 2)")
        # PORT_SPU_FLOAT_XCMP=<0|1|2> (toolkit patch #48, spu_helpers.h SPU_FLOAT_XCMP): what the
        # float compares do with the native arithmetic. The host's compares answer "false" for
        # any operand of biased exponent 255 (a NaN here, an ordinary huge value on the SPU):
        # occjob / pvsjob use such values and hid ~400 draws of a still view of "Quai sous
        # pression" (dynamic objects, vehicle parts, decals popping; 2026-11-24).
        # 0 = host compares (the bug), 1 = host compare + exact redo when a lane is unordered
        # (default), 2 = exact integer-key compares always. build.bat forwards the environment
        # variable of the same name at configure time.
        set(PORT_SPU_FLOAT_XCMP "1" CACHE STRING "SPU float compares with the native arithmetic (0, 1, 2)")
        # PORT_SPU_LS_PROBES=<0|1> (toolkit PR #841, spu_context.h SPU_LS_PROBES): 0 compiles the
        # LS diagnostics gate (SPU_LS_WATCH, SPU_SMC_WATCH, SPU_LS_LOWREAD, SPU_WWS_PROBE) out of
        # every LS load and store of the lifted SPU sources. Default 1 until measured.
        set(PORT_SPU_LS_PROBES "1" CACHE STRING "LS diagnostics gate in the lifted SPU sources (0, 1)")
        set(_spu_xcmp ";SPU_FLOAT_XCMP=${PORT_SPU_FLOAT_XCMP};SPU_LS_PROBES=${PORT_SPU_LS_PROBES}")
        if(PORT_SPU_AVX2 AND NOT PORT_SPU_FLOAT_FAST STREQUAL "0")
            set_source_files_properties(${SPU_SOURCES} PROPERTIES
                COMPILE_DEFINITIONS "SPU_USE_DISPATCH_MT;SPU_FLOAT_FAST=${PORT_SPU_FLOAT_FAST}${_spu_xcmp}")
        endif()
        # PORT_SPU_FLOAT_EXACT=<a,b,...>: the lifted SPU sources whose path contains one of these
        # fragments keep the exact float emulation whatever PORT_SPU_FLOAT_FAST says (e.g.
        # "jobmod_f5fc590a4369,jobmod_d55c1580490d" = occjob and pvsjob, names from
        # scripts/jobmod_names.py). To find which module a float difference comes from, or to
        # keep one exact for good. build.bat forwards the environment variable at configure time.
        set(PORT_SPU_FLOAT_EXACT "" CACHE STRING "Lifted SPU sources kept on the exact float emulation (path fragments, comma separated)")
        # PORT_SPU_FLOAT_EXACT_DEFS (experiments): definitions those sources get instead of none,
        # each with a leading ";", e.g. ";SPU_FLOAT_FAST=1;SPU_FLOAT_XCMP" = native arithmetic
        # with the exact compares, to tell which family of operations a difference comes from.
        set(PORT_SPU_FLOAT_EXACT_DEFS "" CACHE STRING "Definitions for the PORT_SPU_FLOAT_EXACT sources (leading ';')")
        if(PORT_SPU_FLOAT_EXACT)
            string(REPLACE "," ";" _exact_frags "${PORT_SPU_FLOAT_EXACT}")
            foreach(_s ${SPU_SOURCES})
                foreach(_f ${_exact_frags})
                    string(FIND "${_s}" "${_f}" _hit)
                    if(NOT _hit EQUAL -1)
                        set_source_files_properties(${_s} PROPERTIES COMPILE_DEFINITIONS "SPU_USE_DISPATCH_MT${PORT_SPU_FLOAT_EXACT_DEFS}")
                        message(STATUS "exact SPU floats (${PORT_SPU_FLOAT_EXACT_DEFS}): ${_s}")
                    endif()
                endforeach()
            endforeach()
        endif()
    endif()
endif()

# app.rc carries the icon, the version block and the manifest, and needs a
# resource compiler. Listing it as a source on a host that has none is not a
# link error, it is a "no rule to make" for a file nothing can consume.
if(WIN32 AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/app.rc")
    target_sources(${PROJECT_NAME} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/app.rc")
endif()

target_include_directories(${PROJECT_NAME} PRIVATE
    "${RECOMP_DIR}"                            # the generated ppu_recomp.h
    "${PS3RECOMP_DIR}/include"
    "${PS3RECOMP_DIR}/runtime/ppu"
    "${PS3RECOMP_DIR}/runtime/spu"
    "${PS3RECOMP_DIR}/runtime/memory"
    "${PS3RECOMP_DIR}/runtime/syscalls"
    "${PS3RECOMP_DIR}/runtime/platform"        # win32_compat.h and friends
    "${PS3RECOMP_DIR}/libs/video"
    "${CMAKE_CURRENT_SOURCE_DIR}"
)

target_link_libraries(${PROJECT_NAME} PRIVATE
    ps3recomp_runtime
)

# The runtime is C++, and on Apple also Objective-C. Letting CMake infer the
# link language from the generated C would leave the C++ standard library out.
set_target_properties(${PROJECT_NAME} PROPERTIES LINKER_LANGUAGE CXX)

# Windows system import libraries. dbghelp symbolizes crash-handler addresses
# against the PDB, user32 and gdi32 are what the backend's window and its GDI
# present are made of, and winmm is timeBeginPeriod. None of the four names
# anything a POSIX linker can find; the D3D12 backend's own imports come in
# through the #pragma comment(lib) in libs/video/rsx_d3d12_backend.c.
if(WIN32)
    target_link_libraries(${PROJECT_NAME} PRIVATE
        dbghelp
        user32
        gdi32
        winmm
    )
endif()

# ---------------------------------------------------------------------------
# Compiler-specific flags
# ---------------------------------------------------------------------------
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(${PROJECT_NAME} PRIVATE
        -Wall -Wextra -Wno-unused-parameter
        -fno-strict-aliasing
        # The lift spells PPC arithmetic as signed C arithmetic, which must wrap;
        # without this, clang exploits overflow UB (e.g. folds "x*x < 0" to false).
        -fwrapv
        # The target-wide -O1 the SPU note above relies on, for a build whose
        # configuration sets no optimisation level (no CMAKE_BUILD_TYPE, or one
        # CMake has no defaults for). Without it every lifted PPU TU compiled at
        # -O0: each static inline helper (ppc_rlw64, vmx_w, vm_read32_inl) is a
        # real call that spills to the stack, and those calls were most of the
        # PPU thread's profile. -O1 keeps the huge TUs' build time sane. Debug
        # and the optimised configurations keep their own levels.
        $<$<NOT:$<CONFIG:Debug,Release,RelWithDebInfo,MinSizeRel>>:-O1>
    )
elseif(MSVC)
    target_compile_options(${PROJECT_NAME} PRIVATE
        /W3 /wd4100 /wd4244 /wd4267
        /Zc:__cplusplus         # report correct __cplusplus value
        # ppu_recomp.h defines PPU_FENCE, the lowering of the guest's
        # sync/lwsync/eieio/isync, and in C that is <stdatomic.h>. The lifter
        # writes C++ by default, but --single-file writes ppu_recomp.c, and a
        # port that took it would not compile without this. The runtime's own
        # build already carries the same flag for the same reason.
        /experimental:c11atomics
    )
    target_compile_definitions(${PROJECT_NAME} PRIVATE
        _CRT_SECURE_NO_WARNINGS
    )
endif()

# The lifted translation units are machine-generated and can run to hundreds of
# thousands of lines each, so they get their own flags:
#
#   - warnings off. They are about generated code and nobody will act on them,
#     and at this volume they bury the diagnostics that matter.
#   - no floating-point contraction. arm64 fuses a multiply and an add by
#     default; a PPC fmadd is spelt as one where the lifter means one.
#   - /bigobj on MSVC. A single lifted file routinely passes the 65,536-section
#     limit of the default object format.
#   - PORT_PPU_AVX2 (MotorStorm, 2026-11-22): AVX2+FMA for the lifted PPU code,
#     which turns on the SSE/FMA VMX float ops of ppu_vmx.h (toolkit patch #25)
#     and makes fma() one instruction. Contraction MUST stay off with -mfma.
#     The exe already needs such a CPU for the SPU side (PORT_SPU_AVX2).
#   - PORT_PPU_FAST_FP (MotorStorm, 2026-11-23): the lifter's PPU_FAST_FP, i.e. the scalar
#     FP ops without their three NaN tests each (the host's NaN is taken as it comes: which
#     of two NaN operands propagates and the sign of a new NaN may differ from PowerPC).
#   - /GS- (2026-11-23): no stack cookie in generated code (clang-cl puts one in every
#     function that holds a local array, and the lifted code has no buffer to overrun).
option(PORT_PPU_AVX2 "Build the lifted PPU sources with AVX2+FMA" ON)
option(PORT_PPU_FAST_FP "Lifted PPU scalar FP without the PowerPC NaN rules" ON)
set(PORT_PPU_FP_DEF "")
if(PORT_PPU_FAST_FP)
    set(PORT_PPU_FP_DEF ";/DPPU_FAST_FP")
endif()
if(MSVC AND PORT_PPU_AVX2)
    set_source_files_properties(${RECOMP_SOURCES} PROPERTIES
        COMPILE_OPTIONS "/w;/bigobj;/GS-;-mavx2;-mfma;/clang:-ffp-contract=off${PORT_PPU_FP_DEF}")
elseif(MSVC)
    set_source_files_properties(${RECOMP_SOURCES} PROPERTIES
        COMPILE_OPTIONS "/w;/bigobj")
else()
    set_source_files_properties(${RECOMP_SOURCES} PROPERTIES
        COMPILE_OPTIONS "-w;-ffp-contract=off")
endif()

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
install(TARGETS ${PROJECT_NAME} RUNTIME DESTINATION bin)

# ---------------------------------------------------------------------------
# The window launcher (macOS)
# ---------------------------------------------------------------------------
# A title that replaces its executable (sys_game_process_exitspawn, done by a
# port as an exec) loses its window with the old process image. The launcher
# holds the window for the whole session instead: it runs the port with
# PS3RECOMP_HOST_SURFACES set, the Metal backend renders into IOSurfaces it
# shares (libs/video/rsx_host_surface.h), and the image an exec brings up
# attaches to the same window again. One Objective-C file and no runtime
# library, so it builds in seconds:
#
#   ./MyGameRecomp_window [--title T] [--size WxH] -- ./MyGameRecomp <args>
if(APPLE)
    enable_language(OBJC)
    add_executable(${PROJECT_NAME}_window "${PS3RECOMP_DIR}/tools/host_window/host_window.m")
    target_include_directories(${PROJECT_NAME}_window PRIVATE "${PS3RECOMP_DIR}/libs/video")
    target_compile_definitions(${PROJECT_NAME}_window PRIVATE HOST_WINDOW_TITLE="${PROJECT_NAME}")
    target_compile_options(${PROJECT_NAME}_window PRIVATE -fobjc-arc -Wall -Wextra -Wno-unused-parameter)
    target_link_libraries(${PROJECT_NAME}_window PRIVATE
        "-framework AppKit" "-framework Metal" "-framework QuartzCore" "-framework IOSurface")
    install(TARGETS ${PROJECT_NAME}_window RUNTIME DESTINATION bin)
endif()
