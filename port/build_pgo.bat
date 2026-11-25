@echo off
rem Profile-guided build of the port (clang-cl instrumentation PGO), in its own build
rem directories on E: -- port\build is never touched.
rem   build_pgo.bat gen   instrumented exe -> E:\ms_perf\pgo\build_gen\MotorStormApocalypse.exe
rem                       run it with LLVM_PROFILE_FILE=E:\ms_perf\pgo\raw\ms-%%p.profraw and let it
rem                       EXIT by itself (close the window: a killed process writes no profile)
rem   build_pgo.bat merge llvm-profdata merge of E:\ms_perf\pgo\raw\*.profraw -> E:\ms_perf\pgo\ms.profdata
rem   build_pgo.bat use   optimised exe  -> E:\ms_perf\pgo\build_use\MotorStormApocalypse.exe
rem See docs/perf.md "Profile-guided build".
setlocal
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
set "LLVM=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\Llvm\x64"
set "PATH=%LLVM%\bin;%PATH%"
set "ROOT=%~dp0"
set "PGO=E:\ms_perf\pgo"
if not exist "%PGO%\raw" mkdir "%PGO%\raw"

if "%1"=="merge" (
  llvm-profdata merge -o "%PGO%\ms.profdata" "%PGO%\raw" || exit /b 1
  dir "%PGO%\ms.profdata"
  exit /b 0
)
if "%1"=="gen" (
  set "BUILD=%PGO%\build_gen"
  set "XF=-fprofile-instr-generate -fprofile-list=E:/ms_perf/pgo/profile_list.txt"
  set "XL=/LIBPATH:\"%LLVM%\lib\clang\19\lib\windows\" clang_rt.profile-x86_64.lib"
) else if "%1"=="use" (
  set "BUILD=%PGO%\build_use"
  set "XF=-fprofile-instr-use=E:/ms_perf/pgo/ms.profdata -Wno-profile-instr-unprofiled -Wno-profile-instr-out-of-date"
  set "XL="
) else (
  echo usage: build_pgo.bat gen ^| merge ^| use
  exit /b 2
)
if not exist "%BUILD%\CMakeCache.txt" (
  cmake -S "%ROOT%." -B "%BUILD%" -G Ninja ^
    -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl ^
    -DCMAKE_BUILD_TYPE=Release ^
    "-DCMAKE_C_FLAGS=%XF%" "-DCMAKE_CXX_FLAGS=/EHsc %XF%" ^
    "-DCMAKE_EXE_LINKER_FLAGS=%XL%" ^
    -DPS3RECOMP_DIR=I:/Projets/Recomp/ps3recomp ^
    -DRECOMP_DIR=I:/Projets/Recomp/MotorStorm/work/BCES00484/recomp ^
    -DPython3_EXECUTABLE=I:/Projets/Recomp/.venv/Scripts/python.exe ^
    -DPORT_ENABLE_SPU=ON -DPORT_SPU_INPUTS= || exit /b 1
)
rem -k 0: keep going, so that one pass names every translation unit the compiler chokes on
rem (clang 19 crashes in the register allocator on a few giant lifted functions once they are
rem instrumented: list them in E:\ms_perf\pgo\profile_list.txt, "function:*func_XXXXXXXX*=skip").
cmake --build "%BUILD%" -j 10 -- -k 0
