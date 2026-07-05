; Inno Setup script for diskimage_explorer_x68k
; Build via: scripts/build-windows-installer.ps1

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName "diskimage_explorer_x68k"
#define AppPublisher "diskimage_explorer_x68k"
#define AppExeName "diskimage_explorer_x68k.exe"

[Setup]
AppId={{A9E2E4B6-9F4A-4E10-9E79-4A7A6E9D8F11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
DisableProgramGroupPage=yes
LicenseFile=
InfoAfterFile=
OutputDir=..\..\dist
OutputBaseFilename=diskimage_explorer_x68k-windows-setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\diskimage_explorer_x68k\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
