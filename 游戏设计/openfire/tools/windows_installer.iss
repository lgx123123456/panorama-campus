#ifndef ReleaseDir
  #error Pass /DReleaseDir with the Windows player export directory.
#endif
#ifndef ReleaseVersion
  #error Pass /DReleaseVersion with the Godot project version.
#endif
#ifndef OutputPath
  #error Pass /DOutputPath with the installer output directory.
#endif

[Setup]
AppId={{E19A1DC9-A782-42FB-AE84-684429B61722}
AppName=一中东·余铃
AppVersion={#ReleaseVersion}
AppPublisher=OpenFire 校园还原项目
DefaultDirName={localappdata}\Programs\OpenFireCampus
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableDirPage=no
AppendDefaultDirName=no
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\余铃.exe
SetupIconFile=..\assets\ui\campus_library_icon.ico
OutputDir={#OutputPath}
OutputBaseFilename=Yuling-Setup-v{#ReleaseVersion}
WizardStyle=modern
Compression=lzma2/normal
SolidCompression=yes
RestartApplications=no
VersionInfoVersion={#ReleaseVersion}

[Languages]
Name: zhcn; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[CustomMessages]
zhcn.BrowseOrCreateFolder=选择或新建文件夹...
zhcn.BrowseOrCreateHint=可输入安装路径，也可点击右侧按钮选择或新建文件夹。
zhcn.DesktopShortcutOption=创建桌面快捷方式

[Tasks]
Name: desktopicon; Description: "{cm:DesktopShortcutOption}"; Flags: unchecked

[Files]
Source: "{#ReleaseDir}\余铃.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\EOSSDK-Win64-Shipping.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\godot_iroh.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\libeosg.windows.template_release.x86_64.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\xaudio2_9redist.dll"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\一中东·余铃"; Filename: "{app}\余铃.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\一中东·余铃"; Filename: "{app}\余铃.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\余铃.exe"; Description: "启动《一中东·余铃》"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
var
  DesktopShortcutCheck: TNewCheckBox;

procedure InitializeWizard;
var
  BrowseWidthIncrease: Integer;
begin
  { Keep the native folder picker and its Make New Folder action. }
  BrowseWidthIncrease := ScaleX(72);
  WizardForm.DirEdit.Width := WizardForm.DirEdit.Width - BrowseWidthIncrease;
  WizardForm.DirBrowseButton.Left := WizardForm.DirBrowseButton.Left - BrowseWidthIncrease;
  WizardForm.DirBrowseButton.Width := WizardForm.DirBrowseButton.Width + BrowseWidthIncrease;
  WizardForm.DirBrowseButton.Caption := CustomMessage('BrowseOrCreateFolder');
  WizardForm.SelectDirBrowseLabel.Caption := CustomMessage('BrowseOrCreateHint');

  DesktopShortcutCheck := TNewCheckBox.Create(WizardForm);
  DesktopShortcutCheck.Parent := WizardForm.SelectDirPage;
  DesktopShortcutCheck.Left := WizardForm.DirEdit.Left;
  DesktopShortcutCheck.Top := WizardForm.DirEdit.Top + WizardForm.DirEdit.Height + ScaleY(16);
  DesktopShortcutCheck.Width := WizardForm.DirEdit.Width;
  DesktopShortcutCheck.Height := ScaleY(20);
  DesktopShortcutCheck.Caption := CustomMessage('DesktopShortcutOption');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectDir then
    DesktopShortcutCheck.Checked := WizardIsTaskSelected('desktopicon');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  if (CurPageID = wpSelectDir) and not WizardSilent then begin
    if DesktopShortcutCheck.Checked then
      WizardSelectTasks('desktopicon')
    else
      WizardSelectTasks('!desktopicon');
  end;
  Result := True;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := PageID = wpSelectTasks;
end;
