"""Configuração salva em disco: dispositivos ocultos, mixer e perfis."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

# Marca "use o dispositivo que estiver selecionado na lista de cima".
SELECIONADO = "@selecionado"


def _arquivo() -> Path:
    alternativo = os.environ.get("PLUGUE_CONFIG")
    if alternativo:
        return Path(alternativo)
    base = Path(os.environ.get("APPDATA") or str(Path.home()))
    arquivo = base / "Plugue" / "config.json"
    anterior = base / "ControleDeSom" / "config.json"  # nome antigo do programa
    if not arquivo.exists() and anterior.exists():
        try:
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(anterior, arquivo)
        except OSError:
            return anterior
    return arquivo


def canal_novo(entrada: str | None = None, monitor: bool = True) -> dict:
    return {"entrada": entrada, "volume": 100, "mudo": False, "monitor": monitor, "envio": True}


def mixer_padrao() -> dict:
    return {
        "ligado": False,
        # A voz não volta para o fone por padrão; o segundo canal (instrumento) volta.
        "canais": [canal_novo(SELECIONADO, monitor=False), canal_novo(None)],
        "monitor": SELECIONADO,
        "envio": None,
        "latencia": "Normal",
    }


def carregar() -> dict:
    cfg = {"ocultos": None, "nomes": {}, "perfis": [], "perfil_aplicado": None,
           "mixer": mixer_padrao()}
    try:
        lido = json.loads(_arquivo().read_text(encoding="utf-8-sig"))  # aceita arquivo com BOM
    except (OSError, ValueError):
        return cfg
    if isinstance(lido, dict):
        cfg.update({chave: valor for chave, valor in lido.items() if chave in cfg})
    return cfg


def salvar(cfg: dict) -> None:
    arquivo = _arquivo()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    temporario = arquivo.with_suffix(".tmp")
    temporario.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(arquivo)
