#define MyAppName "Sistema de Inventarios"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Sistema de Inventarios"
#define MyAppExeName "SistemaInventarios.exe"

[Setup]
AppId={{D7F2B0E1-8A1A-4B4B-A3A2-5E0F8B9C1201}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\\SistemaInventarios
DefaultGroupName={#MyAppName}
OutputDir=..\\installer_output
OutputBaseFilename=SistemaInventarios-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
UninstallDisplayIcon={app}\\{#MyAppExeName}

[Files]
Source: "..\\dist\\SistemaInventarios\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\\Sistema de Inventarios"; Filename: "{app}\\{#MyAppExeName}"
Name: "{commondesktop}\\Sistema de Inventarios"; Filename: "{app}\\{#MyAppExeName}"

[Run]
Filename: "{app}\\{#MyAppExeName}"; Description: "Iniciar Sistema de Inventarios"; Flags: nowait postinstall skipifsilent
