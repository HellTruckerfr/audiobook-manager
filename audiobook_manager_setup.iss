; Inno Setup script — Audiobook Manager
;
; Prérequis : lancer d'abord le build PyInstaller (dossier) :
;   python -m PyInstaller audiobook_manager.spec -y
;
; Puis compiler cet installeur :
;   iscc audiobook_manager_setup.iss
;
; Output : dist/AudiobookManager-Setup.exe

#define AppName      "Audiobook Manager"
#define AppVersion   "1.0.7"
#define AppPublisher "HellTrucker"
#define AppExeName   "AudiobookManager.exe"
#define SourceDir    "C:\Users\winte\workspace claude\audiobook-manager\dist\AudiobookManager"

[Setup]
AppId={{F3A2C8B1-4D7E-4F9A-B2C3-1A2B3C4D5E6F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/HellTruckerfr/audiobook-manager
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=C:\AudiobookManager-dist
OutputBaseFilename=AudiobookManager-Setup
SetupIconFile=assets\icons\audiobook-manager.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup

[Languages]
Name: "french";   MessagesFile: "compiler:Languages\French.isl"
Name: "english";  MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le Bureau"; GroupDescription: "Icônes supplémentaires :"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";         Filename: "{app}\{#AppExeName}"
Name: "{group}\Désinstaller";        Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";   Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Lancer {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
