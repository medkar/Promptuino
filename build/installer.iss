; Inno Setup script pour PromptuinoUI
;
; Compilation (depuis la racine du repo, apres pyinstaller build/promptuinoui.spec) :
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build/installer.iss
;
; Produit : build/output/PromptuinoUI-Setup.exe
;
; Le script suppose que dist/PromptuinoUI/ existe (= sortie de PyInstaller).

#define MyAppName "PromptuinoUI"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Mehdi Karim"
#define MyAppURL "https://github.com/medkar/PromptuinoUI"
#define MyAppExeName "PromptuinoUI.exe"

[Setup]
; AppId : GUID unique pour PromptuinoUI. NE PAS modifier entre versions
; (sinon l'install est consideree comme un autre logiciel et coexiste).
AppId={{F4A6E1B0-3C5D-4E1F-9A2B-7F8C9D0E1F23}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Install pour l'utilisateur courant si pas admin, sinon machine-wide.
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=output
OutputBaseFilename=PromptuinoUI-Setup
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
; Architecture : x64 only (PyInstaller a empaquete pour Win64)
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Permet la desinstallation propre
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
; Pas de Console / pas de logging excessif
SetupLogging=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copie tout le contenu de dist/PromptuinoUI/ vers {app}.
; Le ".." pointe vers la racine du repo depuis build/.
Source: "..\dist\PromptuinoUI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstaller {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Lance l'app a la fin de l'install (option cochee par defaut)
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
