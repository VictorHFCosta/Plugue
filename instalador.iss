; Instalador do Plugue (Inno Setup 6). Gerado pelo construir.bat a partir de dist\Plugue.exe.
; Instala só para o usuário atual: não pede permissão de administrador.

#ifndef Versao
  #define Versao "1.0.0"
#endif

[Setup]
AppId={{8A02292B-07F6-4B1D-8068-66995198F0DE}
AppName=Plugue
AppVersion={#Versao}
AppVerName=Plugue {#Versao}
AppPublisher=Victor Costa
AppPublisherURL=https://github.com/VictorHFCosta/Plugue
AppSupportURL=https://github.com/VictorHFCosta/Plugue/issues
DefaultDirName={autopf}\Plugue
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=PlugueSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Plugue.exe
UninstallDisplayName=Plugue
; Mesmo nome que o Plugue usa para não abrir duas cópias: assim o instalador
; percebe quando ele está aberto e pede para fechar antes de atualizar ou remover.
AppMutex=Plugue-instancia
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "iniciar"; Description: "Iniciar o Plugue junto com o Windows (abre minimizado)"
Name: "atalho"; Description: "Criar atalho na área de trabalho"; Flags: unchecked

[Files]
Source: "dist\Plugue.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Plugue"; Filename: "{app}\Plugue.exe"
Name: "{autodesktop}\Plugue"; Filename: "{app}\Plugue.exe"; Tasks: atalho

[Registry]
; Mesmo valor que a chave "Iniciar com o Windows" do app liga e desliga.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Plugue"; ValueData: """{app}\Plugue.exe"" --inicio"; Tasks: iniciar
; Na desinstalação, remove o início automático mesmo que ele tenha sido ligado pelo app.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Plugue"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Plugue.exe"; Description: "Abrir o Plugue agora"; Flags: nowait postinstall skipifsilent
