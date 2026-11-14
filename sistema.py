"""Integração com o Windows: iniciar junto com o Windows e manter uma só cópia aberta."""
from __future__ import annotations

import ctypes
import os
import sys
import winreg
from ctypes import wintypes
from pathlib import Path

NOME = "Plugue"
# Argumento passado quando o Windows abre o Plugue no login: a janela já abre minimizada.
ARG_INICIO = "--inicio"
# O instalador usa o mesmo nome (AppMutex) para saber se o Plugue está aberto.
MUTEX = "Plugue-instancia"
_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.FindWindowW.restype = wintypes.HWND
_user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
_ERRO_JA_EXISTE = 183
_mutex = None  # fica aberto enquanto o processo vive


def _chave_run() -> str:
    # Os testes trocam a chave para não mexer na inicialização de verdade.
    return os.environ.get("PLUGUE_CHAVE_INICIO") or _RUN


def comando_inicio() -> str:
    """Linha de comando que o Windows executa no login."""
    if getattr(sys, "frozen", False):  # Plugue.exe
        return f'"{sys.executable}" {ARG_INICIO}'
    # Rodando do código-fonte: pythonw (sem janela de console) + app.py.
    python = Path(sys.executable)
    sem_console = python.with_name("pythonw.exe")
    if sem_console.exists():
        python = sem_console
    app = Path(__file__).with_name("app.py").resolve()
    return f'"{python}" "{app}" {ARG_INICIO}'


def comando_registrado() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _chave_run()) as chave:
            valor, _tipo = winreg.QueryValueEx(chave, NOME)
            return str(valor)
    except OSError:
        return None


def inicia_com_windows() -> bool:
    return comando_registrado() is not None


def definir_inicio(ativo: bool) -> None:
    """Liga ou desliga o início junto com o Windows (só para o usuário atual)."""
    if ativo:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _chave_run()) as chave:
            winreg.SetValueEx(chave, NOME, 0, winreg.REG_SZ, comando_inicio())
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _chave_run(), 0,
                            winreg.KEY_SET_VALUE) as chave:
            winreg.DeleteValue(chave, NOME)
    except FileNotFoundError:
        pass


def corrigir_caminho_inicio() -> None:
    """Se o início com o Windows aponta para outra cópia do Plugue.exe que não existe
    mais (pasta movida, versão antiga apagada), passa a apontar para esta."""
    if not getattr(sys, "frozen", False):
        return
    registrado = comando_registrado()
    if not registrado or registrado == comando_inicio():
        return
    exe = registrado.split('"')[1] if registrado.startswith('"') else registrado.split()[0]
    if not Path(exe).exists():
        definir_inicio(True)


def primeira_instancia() -> bool:
    """True se esta é a única cópia aberta. Se já houver outra, traz a janela dela para
    a frente e devolve False (quem chamou deve encerrar)."""
    global _mutex
    _mutex = _kernel32.CreateMutexW(None, False, MUTEX)
    if ctypes.get_last_error() != _ERRO_JA_EXISTE:
        return True
    janela = _user32.FindWindowW("TkTopLevel", NOME)
    if janela:
        _user32.ShowWindow(janela, 9)  # SW_RESTORE: desfaz o minimizado
        _user32.SetForegroundWindow(janela)
    return False
