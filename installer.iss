; Script do Inno Setup — gera o instalador do Sistema Despachante.
; Compilar com o Inno Setup Compiler (ISCC.exe) depois de rodar o PyInstaller:
;   1) pyinstaller despachante.spec        -> gera dist\SistemaDespachante\
;   2) iscc installer.iss                  -> gera installer_output\SistemaDespachante_Setup.exe
;
; Baixe o Inno Setup em https://jrsoftware.org/isinfo.php

#define MyAppName "Sistema Despachante"
#define MyAppVersion "1.0.0"
#define MyAppExeName "SistemaDespachante.exe"

[Setup]
AppId={{6E6F7A2E-4F63-4B9A-9C10-DESPACHANTE01}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=installer_output
OutputBaseFilename=SistemaDespachante_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Instala só para o usuário atual por padrão — evita pedir senha de admin
; em máquinas onde o usuário não é administrador.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar ícone na área de trabalho"; GroupDescription: "Ícones adicionais:"; Flags: unchecked

[Files]
; Copia a pasta inteira gerada pelo PyInstaller (--onedir)
Source: "dist\SistemaDespachante\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Executar o {#MyAppName} agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove arquivos gerados em runtime dentro da pasta de instalação (logs, cache),
; mas NUNCA toca em %APPDATA%\SistemaDespachante — lá ficam banco de dados,
; uploads e backups do usuário, que devem sobreviver a uma desinstalação.
Type: filesandordirs; Name: "{app}\__pycache__"
