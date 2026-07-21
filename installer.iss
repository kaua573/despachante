; Script do Inno Setup — gera o instalador do Sistema Despachante.
; Compilar com o Inno Setup Compiler (ISCC.exe) depois de rodar o PyInstaller:
;   1) pyinstaller despachante.spec        -> gera dist\SistemaDespachante\
;   2) iscc installer.iss                  -> gera installer_output\SistemaDespachante_Setup.exe
;
; Baixe o Inno Setup em https://jrsoftware.org/isinfo.php

#define MyAppName "Sistema Controle Despachante"
#define MyAppVersion "1.0.1"
#define MyAppExeName "SistemaControleDespachante.exe"

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
LicenseFile=termo_de_uso.txt
InfoBeforeFile=mensagem_inicial.txt
InfoAfterFile=info_pos_instalacao.txt
; Mostra uma tela com o login padrão (admin / admin123) logo após copiar os
; arquivos, antes da tela final — assim quem instala já sai sabendo como
; acessar o sistema pela primeira vez.
; Instala só para o usuário atual por padrão — evita pedir senha de admin
; em máquinas onde o usuário não é administrador.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar ícone na área de trabalho"; GroupDescription: "Ícones adicionais:"; Flags: unchecked
Name: "redelocal"; Description: "Permitir acesso por outros computadores da rede local (recomendado só se outras pessoas do escritório vão usar o sistema)"; GroupDescription: "Rede:"; Flags: unchecked

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
; Remove arquivos gerados em runtime dentro da pasta de instalação (logs, cache).
; A pasta de dados (banco, backups, uploads) NUNCA é removida na desinstalação,
; esteja ela dentro de {app}\dados ou em outro local escolhido na instalação.
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
var
  DadosPage: TInputDirWizardPage;

procedure InitializeWizard;
begin
  { Tela extra, logo depois da escolha da pasta do programa, perguntando
    onde ficam o banco de dados e os backups automáticos. }
  DadosPage := CreateInputDirPage(wpSelectDir,
    'Local dos dados do sistema',
    'Onde o banco de dados e os backups automáticos devem ficar salvos?',
    'Por padrão os dados ficam numa subpasta dentro da instalação do programa. ' +
    'Se preferir, escolha outro local — por exemplo um HD externo ou uma segunda ' +
    'partição local.' + #13#10 + #13#10 +
    'Evite escolher uma pasta de rede (\\servidor\...) aqui: o banco de dados ' +
    'fica sendo acessado o tempo todo enquanto o sistema está aberto, e acesso via ' +
    'rede pode travar ou corromper o arquivo. Pastas de rede/nuvem são seguras só ' +
    'para guardar backups já prontos, não o banco em uso.',
    False, 'dados');
  DadosPage.Add('Pasta de dados:');
end;

procedure InitializeWizardAposSelecaoDePasta;
begin
  { Sugere a pasta padrão (subpasta "dados" dentro da instalação) só depois
    que o usuário já escolheu a pasta do programa na tela anterior, para o caminho sugerido
    já vir certo. }
  if DadosPage.Values[0] = '' then
    DadosPage.Values[0] := ExpandConstant('{app}') + '\dados';
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = DadosPage.ID then
    InitializeWizardAposSelecaoDePasta;
end;

function CaminhoDadosEscolhido(Param: String): String;
begin
  Result := DadosPage.Values[0];
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  PastaDados: String;
  ArquivoConfig: String;
begin
  if CurStep = ssPostInstall then
  begin
    PastaDados := DadosPage.Values[0];
    ForceDirectories(PastaDados);

    { Grava o local escolhido num arquivo simples ao lado do executável.
      config.py lê esse arquivo quando o sistema é aberto, para saber onde
      gravar banco de dados, uploads e backups. }
    ArquivoConfig := ExpandConstant('{app}') + '\local_dados.cfg';
    SaveStringToFile(ArquivoConfig, PastaDados, False);

    { Se a opção de rede local foi marcada, já deixa o interruptor ligado. }
    if WizardIsTaskSelected('redelocal') then
      SaveStringToFile(PastaDados + '\rede_local.flag', 'ativado', False);
  end;
end;
