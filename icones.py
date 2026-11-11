"""Ícones do app, desenhados a partir da fonte de ícones que já vem no Windows."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

# Códigos na fonte "Segoe MDL2 Assets" (os mesmos valem na "Segoe Fluent Icons").
CODIGOS = {
    "fone": 0xE7F6,
    "microfone": 0xE720,
    "virtual": 0xE93E,
    "mudo": 0xE74F,
    "mixer": 0xE9E9,
    "mais": 0xE710,
    "fechar": 0xE711,
    "salvar": 0xE74E,
    "olho": 0xE7B3,
    "estrela": 0xE734,
    "certo": 0xE73E,
    "abrir": 0xE8A7,
    "ajuda": 0xE946,
    "info": 0xE946,
    "aviso": 0xE7BA,
    "erro": 0xE783,
    "mais_opcoes": 0xE712,
    "editar": 0xE70F,
    "lixeira": 0xE74D,
    "subir": 0xE70E,
    # ícones que a pessoa pode escolher para um perfil
    "jogo": 0xE7FC,
    "musica": 0xE8D6,
    "conversa": 0xE8F2,
    "pessoas": 0xE716,
    "video": 0xE714,
    "trabalho": 0xE821,
    "casa": 0xE80F,
    "raio": 0xE945,
}
CLARO, ESCURO = "#1f1f1f", "#e6e6e6"
_ESCALA = 4  # desenha maior e deixa a tela reduzir: fica nítido em qualquer zoom


@lru_cache(maxsize=None)
def _fonte(pixels: int):
    pasta = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for arquivo in ("segmdl2.ttf", "SegoeIcons.ttf"):
        try:
            return ImageFont.truetype(str(pasta / arquivo), pixels)
        except OSError:
            continue
    return None


@lru_cache(maxsize=None)
def icone(nome: str, tamanho: int = 18, claro: str = CLARO, escuro: str = ESCURO):
    """Imagem do ícone para botões e rótulos (None se o Windows não tiver a fonte)."""
    pixels = tamanho * _ESCALA
    fonte = _fonte(pixels)
    if fonte is None:
        return None

    def desenhar(cor: str) -> Image.Image:
        if cor.startswith(("gray", "grey")) and cor[4:].isdigit():  # nomes do Tk, ex. gray40
            nivel = round(int(cor[4:]) * 255 / 100)
            cor = f"#{nivel:02x}{nivel:02x}{nivel:02x}"
        imagem = Image.new("RGBA", (pixels, pixels), (0, 0, 0, 0))
        ImageDraw.Draw(imagem).text((pixels / 2, pixels / 2), chr(CODIGOS[nome]), font=fonte,
                                    fill=cor, anchor="mm")
        return imagem

    return ctk.CTkImage(light_image=desenhar(claro), dark_image=desenhar(escuro),
                        size=(tamanho, tamanho))


def icone_branco(nome: str, tamanho: int = 18):
    """Versão para usar sobre fundo azul (item selecionado)."""
    return icone(nome, tamanho, "#ffffff", "#ffffff")
