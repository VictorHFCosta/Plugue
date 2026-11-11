"""Lista os dispositivos de áudio do Windows e troca o dispositivo padrão."""
from __future__ import annotations

from dataclasses import dataclass

import comtypes
from _ctypes import COMError
from comtypes import GUID
from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
from pycaw.api.mmdeviceapi.depend.structures import PROPERTYKEY
from pycaw.constants import CLSID_MMDeviceEnumerator, DEVICE_STATE, STGM, EDataFlow, ERole
from pycaw.utils import AudioUtilities

SAIDA = EDataFlow.eRender.value
ENTRADA = EDataFlow.eCapture.value

_CHAVE_NOME = PROPERTYKEY(GUID("{a45c254e-df1c-4efd-8020-67d146a850e0}"), 14)
_enumerador = None


@dataclass(frozen=True)
class Dispositivo:
    id: str
    nome: str


def _enum():
    global _enumerador
    if _enumerador is None:
        _enumerador = comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER
        )
    return _enumerador


def _nome(dev) -> str:
    valor = dev.OpenPropertyStore(STGM.STGM_READ.value).GetValue(_CHAVE_NOME)
    try:
        return valor.GetValue() or "(sem nome)"
    finally:
        valor.clear()


def listar(fluxo: int) -> list[Dispositivo]:
    """Dispositivos ativos (conectados e habilitados) de saída ou de entrada."""
    colecao = _enum().EnumAudioEndpoints(fluxo, DEVICE_STATE.ACTIVE.value)
    achados = []
    for i in range(colecao.GetCount()):
        try:
            dev = colecao.Item(i)
            achados.append(Dispositivo(dev.GetId(), _nome(dev)))
        except COMError:
            continue  # dispositivo sumiu no meio da listagem
    achados.sort(key=lambda d: d.nome.lower())
    return achados


def padrao(fluxo: int) -> str | None:
    """ID do dispositivo padrão do Windows, ou None se não houver nenhum."""
    try:
        return _enum().GetDefaultAudioEndpoint(fluxo, ERole.eConsole.value).GetId()
    except COMError:
        return None


def definir_padrao(id_dispositivo: str) -> None:
    """Torna o dispositivo o padrão do Windows (som geral e comunicação)."""
    AudioUtilities.SetDefaultDevice(
        id_dispositivo, [ERole.eConsole, ERole.eMultimedia, ERole.eCommunications]
    )
