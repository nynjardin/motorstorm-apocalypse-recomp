@echo off
rem Build MotorStorm: Apocalypse (BCES00484) port with clang-cl + Ninja.
rem Usage: build.bat [configure]   -- "configure" forces a fresh CMake configure.
setlocal
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
set "PATH=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\Llvm\x64\bin;%PATH%"
set "ROOT=%~dp0"
set "BUILD=%ROOT%build"
rem Another build tree / another lift (an A/B exe that leaves port\build alone), both optional:
rem   PORT_BUILD_DIR=E:\ms_perf\lr\build   PORT_RECOMP_DIR=E:/ms_perf/lr/recomp_lr   (forward slashes)
if defined PORT_BUILD_DIR set "BUILD=%PORT_BUILD_DIR%"
set "RECOMP=I:/Projets/Recomp/MotorStorm/work/BCES00484/recomp"
if defined PORT_RECOMP_DIR set "RECOMP=%PORT_RECOMP_DIR%"

rem Profile-guided optimisation: when a merged profile exists (made by build_pgo.bat gen + a race +
rem build_pgo.bat merge, see docs/perf.md), the build uses it: +1 FPS in the race (2026-11-23).
rem A profile older than the sources is fine (changed functions are just compiled without it).
rem PORT_PGO=0 = plain build. Changing this needs "build.bat configure" (everything recompiles).
set "PGOF="
rem The profile's date goes into the flags (PORT_PGO_STAMP): Ninja does not track the profile
rem file, so without it a new profile + "build.bat configure" recompiled nothing.
set "PGOSTAMP="
for %%F in ("E:\ms_perf\pgo\ms.profdata") do set "PGOSTAMP=%%~tF"
set "PGOSTAMP=%PGOSTAMP: =_%"
set "PGOSTAMP=%PGOSTAMP:/=_%"
set "PGOSTAMP=%PGOSTAMP::=_%"
if not "%PORT_PGO%"=="0" if exist "E:\ms_perf\pgo\ms.profdata" set "PGOF=-fprofile-instr-use=E:/ms_perf/pgo/ms.profdata -Wno-profile-instr-unprofiled -Wno-profile-instr-out-of-date /DPORT_PGO_STAMP=%PGOSTAMP%"

rem PORT_SPU_FLOAT_FAST=<0|1|2> (environment): native SPU floats in the lifted SPU sources (see
rem CMakeLists.txt). Unset = keep what the build directory has; changing it needs "configure".
set "FFOPT="
if defined PORT_SPU_FLOAT_FAST set "FFOPT=-DPORT_SPU_FLOAT_FAST=%PORT_SPU_FLOAT_FAST%"
rem PORT_SPU_FLOAT_XCMP=<0|1|2> (environment): SPU float compares, 0 = host only (see
rem CMakeLists.txt; default 1). Unset at "configure" = 1.
if defined PORT_SPU_FLOAT_XCMP set "FFOPT=%FFOPT% -DPORT_SPU_FLOAT_XCMP=%PORT_SPU_FLOAT_XCMP%"
if defined PORT_SPU_LS_PROBES set "FFOPT=%FFOPT% -DPORT_SPU_LS_PROBES=%PORT_SPU_LS_PROBES%"
rem PORT_SPU_FLOAT_EXACT=<a,b,...> (environment): lifted SPU sources kept on the exact float
rem emulation (path fragments, see CMakeLists.txt). Unset at "configure" = none.
set "FXOPT=-DPORT_SPU_FLOAT_EXACT="
if defined PORT_SPU_FLOAT_EXACT set "FXOPT=-DPORT_SPU_FLOAT_EXACT=%PORT_SPU_FLOAT_EXACT%"

if "%1"=="configure" if exist "%BUILD%\CMakeCache.txt" del "%BUILD%\CMakeCache.txt"
if not exist "%BUILD%\CMakeCache.txt" (
  cmake -S "%ROOT%." -B "%BUILD%" -G Ninja ^
    -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl ^
    -DCMAKE_BUILD_TYPE=Release ^
    "-DCMAKE_C_FLAGS=/DWIN32 /D_WINDOWS %PGOF%" "-DCMAKE_CXX_FLAGS=/DWIN32 /D_WINDOWS /EHsc %PGOF%" ^
    -DPS3RECOMP_DIR=I:/Projets/Recomp/ps3recomp ^
    -DPS3RECOMP_FFMPEG_RUNTIME=ON "-DPS3RECOMP_FFMPEG_INCLUDE_DIR=E:/ms_perf/ffmpeg/ffmpeg-n8.1-latest-win64-lgpl-shared-8.1/include" ^
    -DRECOMP_DIR=%RECOMP% ^
    -DPython3_EXECUTABLE=I:/Projets/Recomp/.venv/Scripts/python.exe ^
    -DPORT_ENABLE_SPU=ON -DPORT_SPU_INPUTS= %FFOPT% "%FXOPT%" "-DPORT_SPU_FLOAT_EXACT_DEFS=%PORT_SPU_FLOAT_EXACT_DEFS%" || exit /b 1
rem SPU: lifted images live in port\spu\ (built by tools\build_spu_workloads.py --images
rem work\BCES00484\spu_images, which includes the raw WWS job PM wrapped as pm_wwsjob.elf).
)
rem Lifted TUs are huge: cap parallelism to keep memory in check.
cmake --build "%BUILD%" -j 10
