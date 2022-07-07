;Include Modern UI

  !include "MUI2.nsh"

!insertmacro MUI_LANGUAGE "English"

; This script is perhaps one of the simplest NSIs you can make. All of the
; optional settings are left to their default settings. 
;--------------------------------

; The name of the installer
Name "PolyPop Spotify Plugin"

; The file to write
OutFile "PolyPop Spotify Plugin Installer.exe"

; The default installation directory
InstallDir $Profile\PolyPop\UIX\Spotify\

; Set the icon of the installer
Icon "static/icon.ico"

; Request application privileges for Windows Vista
RequestExecutionLevel user

;--------------------------------

; Pages

;--------------------------------

;Pages

  !insertmacro MUI_PAGE_LICENSE "License.txt"
  !insertmacro MUI_PAGE_DIRECTORY
  !insertmacro MUI_PAGE_INSTFILES
  !insertmacro MUI_UNPAGE_CONFIRM
  !insertmacro MUI_UNPAGE_INSTFILES

;--------------------------------

; The stuff to install
Section "" ;No components page, name is not important
  
  ; Set output path to the installation directory.
  SetOutPath $INSTDIR
  File /r "C:\Users\Owner\PolyPop\UIX\PolyPop-Spotify-Plugin\Spotify\"
  File /r "C:\Users\Owner\PolyPop\UIX\PolyPop-Spotify-Plugin\ppspotify\dist\ppspotify.exe"
  
  SetOutPath $INSTDIR\static
  File /r "C:\Users\Owner\PolyPop\UIX\PolyPop-Spotify-Plugin\static\"
  
  SetOutPath $INSTDIR\templates
  File /r "C:\Users\Owner\PolyPop\UIX\PolyPop-Spotify-Plugin\templates\"
  
  
SectionEnd ; end the section

Section "Uninstall"

  Delete "$INSTDIR\*"

  RMDir "$INSTDIR"

SectionEnd