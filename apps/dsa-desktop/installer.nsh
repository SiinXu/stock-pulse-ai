!macro customInstallMode
  ; Keep the install-dir wizard, but force a per-user install so runtime files
  ; stay under a user-writable location next to the packaged executable.
  StrCpy $isForceCurrentInstall 1
!macroend

!macro _dsaRetryQuotedOldUninstall ROOT_KEY SUFFIX
  ${if} $R0 == 0
    Return
  ${endif}

  ; electron-builder's default NSIS template passes _?=$installationDir
  ; without quotes. StockPulse and legacy "Daily Stock Analysis" per-user
  ; install paths can contain spaces, so old uninstallers can receive a split
  ; _? path and return code 2.
  DetailPrint "Retrying old uninstaller with quoted _? installation directory."
  !insertmacro readReg $R6 "${ROOT_KEY}" "${UNINSTALL_REGISTRY_KEY}" UninstallString
  ${if} $R6 == ""
    !ifdef UNINSTALL_REGISTRY_KEY_2
      !insertmacro readReg $R6 "${ROOT_KEY}" "${UNINSTALL_REGISTRY_KEY_2}" UninstallString
    !endif
  ${endif}
  ${if} $R6 == ""
    Goto DsaQuotedUninstallFailed_${SUFFIX}
  ${endif}

  !insertmacro GetInQuotes $R7 "$R6"
  !insertmacro readReg $R8 "${ROOT_KEY}" "${INSTALL_REGISTRY_KEY}" InstallLocation
  ${if} $R8 == ""
  ${andIf} $R7 != ""
    Push $R7
    Call GetFileParent
    Pop $R8
  ${endif}
  ${if} $R8 == ""
  ${orIf} $R7 == ""
    Goto DsaQuotedUninstallFailed_${SUFFIX}
  ${endif}

  ${if} $installMode == "CurrentUser"
  ${orIf} "${ROOT_KEY}" == "HKEY_CURRENT_USER"
    StrCpy $R9 "/currentuser"
  ${else}
    StrCpy $R9 "/allusers"
  ${endif}
  ${if} ${isDeleteAppData}
    StrCpy $R9 "$R9 --delete-app-data"
  ${else}
    StrCpy $R9 "$R9 --updated"
  ${endif}

  StrCpy $R5 "$PLUGINSDIR\old-uninstaller-quoted.exe"
  !insertmacro copyFile "$R7" "$R5"
  ClearErrors
  ExecWait '"$R5" /S /KEEP_APP_DATA $R9 "_?=$R8"' $R0
  IfErrors 0 DsaQuotedUninstallResult_${SUFFIX}

  ClearErrors
  ExecWait '"$R7" /S /KEEP_APP_DATA $R9 "_?=$R8"' $R0
  IfErrors DsaQuotedUninstallFailed_${SUFFIX} DsaQuotedUninstallResult_${SUFFIX}

DsaQuotedUninstallResult_${SUFFIX}:
  ${if} $R0 == 0
    Return
  ${endif}

DsaQuotedUninstallFailed_${SUFFIX}:
  MessageBox MB_OK|MB_ICONEXCLAMATION "$(uninstallFailed): $R0"
  DetailPrint "Quoted old uninstaller retry failed with code: $R0."
  SetErrorLevel 2
  Quit
!macroend

!macro customUnInstallCheck
  !insertmacro _dsaRetryQuotedOldUninstall SHELL_CONTEXT Shell
!macroend

!macro customUnInstallCheckCurrentUser
  !insertmacro _dsaRetryQuotedOldUninstall HKEY_CURRENT_USER CurrentUser
!macroend

!macro customInstall
  ; electron-builder's protocols option is macOS-only. Register the per-user
  ; Windows URL handler explicitly and quote both the executable and URL.
  WriteRegStr SHELL_CONTEXT "Software\Classes\stockpulse" "" "URL:StockPulse Protocol"
  WriteRegStr SHELL_CONTEXT "Software\Classes\stockpulse" "URL Protocol" ""
  WriteRegStr SHELL_CONTEXT "Software\Classes\stockpulse\DefaultIcon" "" '"$appExe",0'
  WriteRegStr SHELL_CONTEXT "Software\Classes\stockpulse\shell\open\command" "" '"$appExe" "%1"'
!macroend

!macro customUnInstall
  ; Preserve a handler that another installation has claimed since this one
  ; was installed. Only remove the command owned by the current install path.
  ReadRegStr $R0 SHELL_CONTEXT "Software\Classes\stockpulse\shell\open\command" ""
  StrCmp $R0 '"$INSTDIR\${APP_EXECUTABLE_FILENAME}" "%1"' 0 DsaProtocolUninstallDone
  DeleteRegKey SHELL_CONTEXT "Software\Classes\stockpulse"
DsaProtocolUninstallDone:
!macroend

!macro customHeader
; Reject system-protected directories (Program Files, Windows, etc.)
; to prevent runtime write failures for .env, data/ and logs/.
; .onVerifyInstDir is called on each change in the directory field;
; Abort grays out "Next" so the user cannot proceed with a blocked path.
Function .onVerifyInstDir
  Push $R0
  Push $R1

  ; --- Block $PROGRAMFILES (C:\Program Files on x64 installer) ---
  StrLen $R0 $PROGRAMFILES
  StrCpy $R1 $INSTDIR $R0
  StrCmp $R1 $PROGRAMFILES _dsa_reject

  ; --- Block $PROGRAMFILES64 ---
  StrLen $R0 $PROGRAMFILES64
  StrCpy $R1 $INSTDIR $R0
  StrCmp $R1 $PROGRAMFILES64 _dsa_reject

  ; --- Block $PROGRAMFILES32 (C:\Program Files (x86)) ---
  StrLen $R0 $PROGRAMFILES32
  StrCpy $R1 $INSTDIR $R0
  StrCmp $R1 $PROGRAMFILES32 _dsa_reject

  ; --- Block $WINDIR (C:\Windows and subdirectories) ---
  StrLen $R0 $WINDIR
  StrCpy $R1 $INSTDIR $R0
  StrCmp $R1 $WINDIR _dsa_reject

  Pop $R1
  Pop $R0
  Return

_dsa_reject:
  Pop $R1
  Pop $R0
  Abort
FunctionEnd
!macroend
