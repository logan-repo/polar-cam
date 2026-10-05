; Polar Deer 설치 프로그램 (Inno Setup 6.5+)
;   - 사용자 단위 설치 (관리자 권한 불필요)
;   - ffmpeg가 없거나 필요한 기능(gfxcapture, libx264)이 없으면 자동으로 내려받아 앱 폴더에 설치
;
; 빌드: build.bat  (또는 ISCC.exe installer\polardeer.iss)

#define AppName "Polar Deer"
#define AppVersion "1.0.0"
#define AppExe "PolarDeer.exe"
#define AppUrl "https://github.com/logan-repo/polar-cam"

; 자동 설치용 ffmpeg (gyan.dev essentials 빌드: gfxcapture, ddagrab, libx264, NVENC/QSV/AMF 포함)
; 버전을 올릴 때는 URL과 SHA256을 함께 바꾼다.
;   gh api repos/GyanD/codexffmpeg/releases/tags/<버전> --jq '.assets[] | "\(.name) \(.digest)"'
#define FfmpegUrl "https://github.com/GyanD/codexffmpeg/releases/download/8.1.2/ffmpeg-8.1.2-essentials_build.zip"
#define FfmpegSha256 "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec"

[Setup]
AppId={{7B1F6C0E-5D2A-4F43-9B7E-2C1A8D6E4F90}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Polar Deer
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
DefaultDirName={autopf}\Polar Deer
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.18362
OutputDir=..\dist
OutputBaseFilename=PolarDeer-Setup-{#AppVersion}
SetupIconFile=..\assets\polardeer.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#AppVersion}

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
korean.FfmpegDownloading=ffmpeg 다운로드 중 (약 105MB)
korean.FfmpegDownloadingDesc=녹화에 필요한 ffmpeg가 이 PC에 없어 자동으로 내려받습니다.
korean.FfmpegDownloadFailed=ffmpeg를 내려받지 못했습니다.%n%nffmpeg 없이 계속 설치할까요? (나중에 ffmpeg.exe를 설치 폴더나 PATH에 직접 넣어야 녹화할 수 있습니다)
korean.FfmpegExtractFailed=ffmpeg 설치에 실패했습니다. 나중에 ffmpeg.exe를 설치 폴더나 PATH에 직접 넣어 주세요.
korean.FfmpegInstalling=ffmpeg 설치 중...
korean.SetupCancelled=설치가 취소되었습니다.
english.FfmpegDownloading=Downloading ffmpeg (about 105 MB)
english.FfmpegDownloadingDesc=ffmpeg, which is required for recording, was not found on this PC and is being downloaded.
english.FfmpegDownloadFailed=Failed to download ffmpeg.%n%nContinue installing without ffmpeg? (You will need to put ffmpeg.exe in the install folder or on PATH before you can record.)
english.FfmpegExtractFailed=Failed to install ffmpeg. Please put ffmpeg.exe in the install folder or on PATH later.
english.FfmpegInstalling=Installing ffmpeg...
english.SetupCancelled=Setup was cancelled.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 설치 과정에서 내려받아 넣은 ffmpeg
Type: files; Name: "{app}\ffmpeg.exe"

[Code]
var
  DownloadPage: TDownloadWizardPage;
  FfmpegDownloaded: Boolean;

{ 이 ffmpeg가 Polar Deer에 필요한 기능(창 녹화용 gfxcapture, CPU 인코딩용 libx264)을 갖췄는지 확인.
  Exe에 'ffmpeg'처럼 이름만 주면 PATH에서 찾는다.
  설치 프로그램 프로세스에서 직접 실행하면 WinGet이 PATH에 만드는 심볼릭 링크 형태의 ffmpeg.exe가
  실행되지 않아서, 파워셸을 거쳐 실행한다. 종료 코드 0 = 사용 가능. }
function FfmpegUsable(const Exe: String): Boolean;
var
  Args: String;
  RC: Integer;
begin
  { 파워셸이 PATH에서 찾은 뒤, 심볼릭 링크면 실제 대상 파일로 풀어서 실행한다 }
  Args := '-NoProfile -ExecutionPolicy Bypass -Command "try { ' +
    '$p = (Get-Command ''' + Exe + ''' -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source; ' +
    '$i = Get-Item -LiteralPath $p; if ($i.LinkType) { $p = @($i.Target)[0] }; ' +
    '$f = (& $p -hide_banner -filters 2>&1 | Out-String); ' +
    '$e = (& $p -hide_banner -encoders 2>&1 | Out-String); ' +
    'if (($f -match ''gfxcapture'') -and ($e -match ''libx264'')) { exit 0 } else { exit 2 } } catch { exit 3 }"';
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Args, '', SW_HIDE,
    ewWaitUntilTerminated, RC) and (RC = 0);
  Log('ffmpeg 검사: ' + Exe + ' -> ' + IntToStr(RC) + ' (0=사용 가능, 2=기능 부족, 3=실행 실패)');
end;

function NeedFfmpeg: Boolean;
var
  Local: String;
begin
  Result := True;
  Local := AddBackslash(ExpandConstant('{app}')) + 'ffmpeg.exe';
  if FileExists(Local) and FfmpegUsable(Local) then
  begin
    Log('ffmpeg: 설치 폴더의 ffmpeg 사용 가능');
    Result := False;
  end
  else if FfmpegUsable('ffmpeg') then
  begin
    Log('ffmpeg: PATH의 ffmpeg 사용 가능');
    Result := False;
  end
  else
    Log('ffmpeg: 사용 가능한 ffmpeg가 없어 내려받습니다');
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(CustomMessage('FfmpegDownloading'), CustomMessage('FfmpegDownloadingDesc'), nil);
end;

{ ffmpeg를 내려받는다. 성공하면 True. 사용자가 설치를 취소하기로 하면 Cancelled=True. }
function DownloadFfmpeg(var Cancelled: Boolean): Boolean;
begin
  Result := False;
  Cancelled := False;
  try
    if WizardSilent then
      DownloadTemporaryFile('{#FfmpegUrl}', 'ffmpeg.zip', '{#FfmpegSha256}', nil)
    else
    begin
      DownloadPage.Clear;
      DownloadPage.Add('{#FfmpegUrl}', 'ffmpeg.zip', '{#FfmpegSha256}');
      DownloadPage.Show;
      try
        DownloadPage.Download;
      finally
        DownloadPage.Hide;
      end;
    end;
    Result := True;
  except
    Log('ffmpeg 다운로드 실패: ' + GetExceptionMessage);
    if not WizardSilent then
    begin
      if DownloadPage.AbortedByUser then
        Cancelled := True
      else if SuppressibleMsgBox(CustomMessage('FfmpegDownloadFailed') + #13#10#13#10 + GetExceptionMessage,
                mbError, MB_YESNO, IDYES) = IDNO then
        Cancelled := True;
    end;
  end;
end;

{ 필요할 때만(사용 가능한 ffmpeg가 없을 때) 내려받는다. 이미 받았으면 다시 받지 않는다. }
procedure EnsureFfmpeg(var Cancelled: Boolean);
begin
  Cancelled := False;
  if FfmpegDownloaded then
    Exit;
  if NeedFfmpeg then
    FfmpegDownloaded := DownloadFfmpeg(Cancelled);
end;

{ 마법사 설치: '설치 준비 완료' 페이지에서 [설치]를 누르면 진행 막대와 함께 내려받는다 }
function NextButtonClick(CurPageID: Integer): Boolean;
var
  Cancelled: Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and (not WizardSilent) then
  begin
    EnsureFfmpeg(Cancelled);
    if Cancelled then
      Result := False;
  end;
end;

{ 무인 설치(/SILENT, /VERYSILENT)는 마법사 페이지를 거치지 않으므로 여기서 처리한다 }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Cancelled: Boolean;
begin
  Result := '';
  EnsureFfmpeg(Cancelled);
  if Cancelled then
    Result := CustomMessage('SetupCancelled');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Zip, Dest, Args: String;
  RC: Integer;
begin
  if (CurStep = ssPostInstall) and FfmpegDownloaded then
  begin
    WizardForm.StatusLabel.Caption := CustomMessage('FfmpegInstalling');
    Zip := ExpandConstant('{tmp}\ffmpeg.zip');
    Dest := ExpandConstant('{app}\ffmpeg.exe');
    { zip 안의 */bin/ffmpeg.exe 하나만 꺼내서 앱 폴더에 둔다 }
    Args := '-NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.IO.Compression.FileSystem; ' +
      '$z=[IO.Compression.ZipFile]::OpenRead(''' + Zip + '''); try { ' +
      '$e=$z.Entries | Where-Object { $_.FullName -like ''*/bin/ffmpeg.exe'' } | Select-Object -First 1; ' +
      '[IO.Compression.ZipFileExtensions]::ExtractToFile($e,''' + Dest + ''',$true) } finally { $z.Dispose() }"';
    if (not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Args, '', SW_HIDE,
          ewWaitUntilTerminated, RC)) or (RC <> 0) or (not FileExists(Dest)) then
    begin
      Log('ffmpeg 압축 해제 실패 (RC=' + IntToStr(RC) + ')');
      SuppressibleMsgBox(CustomMessage('FfmpegExtractFailed'), mbError, MB_OK, IDOK);
    end;
  end;
end;
