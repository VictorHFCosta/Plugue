"""Perfis: cartões da barra lateral e janela para criar ou editar um perfil.

Um perfil guarda até três partes: o fone ("saida"), o microfone ("entrada") e o
mixer. Uma parte com valor None não é trocada quando o perfil é aplicado.
"""
from __future__ import annotations

import copy
from tkinter import messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

from icones import icone, icone_branco
from tema import (AMARELO, AZUL, AZUL_FORTE, AZUL_TEXTO_FRACO, NEUTRO, NEUTRO_FORTE,
                  TEXTO, TEXTO_FRACO, VERMELHO)

if TYPE_CHECKING:
    from app import App

ICONES_PERFIL = ("estrela", "jogo", "musica", "microfone", "fone", "conversa", "pessoas",
                 "video", "trabalho", "casa", "raio")
PARTES = (("saida", "fone", "Fone"), ("entrada", "microfone", "Microfone"),
          ("mixer", "mixer", "Mixer"))
MAX_ATALHOS = 9


def curto(nome: str, limite: int = 30) -> str:
    """'Alto-falantes (PRO X Wireless Gaming Headset)' -> 'PRO X Wireless Gaming Headset'."""
    if "(" in nome and nome.endswith(")"):
        dentro = nome[nome.index("(") + 1:-1].strip()
        if dentro:
            nome = dentro
    return nome if len(nome) <= limite else nome[: limite - 1].rstrip() + "…"


def resumo_mixer(mixer: dict) -> str:
    entradas = sum(1 for canal in mixer["canais"] if canal["entrada"])
    estado = "ligado" if mixer["ligado"] else "desligado"
    return f"Mixer {estado} · {entradas} entrada{'' if entradas == 1 else 's'}"


def normalizar(perfil: dict) -> dict:
    """Completa perfis gravados por versões antigas do app."""
    perfil.setdefault("icone", "estrela")
    for chave, _, _ in PARTES:
        perfil.setdefault(chave, None)
    if perfil["icone"] not in ICONES_PERFIL:
        perfil["icone"] = "estrela"
    return perfil


class CartaoPerfil:
    """Cartão clicável de um perfil na barra lateral."""

    def __init__(self, app: "App", pai, indice: int, perfil: dict):
        self.app = app
        self.indice = indice
        self.perfil = perfil
        self.estado = None  # (ativo, alterado, sob o mouse) desenhado por último

        self.frame = ctk.CTkFrame(pai, corner_radius=8, fg_color=NEUTRO, border_width=2,
                                  border_color=NEUTRO)
        self.frame.pack(fill="x", padx=2, pady=4)
        self.frame.grid_columnconfigure(1, weight=1)

        self.simbolo = ctk.CTkLabel(self.frame, text="", width=26)
        self.simbolo.grid(row=0, column=0, padx=(10, 6), pady=(8, 0), sticky="w")
        self.nome = ctk.CTkLabel(self.frame, text=perfil["nome"], anchor="w",
                                 font=ctk.CTkFont(size=14, weight="bold"))
        self.nome.grid(row=0, column=1, sticky="ew", pady=(8, 0))
        texto_atalho = f"Ctrl+{indice + 1}" if indice < MAX_ATALHOS else ""
        self.atalho = ctk.CTkLabel(self.frame, text=texto_atalho, font=ctk.CTkFont(size=11))
        self.atalho.grid(row=0, column=2, padx=(4, 0), pady=(8, 0))
        self.botao_editar = ctk.CTkButton(self.frame, text="", width=26, height=26,
                                          fg_color="transparent", hover_color=NEUTRO_FORTE,
                                          command=lambda: app.editar_perfil(self.indice))
        self.botao_editar.grid(row=0, column=3, padx=(2, 6), pady=(8, 0))

        self.resumo: list[tuple[ctk.CTkLabel, str]] = []
        for linha, (chave, simbolo, _) in enumerate(PARTES, start=1):
            valor = perfil.get(chave)
            if valor is None:
                continue
            if chave == "mixer":
                texto = resumo_mixer(valor)
            else:
                texto = curto(app.cfg["nomes"].get(valor, "Dispositivo desconhecido"), 24)
                if not app.conectado(valor):
                    texto += " · desconectado"
            rotulo = ctk.CTkLabel(self.frame, text="  " + texto, compound="left", anchor="w",
                                  font=ctk.CTkFont(size=12), height=20)
            rotulo.grid(row=linha, column=1, columnspan=3, sticky="ew")
            self.resumo.append((rotulo, simbolo))

        self.alterado = ctk.CTkFrame(self.frame, fg_color="transparent")
        ctk.CTkLabel(self.alterado, text="Mudou desde que foi aplicado", text_color=AMARELO,
                     font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.botao_salvar = ctk.CTkButton(
            self.alterado, text="Guardar mudanças", image=icone("salvar", 13),
            height=26, font=ctk.CTkFont(size=12), fg_color=NEUTRO_FORTE,
            hover_color=("gray70", "gray36"), text_color=TEXTO,
            command=lambda: app.atualizar_perfil(self.indice))
        self.botao_salvar.pack(anchor="w", pady=(2, 0))
        self.espaco = ctk.CTkFrame(self.frame, fg_color="transparent", height=8)
        self.espaco.grid(row=9, column=0, columnspan=4)

        clicaveis = [self.frame, self.simbolo, self.nome, self.atalho] + [r for r, _ in self.resumo]
        for widget in clicaveis:
            widget.bind("<Button-1>", lambda _e: app.aplicar_perfil(self.indice))
        for widget in clicaveis + [self.botao_editar]:
            widget.bind("<Enter>", lambda _e: self._conferir_mouse(), add="+")
            widget.bind("<Leave>", lambda _e: self.frame.after(15, self._conferir_mouse),
                        add="+")

    def _sob_o_mouse(self) -> bool:
        x, y = self.frame.winfo_pointerxy()
        alvo = self.frame.winfo_containing(x, y)
        caminho = str(self.frame)
        return alvo is not None and str(alvo).startswith(caminho)

    def _conferir_mouse(self) -> None:
        if self.frame.winfo_exists() and self.estado:
            ativo, alterado, _ = self.estado
            self.estilo(ativo, alterado)

    def estilo(self, ativo: bool, alterado: bool) -> None:
        sob = self._sob_o_mouse()
        if self.estado == (ativo, alterado, sob):
            return
        self.estado = (ativo, alterado, sob)
        if ativo:
            fundo = AZUL_FORTE if sob else AZUL
        else:
            fundo = NEUTRO_FORTE if sob else NEUTRO
        texto, fraco = ("white", AZUL_TEXTO_FRACO) if ativo else (TEXTO, TEXTO_FRACO)
        desenhar = icone_branco if ativo else icone
        self.frame.configure(fg_color=fundo, border_color=AMARELO if alterado else fundo)
        self.simbolo.configure(image=desenhar(self.perfil["icone"], 20))
        self.nome.configure(text_color=texto)
        self.atalho.configure(text_color=fraco)
        self.botao_editar.configure(image=desenhar("mais_opcoes", 14),
                                    hover_color=AZUL_FORTE if ativo else ("gray70", "gray36"))
        for rotulo, simbolo in self.resumo:
            rotulo.configure(text_color=fraco, image=desenhar(simbolo, 13))
        if alterado:
            self.alterado.grid(row=8, column=1, columnspan=3, sticky="w", pady=(4, 0))
        else:
            self.alterado.grid_forget()


class EditorPerfil(ctk.CTkToplevel):
    """Janela para criar um perfil novo ou editar um existente."""

    def __init__(self, app: "App", indice: int | None = None):
        super().__init__(app)
        self.app = app
        self.indice = indice
        self.original = app.cfg["perfis"][indice] if indice is not None else None
        novo = self.original is None
        self.title("Novo perfil" if novo else "Editar perfil")
        self.resizable(False, False)
        self.transient(app)

        corpo = ctk.CTkFrame(self, fg_color="transparent")
        corpo.pack(fill="both", expand=True, padx=20, pady=16)
        forte = ctk.CTkFont(weight="bold")

        ctk.CTkLabel(corpo, text="Nome", font=forte).pack(anchor="w")
        self.var_nome = ctk.StringVar(value=self.original["nome"] if self.original
                                      else self._nome_sugerido())
        self.campo_nome = ctk.CTkEntry(corpo, textvariable=self.var_nome, width=440)
        self.campo_nome.pack(anchor="w", pady=(4, 12))

        ctk.CTkLabel(corpo, text="Ícone", font=forte).pack(anchor="w")
        grade = ctk.CTkFrame(corpo, fg_color="transparent")
        grade.pack(anchor="w", pady=(4, 12))
        self.icone_escolhido = self.original["icone"] if self.original else "estrela"
        self.botoes_icone: dict[str, ctk.CTkButton] = {}
        for nome in ICONES_PERFIL:
            botao = ctk.CTkButton(grade, text="", width=36, height=36,
                                  command=lambda n=nome: self._escolher_icone(n))
            botao.pack(side="left", padx=(0, 4))
            self.botoes_icone[nome] = botao
        self._escolher_icone(self.icone_escolhido)

        ctk.CTkLabel(corpo, text="O que este perfil troca", font=forte).pack(anchor="w")
        ctk.CTkLabel(corpo, text="Desmarque o que deve ficar como está ao aplicar o perfil.",
                     text_color=TEXTO_FRACO).pack(anchor="w")
        self.vars_parte: dict[str, ctk.BooleanVar] = {}
        self.valores: dict[str, ctk.CTkLabel] = {}
        for chave, simbolo, titulo in PARTES:
            linha = ctk.CTkFrame(corpo, fg_color="transparent")
            linha.pack(fill="x", pady=(8, 0))
            ctk.CTkLabel(linha, text="", image=icone(simbolo, 18), width=24).pack(side="left")
            var = ctk.BooleanVar(value=novo or self.original.get(chave) is not None)
            ctk.CTkCheckBox(linha, text=titulo, variable=var, width=120,
                            command=self._atualizar_valores).pack(side="left", padx=(6, 0))
            valor = ctk.CTkLabel(linha, text="", anchor="w", text_color=TEXTO_FRACO,
                                 wraplength=300, justify="left")
            valor.pack(side="left", fill="x", expand=True)
            self.vars_parte[chave] = var
            self.valores[chave] = valor

        self.var_agora = ctk.BooleanVar(value=False)
        if not novo:
            ctk.CTkCheckBox(corpo, text="Trocar pelo que está em uso agora",
                            variable=self.var_agora, command=self._atualizar_valores
                            ).pack(anchor="w", pady=(14, 0))

        self.erro = ctk.CTkLabel(corpo, text="", text_color=VERMELHO, anchor="w")
        self.erro.pack(fill="x", pady=(10, 0))

        botoes = ctk.CTkFrame(corpo, fg_color="transparent")
        botoes.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(botoes, text="Salvar", width=100, command=self.salvar).pack(side="right")
        ctk.CTkButton(botoes, text="Cancelar", width=100, fg_color=NEUTRO,
                      hover_color=NEUTRO_FORTE, text_color=TEXTO,
                      command=self.destroy).pack(side="right", padx=(0, 8))
        if not novo:
            ctk.CTkButton(botoes, text="Excluir", image=icone("lixeira", 14), width=90,
                          fg_color="transparent", border_width=1, border_color=VERMELHO,
                          text_color=VERMELHO, hover_color=NEUTRO_FORTE,
                          command=self.excluir).pack(side="left")
            self.botao_subir = ctk.CTkButton(
                botoes, text="Subir", image=icone("subir", 12), width=80,
                fg_color="transparent", border_width=1, border_color=NEUTRO_FORTE,
                text_color=TEXTO, hover_color=NEUTRO_FORTE, command=self.subir)
            self.botao_subir.pack(side="left", padx=(8, 0))
            self._atualizar_subir()

        self._atualizar_valores()
        self.bind("<Return>", lambda _e: self.salvar())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_reqwidth()) // 2
        y = app.winfo_rooty() + (app.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.after(120, self._focar)

    def _focar(self) -> None:
        if not self.winfo_exists():
            return
        self.lift()
        self.campo_nome.focus_set()
        self.campo_nome.select_range(0, "end")
        try:
            self.grab_set()  # bloqueia a janela principal enquanto esta estiver aberta
        except Exception:
            pass

    def _nome_sugerido(self) -> str:
        usados = {p["nome"].lower() for p in self.app.cfg["perfis"]}
        numero = len(self.app.cfg["perfis"]) + 1
        while f"perfil {numero}" in usados:
            numero += 1
        return f"Perfil {numero}"

    def _escolher_icone(self, nome: str) -> None:
        self.icone_escolhido = nome
        for chave, botao in self.botoes_icone.items():
            escolhido = chave == nome
            botao.configure(image=icone_branco(chave, 18) if escolhido else icone(chave, 18),
                            fg_color=AZUL if escolhido else NEUTRO,
                            hover_color=AZUL_FORTE if escolhido else NEUTRO_FORTE)

    def _atualizar_subir(self) -> None:
        self.botao_subir.configure(state="normal" if self.indice else "disabled")

    def valor(self, chave: str):
        """O que será gravado nesta parte do perfil (None = não troca)."""
        if not self.vars_parte[chave].get():
            return None
        guardado = self.original.get(chave) if self.original else None
        if guardado is not None and not self.var_agora.get():
            return guardado
        return self.app.valor_atual(chave)

    def _atualizar_valores(self) -> None:
        for chave, rotulo in self.valores.items():
            valor = self.valor(chave)
            if valor is None:
                texto = "não muda"
            elif chave == "mixer":
                texto = resumo_mixer(valor)
            else:
                texto = self.app.nome_dispositivo(valor)
            rotulo.configure(text=texto)

    def salvar(self) -> None:
        nome = self.var_nome.get().strip()
        outros = {p["nome"].lower() for i, p in enumerate(self.app.cfg["perfis"])
                  if i != self.indice}
        if not nome:
            self.erro.configure(text="Dê um nome ao perfil.")
            return
        if nome.lower() in outros:
            self.erro.configure(text=f"Já existe um perfil chamado “{nome}”.")
            return
        perfil = {"nome": nome, "icone": self.icone_escolhido}
        for chave, _, _ in PARTES:
            perfil[chave] = copy.deepcopy(self.valor(chave))
        if all(perfil[chave] is None for chave, _, _ in PARTES):
            self.erro.configure(text="Marque pelo menos uma parte: fone, microfone ou mixer.")
            return
        self.app.gravar_perfil(self.indice, perfil)
        self.destroy()

    def excluir(self) -> None:
        if messagebox.askyesno("Plugue", f"Excluir o perfil “{self.original['nome']}”?",
                               parent=self):
            self.app.excluir_perfil(self.indice)
            self.destroy()

    def subir(self) -> None:
        if self.indice:
            self.app.mover_perfil(self.indice, -1)
            self.indice -= 1
            self._atualizar_subir()
