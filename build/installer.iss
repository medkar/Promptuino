; Inno Setup script pour Promptuino
;
; Compilation (depuis la racine du repo, apres pyinstaller build/promptuinoui.spec) :
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build/installer.iss
;
; Produit : build/output/Promptuino-Setup.exe
;
; Le script suppose que dist/Promptuino/ existe (= sortie de PyInstaller).

#define MyAppName "Promptuino"
; Surchargeable par la CI : ISCC /DMyAppVersion=1.2.3 build/installer.iss
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "Mehdi Karim"
; Depot PUBLIC. NE PAS mettre PromptuinoUI : c'est le depot de travail,
; prive -- cette URL est visible depuis << Programmes et fonctionnalites >>.
#define MyAppURL "https://github.com/medkar/Promptuino"
#define MyAppExeName "Promptuino.exe"

[Setup]
; AppId : GUID unique du produit. NE PAS modifier entre versions
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
; Icone de l'assistant d'installation lui-meme (celle de l'app installee
; vient de l'exe, cf. UninstallDisplayIcon plus bas).
SetupIconFile=..\assets\logo\promptuino.ico
OutputDir=output
OutputBaseFilename=Promptuino-Setup
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
; Les MEMES 4 langues que l'application (ui/i18n.py). L'installeur
; n'en proposait que deux : un utilisateur espagnol ou italien voyait
; l'assistant en anglais alors que l'app, elle, lui parlait sa langue.
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[CustomMessages]
; ⚠️ Ce fichier DOIT etre enregistre en UTF-8 AVEC BOM : sans lui, Inno
; Setup 6 le lit comme de l'ANSI et les accents se perdent en silence.
; Constate le 2026-08-28 -- le titre << Desinstallation >> d'Inno avait
; son accent (il vient du .isl) alors que NOS chaines non.
; `%n` est le saut de ligne d'Inno.
french.DownloadModel=Téléchargement du modèle de recherche…
english.DownloadModel=Downloading the search model…
spanish.DownloadModel=Descargando el modelo de búsqueda…
italian.DownloadModel=Download del modello di ricerca…
french.UninstallEntry=Désinstaller %1
english.UninstallEntry=Uninstall %1
spanish.UninstallEntry=Desinstalar %1
italian.UninstallEntry=Disinstallare %1
french.RemoveKeys=Supprimer aussi vos clés d'API enregistrées ?%n%nElles sont stockées dans le Gestionnaire d'identifiants de Windows et ne sont PAS supprimées par défaut.
english.RemoveKeys=Also delete your saved API keys?%n%nThey are stored in the Windows Credential Manager and are NOT deleted by default.
spanish.RemoveKeys=¿Eliminar también sus claves de API guardadas?%n%nEstán almacenadas en el Administrador de credenciales de Windows y NO se eliminan de forma predeterminada.
italian.RemoveKeys=Eliminare anche le chiavi API salvate?%n%nSono memorizzate in Gestione credenziali di Windows e NON vengono eliminate per impostazione predefinita.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copie tout le contenu de dist/Promptuino/ vers {app}.
; Le ".." pointe vers la racine du repo depuis build/.
Source: "..\dist\Promptuino\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallEntry,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Telechargement du modele d'embeddings (~448 Mio) PENDANT l'install,
; pour que le premier double-clic ne se solde pas par une longue
; attente (TODO #74). C'est l'APPLICATION qui telecharge, via son mode
; --download-model : l'URL epinglee et l'empreinte SHA-256 n'existent
; qu'a un seul endroit, dans ui/onnx_setup.py.
;
; Pas de `postinstall` : l'etape s'execute d'elle-meme, sans case a
; cocher. Inno ne verifie PAS le code de sortie d'une entree [Run],
; donc un echec (reseau filtre d'etablissement, annulation) ne fait pas
; echouer l'installation -- l'app reproposera le telechargement a son
; premier lancement. C'est voulu : un installeur qui plante sur un
; reseau bloque serait pire que le probleme d'origine.
Filename: "{app}\{#MyAppExeName}"; Parameters: "--download-model"; StatusMsg: "{cm:DownloadModel}"; Flags: waituntilterminated

; Lance l'app a la fin de l'install (option cochee par defaut)
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// TODO #78 -- les cles d'API vivent dans le Gestionnaire d'identifiants
// Windows, jamais dans le dossier de l'application. Une desinstallation ne les
// emporte donc PAS, et rien ne l'annoncait a l'utilisateur : sur un poste
// partage, ca compte.
//
// On DEMANDE plutot que de supprimer d'office. Quelqu'un qui desinstalle pour
// reinstaller ailleurs, ou pour essayer une autre version, perdrait sinon une
// cle qu'il a peut-etre payee. MB_DEFBUTTON2 met << Non >> par defaut : une
// validation distraite CONSERVE les cles.
//
// ⚠️ C'est l'APPLICATION qui efface (--clear-credentials) : elle seule sait
// quels services elle a ecrits. Une liste recopiee ici aurait derive au
// premier fournisseur ajoute.
//
// ⚠️ Se declenche a usUninstall, AVANT la suppression des fichiers -- sinon
// l'executable appele n'existerait plus.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Code: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Le texte vient de [CustomMessages] : l'installeur parle les 4 langues
    // de l'app, et le desinstalleur reutilise celle choisie a l'installation.
    if MsgBox(CustomMessage('RemoveKeys'),
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      Exec(ExpandConstant('{app}\{#MyAppExeName}'), '--clear-credentials', '',
           SW_HIDE, ewWaitUntilTerminated, Code);
    end;
  end;
end;
