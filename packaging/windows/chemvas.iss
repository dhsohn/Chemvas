; Compile the verified one-folder bundle; no source checkout is installed.
; ISCC /DBundleDir=... /DAppVersion=... /DOutputDir=... chemvas.iss
#ifndef BundleDir
  #error BundleDir must name the verified dist/chemvas directory.
#endif
#ifndef AppVersion
  #error AppVersion must match the bundled source version.
#endif
#ifndef OutputDir
  #error OutputDir must name a separate installer output directory.
#endif
#if Trim(BundleDir) == ""
  #error BundleDir must not be empty.
#endif
#if Trim(AppVersion) == ""
  #error AppVersion must not be empty.
#endif
#if Trim(OutputDir) == ""
  #error OutputDir must not be empty.
#endif
#if !FileExists(AddBackslash(BundleDir) + "chemvas.exe")
  #error BundleDir must contain chemvas.exe.
#endif
#define InstallerName "Chemvas-" + AppVersion + "-windows-x64-setup"
#if FileExists(AddBackslash(OutputDir) + InstallerName + ".exe")
  #error Refusing to overwrite an existing installer.
#endif

[Setup]
AppId=Chemvas
AppName=Chemvas
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher=Chemvas
AppPublisherURL=https://github.com/dhsohn/Chemvas
DefaultDirName={localappdata}\Programs\Chemvas
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
ChangesAssociations=yes
SetupIconFile=..\icons\chemvas.ico
UninstallDisplayIcon={app}\chemvas.exe
OutputDir={#OutputDir}
OutputBaseFilename={#InstallerName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
; Includes the dependency-license directory supplied by the bundle builder.
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Chemvas\Chemvas"; Filename: "{app}\chemvas.exe"

[Registry]
; Advertise an alternative handler. Windows retains the user's default choice.
Root: HKCU; Subkey: "Software\Classes\.chemvas\OpenWithProgids"; ValueType: string; ValueName: "Chemvas.Document"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\Chemvas.Document"; ValueType: string; ValueName: ""; ValueData: "Chemvas Drawing"
Root: HKCU; Subkey: "Software\Classes\Chemvas.Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\chemvas.exe"",0"
Root: HKCU; Subkey: "Software\Classes\Chemvas.Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\chemvas.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\Applications\chemvas.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Chemvas"
Root: HKCU; Subkey: "Software\Classes\Applications\chemvas.exe\SupportedTypes"; ValueType: string; ValueName: ".chemvas"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\Applications\chemvas.exe\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\chemvas.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Chemvas\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Chemvas"
Root: HKCU; Subkey: "Software\Chemvas\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Draw and edit chemical structures and reaction schemes."
Root: HKCU; Subkey: "Software\Chemvas\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: """{app}\chemvas.exe"",0"
Root: HKCU; Subkey: "Software\Chemvas\Capabilities\FileAssociations"; ValueType: string; ValueName: ".chemvas"; ValueData: "Chemvas.Document"
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "Chemvas"; ValueData: "Software\Chemvas\Capabilities"

[Code]
function RegistryStringMatches(const Key, ValueName, Expected: String): Boolean;
var
  Value: String;
begin
  Result := RegQueryStringValue(HKCU, Key, ValueName, Value) and
    (Value = Expected);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  OwnCommand, OwnIcon: String;
begin
  if CurUninstallStep <> usUninstall then
    Exit;
  OwnCommand := '"' + ExpandConstant('{app}\chemvas.exe') + '" "%1"';
  OwnIcon := '"' + ExpandConstant('{app}\chemvas.exe') + '",0';

  { Another portable installation may have taken over either open command. }
  if RegistryStringMatches(
    'Software\Classes\Chemvas.Document\shell\open\command', '', OwnCommand) then
  begin
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\Chemvas.Document');
    if RegistryStringMatches(
      'Software\Classes\.chemvas\OpenWithProgids', 'Chemvas.Document', '') then
      RegDeleteValue(HKCU, 'Software\Classes\.chemvas\OpenWithProgids', 'Chemvas.Document');
  end;
  if RegistryStringMatches(
    'Software\Classes\Applications\chemvas.exe\shell\open\command', '', OwnCommand) then
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\Applications\chemvas.exe');

  if RegistryStringMatches(
    'Software\Chemvas\Capabilities', 'ApplicationIcon', OwnIcon) then
  begin
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Chemvas\Capabilities');
    if RegistryStringMatches(
      'Software\RegisteredApplications', 'Chemvas', 'Software\Chemvas\Capabilities') then
      RegDeleteValue(HKCU, 'Software\RegisteredApplications', 'Chemvas');
  end;
end;
