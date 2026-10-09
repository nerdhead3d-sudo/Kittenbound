; Installer di Kittenbound (Inno Setup 6).
; Si crea con installer/build.ps1, che prima impacchetta il gioco con PyInstaller.

#define AppName "Kittenbound"
#define AppVersion "0.3.0"
#define AppExe "Kittenbound.exe"

[Setup]
AppId={{F724EFE7-0306-4084-B562-5EB912D75052}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=nerdhead3d
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Installa anche senza permessi di amministratore (chiede dove, se serve)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=Kittenbound_Setup
SetupIconFile=kittenbound.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Kittenbound\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\docs\guida_tasti.txt"; DestDir: "{app}"; DestName: "Comandi.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Comandi"; Filename: "{app}\Comandi.txt"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
