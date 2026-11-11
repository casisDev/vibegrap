; Instalador do VibeGrap  (Inno Setup 6)
; Compilar:  ISCC.exe /DAppVersion=2.0.0 installer.iss
; Pré-requisito: a pasta dist\VibeGrap (gerada pelo PyInstaller, já com ffmpeg e Deno dentro).

#define MyAppName "VibeGrap"
#define MyAppExe  "VibeGrap.exe"
#ifndef AppVersion
  #define AppVersion "2.0.0"
#endif

[Setup]
AppId={{6F1B2C9A-3D54-4E8B-9A71-2C5D8E0F4B17}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher=casisDev
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Instala só para o usuário atual, sem pedir senha de administrador (o usuário pode escolher "todos").
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer_output
OutputBaseFilename=VibeGrap-Setup
SetupIconFile=assets\VibeGrap_icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
; Os idiomas só entram se o arquivo existir nesta instalação do Inno Setup (assim o build nunca quebra).
#if FileExists(CompilerPath + "Languages\Portuguese.isl")
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"
#endif
#if FileExists(CompilerPath + "Languages\BrazilianPortuguese.isl")
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\VibeGrap\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Licenças e créditos (também mostrados dentro do programa, em Ferramentas > Licenças e créditos)
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
; Atualização feita pelo botão do próprio programa (instalação silenciosa): abre o programa de novo ao terminar.
Filename: "{app}\{#MyAppExe}"; Flags: nowait; Check: WizardSilent
