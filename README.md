# Polar Deer

<img src="assets/polardeer_512.png" alt="Polar Deer" width="96" align="left">

워터마크 없는 가벼운 Windows 화면 녹화기. 영역 / 창(프로세스) / 전체 화면을 녹화하고, 화질과 전역 단축키를 설정할 수 있습니다.
ffmpeg를 직접 호출하며 파이썬 표준 라이브러리(tkinter)만 사용합니다.

<br clear="left">

## 설치

1. [Releases](https://github.com/logan-repo/polar-cam/releases/latest)에서 **`PolarDeer-Setup-*.exe`** 를 내려받아 실행합니다.
2. 끝입니다. **녹화에 필요한 ffmpeg가 이 PC에 없거나 기능이 부족하면 설치 프로그램이 자동으로 내려받아 설치합니다** (약 105MB, SHA256 검증).

- 관리자 권한이 필요 없습니다 (현재 사용자 폴더에 설치). 제거는 Windows "앱 및 기능"에서 하면 ffmpeg까지 함께 삭제됩니다.
- 코드 서명이 되어 있지 않아 처음 실행할 때 Windows SmartScreen 경고("알 수 없는 게시자")가 나올 수 있습니다. **추가 정보 → 실행**을 누르세요.
- 무인 설치: `PolarDeer-Setup-1.0.0.exe /VERYSILENT` (ffmpeg 자동 설치 포함)

## 필수 요구사항

설치 프로그램을 쓰면 **직접 설치할 것이 없습니다.** 아래는 각 항목의 상세입니다.

| 항목 | 필요 여부 | 설명 |
|---|---|---|
| **ffmpeg** | **필수** | 실제 녹화/인코딩을 담당. **설치 프로그램이 없거나 기능이 부족하면 자동 설치**합니다. 수동 사용 시 `PolarDeer.exe`와 같은 폴더에 `ffmpeg.exe`를 두거나 PATH에 등록 (`winget install Gyan.FFmpeg`) |
| Windows 10 1903 (빌드 18362) 이상, 64비트 | **필수** | 창(프로세스) 녹화에 쓰는 Windows Graphics Capture가 이 버전부터 Win32 앱에서 동작. Windows 11도 가능 |
| .NET (Framework / Runtime) | 불필요 | .NET 기반이 아님 |
| Python | 불필요 (설치 프로그램 / exe 사용 시) | Python 3.12 런타임과 Tcl/Tk가 exe에 번들됨. 소스(`run.bat`)로 실행할 때만 Python 3 + tkinter 필요 |
| Visual C++ 재배포 패키지 | 불필요 | `VCRUNTIME140.dll`이 exe에 번들됨. ffmpeg(gyan 정적 빌드)는 Windows 기본 DLL만 사용 |
| 관리자 권한 | 불필요 | |
| GPU 드라이버 (NVIDIA / Intel / AMD) | 선택 | 있으면 하드웨어 인코딩(NVENC / QSV / AMF) 자동 사용, 없으면 CPU(x264)로 자동 전환 |
| 폰트 | 불필요 | Windows 기본 폰트(맑은 고딕, Georgia) 사용 |

### ffmpeg 버전/빌드 조건

설치 프로그램은 다음을 확인하고, 조건을 만족하는 ffmpeg(설치 폴더 → PATH 순)가 있으면 내려받지 않습니다.

- **`gfxcapture` 필터 포함** (FFmpeg 8.1 이상). 창(프로세스) 녹화에 필요. 일부 Windows 빌드에는 빠져 있습니다 ([BtbN 이슈](https://github.com/BtbN/FFmpeg-Builds/issues/549)). 직접 확인: `ffmpeg -hide_banner -filters | findstr gfxcapture`
- **`libx264` 포함** (GPL 빌드). GPU 인코더가 없는 PC의 CPU 인코딩에 필요.
- 조건을 만족하는 ffmpeg가 없으면 [gyan.dev essentials 빌드 8.1.2](https://github.com/GyanD/codexffmpeg/releases/tag/8.1.2)(`ffmpeg-8.1.2-essentials_build.zip`)에서 `ffmpeg.exe` 하나만 꺼내 설치 폴더에 둡니다. 앱은 설치 폴더의 ffmpeg를 PATH보다 먼저 사용합니다.
- 구버전 / gfxcapture 미포함 ffmpeg를 수동으로 쓰면: 전체 화면·영역은 `gdigrab`으로 자동 폴백(성능 낮음)되지만, **창 녹화는 GPU 렌더링 앱(브라우저, Electron, 게임 등)이 흰/검은 화면**으로 나올 수 있습니다.
- ffmpeg는 이 저장소에 포함되어 있지 않습니다. 설치 시 위 공식 배포처에서 내려받으며, ffmpeg의 라이선스(GPL)는 해당 배포본을 따릅니다.

### 검증한 내용

- Python/ffmpeg가 PATH에 없는 환경에서 설치 프로그램이 ffmpeg를 내려받아(SHA256 검증) 설치하고, 설치된 앱이 2560x1440 녹화에 성공.
- PATH에 조건을 만족하는 ffmpeg가 있으면 내려받지 않고 건너뜀.
- 제거 시 설치 폴더(ffmpeg 포함), 시작 메뉴 바로 가기, 제거 정보가 모두 삭제됨.
- 테스트 환경: Windows 10 Pro 19045.

## 사용법

툴바에서 **영역 / 창 / 전체 화면**을 고르고 `녹화 시작`(또는 단축키). **설정**에서 화질·저장 폴더·단축키를 바꿉니다.
저장이 끝나면 하단의 파일명을 클릭해 폴더에서 바로 볼 수 있습니다.

| 모드 | 방식 |
|---|---|
| 영역 | 드래그로 선택 (Esc/우클릭 취소) |
| 창(프로세스) | 실행 중인 창 목록에서 선택. Windows Graphics Capture라서 GPU 앱·가려진 창도 녹화됨. 최소화된 창은 자동 복원 |
| 전체 화면 | 모니터 선택 가능. GPU 방식(ddagrab), 실패 시 gdigrab 자동 폴백 |

### 단축키 (설정에서 변경 가능)

| 기능 | 기본값 |
|---|---|
| 시작 / 정지 (현재 선택한 대상) | F9 |
| 영역 녹화 (영역을 고르면 바로 시작) | Win + Shift + R |
| 창 녹화 (현재 활성 창을 바로 녹화) | Win + Shift + E |
| 전체 화면 녹화 | Win + Shift + F |

녹화 중에는 어느 단축키를 눌러도 정지됩니다. 다른 프로그램이 쓰는 조합은 "(사용 불가)"로 표시되니 바꿔 주세요.

### 기타

- 화질: 품질 4단계, FPS 15/24/30/60, 크기 100/75/50%, 인코더(자동·NVENC·QSV·AMF·x264)
- 저장 위치 기본값: `내 비디오\PolarDeer` / 파일명 `PolarDeer_날짜_시간.mp4`
- 설정: `%APPDATA%\PolarDeer\settings.json`, 오류 로그: `%APPDATA%\PolarDeer\ffmpeg.log`

## 한계

- 오디오 녹음 없음. 필요하면 `build_commands()`에 ffmpeg 오디오 입력을 추가하면 됨.
- 전체 화면 독점(exclusive fullscreen) 게임은 검게 나올 수 있음 → 테두리 없는 창 모드로 실행.
- DRM 보호 영상(넷플릭스 등)은 검게 녹화됨.

## 소스에서 실행 / 빌드

```
polardeer.py        앱 본체 (tkinter + ctypes)
assets/             아이콘, 헤더 로고
installer/          Inno Setup 스크립트 (ffmpeg 자동 설치 로직 포함)
build.bat           exe + 설치 프로그램 빌드
run.bat             소스 실행
```

- 소스 실행: `run.bat` (Python 3 + tkinter, 3.12에서 테스트. ffmpeg는 PATH에 있어야 함)
- 빌드: `build.bat` (Python + PyInstaller(자동 설치) + [Inno Setup 6.5+](https://jrsoftware.org/isdl.php)) → `dist\PolarDeer.exe`, `dist\PolarDeer-Setup-<버전>.exe`
- 자동 설치할 ffmpeg 버전을 올리려면 `installer\polardeer.iss` 상단의 `FfmpegUrl`과 `FfmpegSha256`을 함께 수정합니다 (해시 조회: `gh api repos/GyanD/codexffmpeg/releases/tags/<버전> --jq '.assets[] | "\(.name) \(.digest)"'`).
