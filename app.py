"""Plugue: troca rápida de fone/microfone, mixer de entradas e perfis."""
from __future__ import annotations

import copy
import math
import sys
import webbrowser
from tkinter import messagebox

import customtkinter as ctk

import dispositivos as disp
from config import SELECIONADO, canal_novo, carregar, salvar
from icones import icone, icone_branco
from mixer import Mixer
from perfis import MAX_ATALHOS, PARTES, CartaoPerfil, EditorPerfil, normalizar
from tema import (AZUL, AZUL_FORTE, CARTAO, FUNDO_MEDIDOR, NEUTRO, NEUTRO_FORTE,
                  SITUACOES, TEXTO, TEXTO_FRACO, VERDE, VERMELHO)

MIC_SELECIONADO = "Microfone escolhido acima"
FONE_SELECIONADO = "Fone escolhido acima"
SEM_OUVIR = "Não ouvir"
DESLIGADO = "Desligado"
SEM_VIRTUAL = "Nenhum instalado"
NENHUMA = "Nenhuma"
# Folga do buffer, em ms. "Baixo" responde mais rápido, mas pode dar estalos de vez
# em quando: com 15 ms não sobra margem quando dois blocos de áudio chegam juntos.
LATENCIAS = {"Baixo": 15, "Normal": 30, "Seguro": 60}
MAX_CANAIS = 4
# Trechos de nome que identificam dispositivos virtuais.
VIRTUAIS = ("voicemeeter", "steelseries sonar", "vb-audio", "cable ", "virtual")
SITE_VB_CABLE = "https://vb-audio.com/Cable/"


def _virtual(nome: str) -> bool:
    return any(marca in nome.lower() for marca in VIRTUAIS)


def _saida_do_cabo(microfone: str | None) -> str | None:
    """Nome da saída que alimenta um microfone virtual (None se não for virtual).

    Um "cabo virtual" é um par criado por um driver: o que toca na saída aparece no
    microfone. No VB-CABLE o par é "CABLE Input" (saída) e "CABLE Output" (microfone).
    """
    if not microfone:
        return None
    minusculo = microfone.lower()
    if "cable" in minusculo and "Output" in microfone:
        return microfone.replace("Output", "Input")
    if "virtual" in minusculo or "sonar" in minusculo:
        return microfone  # drivers que dão o mesmo nome aos dois lados
    return None


def _mesmo_cabo(entrada: str | None, saida: str | None) -> bool:
    """True se a entrada capta o que é enviado para a saída: reenviar daria microfonia."""
    return bool(saida) and _saida_do_cabo(entrada) == saida


def _nivel_visual(pico: float) -> float:
    """Converte o pico (0..1) para a barra, em escala de decibéis (-60 dB a 0 dB)."""
    if pico <= 1e-6:
        return 0.0
    return max(0.0, min(1.0, (20 * math.log10(pico) + 60) / 60))


class LinhaCanal:
    """Uma linha do mixer: entrada, volume, mudo, rotas e medidor."""

    def __init__(self, app: "App", pai, linha: int, dados: dict, removivel: bool):
        self.app = app
        self.dados = dados
        self.nivel = 0.0

        simbolo = ctk.CTkLabel(pai, text="", image=icone("microfone", 18), width=22)
        self.var_entrada = ctk.StringVar()
        self.menu = ctk.CTkOptionMenu(pai, variable=self.var_entrada, values=[NENHUMA],
                                      dynamic_resizing=False, command=self._mudou_entrada)
        self.slider = ctk.CTkSlider(pai, from_=0, to=400, number_of_steps=80, width=140,
                                    command=self._mudou_volume)
        self.slider.set(dados["volume"])
        self.rotulo_volume = ctk.CTkLabel(pai, text=f"{dados['volume']}%", width=46, anchor="e")
        self.var_mudo = ctk.BooleanVar(value=dados["mudo"])
        self.var_monitor = ctk.BooleanVar(value=dados["monitor"])
        self.var_envio = ctk.BooleanVar(value=dados["envio"])
        caixas = [
            ctk.CTkCheckBox(pai, text="", variable=var, width=22, checkbox_width=22,
                            checkbox_height=22, command=self._mudou_opcoes)
            for var in (self.var_mudo, self.var_monitor, self.var_envio)
        ]
        # Sem sinal, a barra fica da cor do fundo (a ponta arredondada pareceria som).
        self.cor_medidor = FUNDO_MEDIDOR
        self.medidor = ctk.CTkProgressBar(pai, width=110, height=10, fg_color=FUNDO_MEDIDOR,
                                          progress_color=FUNDO_MEDIDOR)
        self.medidor.set(0)
        self.remover = ctk.CTkButton(pai, text="", image=icone("fechar", 12), width=28, height=28,
                                     fg_color="transparent", hover_color=NEUTRO_FORTE,
                                     command=lambda: app.remover_canal(self.dados))

        simbolo.grid(row=linha, column=0, padx=(0, 8))
        self.menu.grid(row=linha, column=1, sticky="ew", pady=4)
        self.slider.grid(row=linha, column=2, padx=(12, 0))
        self.rotulo_volume.grid(row=linha, column=3, padx=(2, 10))
        for coluna, caixa in enumerate(caixas, start=4):
            caixa.grid(row=linha, column=coluna, padx=(14, 0))
        self.medidor.grid(row=linha, column=7, padx=(14, 4))
        if removivel:
            self.remover.grid(row=linha, column=8)
        self.widgets = [simbolo, self.menu, self.slider, self.rotulo_volume, *caixas,
                        self.medidor, self.remover]

    def destruir(self) -> None:
        for widget in self.widgets:
            widget.destroy()

    def _mudou_entrada(self, rotulo: str) -> None:
        self.dados["entrada"] = self.app.referencia(
            rotulo, self.app.rotulos_entrada, MIC_SELECIONADO, NENHUMA, self.dados["entrada"])
        self.app.mixer_alterado(reiniciar=True)

    def _mudou_volume(self, valor: float) -> None:
        self.dados["volume"] = int(round(valor))
        self.rotulo_volume.configure(text=f"{self.dados['volume']}%")
        self.app.mixer_alterado(reiniciar=False)

    def _mudou_opcoes(self) -> None:
        self.dados["mudo"] = self.var_mudo.get()
        self.dados["monitor"] = self.var_monitor.get()
        self.dados["envio"] = self.var_envio.get()
        self.app.mixer_alterado(reiniciar=False)

    def mostrar_nivel(self, pico: float) -> None:
        alvo = _nivel_visual(pico)
        novo = max(alvo, self.nivel - 0.05)  # a barra desce devagar
        if abs(novo - self.nivel) > 0.004:
            self.nivel = novo
            self.medidor.set(novo)
        cor = VERMELHO if pico >= 1.0 else VERDE if self.nivel > 0.004 else FUNDO_MEDIDOR
        if cor != self.cor_medidor:
            self.cor_medidor = cor
            self.medidor.configure(progress_color=cor)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Plugue")
        try:
            escala = self._get_window_scaling()
        except Exception:
            escala = 1.0
        # Abre centralizada e inteira dentro da tela (o Windows, por conta própria,
        # às vezes posiciona a janela com a parte de baixo atrás da barra de tarefas).
        largura = int(min(1280, self.winfo_screenwidth() / escala - 40))
        altura = max(700, int(min(860, self.winfo_screenheight() / escala - 110)))
        x = max(0, int((self.winfo_screenwidth() - largura * escala) / 2))
        y = max(0, int((self.winfo_screenheight() - altura * escala) / 2 - 40))
        self.geometry(f"{largura}x{altura}+{x}+{y}")
        self.minsize(1180, 700)

        self.cfg = carregar()
        self.cfg["perfis"] = [normalizar(perfil) for perfil in self.cfg["perfis"]]
        self.mixer = Mixer()
        self.saidas: list[disp.Dispositivo] = []
        self.entradas: list[disp.Dispositivo] = []
        self.padrao_saida: str | None = None
        self.padrao_entrada: str | None = None
        self.rotulos_entrada: dict[str, str] = {}
        self.rotulos_saida: dict[str, str] = {}
        # Microfones virtuais instalados: (nome do microfone, id do microfone, id da saída).
        self.cabos: list[tuple[str, str, str]] = []
        self.rotulos_virtual: dict[str, str] = {}  # nome do microfone -> id da saída
        self.linhas: list[LinhaCanal] = []
        self.cartoes: list[CartaoPerfil] = []
        self._assinatura = None
        self._plano = None  # (entradas, monitor, envio, folga) em uso pelo mixer
        self._ausentes: list[str] = []  # dispositivos do mixer que estão desconectados
        self._salvamento = None
        self._texto_status = ""

        self.fonte_secao = ctk.CTkFont(size=15, weight="bold")
        self.fonte_forte = ctk.CTkFont(weight="bold")
        self._montar()
        self._montar_canais()
        self._ciclo_dispositivos()
        self._ciclo_medidores()
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        for numero in range(1, MAX_ATALHOS + 1):
            self.bind(f"<Control-Key-{numero}>", lambda _e, i=numero - 1: self.aplicar_perfil(i))

    # ------------------------------------------------------------------ tela

    def _montar(self) -> None:
        self.grid_columnconfigure(0, weight=0, minsize=270)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(12, 4))
        ctk.CTkLabel(cabecalho, text="  Plugue", image=icone("mixer", 24),
                     compound="left", font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        ctk.CTkLabel(cabecalho, text="troque fone e microfone, junte entradas e guarde perfis",
                     text_color=TEXTO_FRACO).pack(side="left", padx=14, pady=(6, 0))

        self._montar_barra_perfis()

        self.principal = ctk.CTkFrame(self, fg_color="transparent")
        self.principal.grid(row=1, column=1, sticky="nsew", padx=(6, 16), pady=(6, 16))
        self.principal.grid_columnconfigure((0, 1), weight=1, uniform="colunas")
        self.principal.grid_rowconfigure(0, weight=1)

        self.listas = {}
        self.botoes_lista = {}
        secoes = ((disp.SAIDA, "fone", "Fone / saída de som"),
                  (disp.ENTRADA, "microfone", "Microfone / entrada de som"))
        for coluna, (fluxo, simbolo, titulo) in enumerate(secoes):
            quadro = ctk.CTkFrame(self.principal)
            quadro.grid(row=0, column=coluna, sticky="nsew", pady=(0, 6),
                        padx=(0, 6) if coluna == 0 else (6, 0))
            topo = ctk.CTkFrame(quadro, fg_color="transparent")
            topo.pack(fill="x", padx=14, pady=(12, 0))
            ctk.CTkLabel(topo, text="  " + titulo, image=icone(simbolo, 20), compound="left",
                         font=self.fonte_secao).pack(side="left")
            botao = ctk.CTkButton(topo, text="Editar lista", image=icone("olho", 14), width=96,
                                  height=26, fg_color="transparent", border_width=1,
                                  border_color=NEUTRO_FORTE, hover_color=NEUTRO_FORTE,
                                  text_color=TEXTO, command=lambda f=fluxo: self._editar_lista(f))
            botao.pack(side="right")
            ctk.CTkLabel(quadro, text="Clique para trocar. O azul é o que o Windows está usando.",
                         text_color=TEXTO_FRACO).pack(anchor="w", padx=14)
            lista = ctk.CTkScrollableFrame(quadro, fg_color="transparent", height=80)
            lista.pack(fill="both", expand=True, padx=6, pady=(2, 8))
            self.listas[fluxo] = lista
            self.botoes_lista[fluxo] = botao

        self._montar_mixer()

    def _montar_barra_perfis(self) -> None:
        barra = ctk.CTkFrame(self, width=270)
        barra.grid(row=1, column=0, sticky="nsew", padx=(16, 6), pady=(6, 16))
        barra.grid_propagate(False)
        barra.pack_propagate(False)
        ctk.CTkLabel(barra, text="  Perfis", image=icone("estrela", 20), compound="left",
                     font=self.fonte_secao).pack(anchor="w", padx=14, pady=(12, 0))
        ctk.CTkLabel(barra, text="Um clique troca fone, microfone e mixer de uma vez.",
                     text_color=TEXTO_FRACO, wraplength=235, justify="left", anchor="w"
                     ).pack(fill="x", padx=14, pady=(2, 8))
        ctk.CTkButton(barra, text="Novo perfil", image=icone_branco("mais", 13), height=32,
                      command=lambda: self.editar_perfil(None)).pack(fill="x", padx=14)
        self.lista_perfis = ctk.CTkScrollableFrame(barra, fg_color="transparent")
        self.lista_perfis.pack(fill="both", expand=True, padx=6, pady=(8, 4))
        ctk.CTkLabel(barra, text=f"Atalhos: Ctrl+1 a Ctrl+{MAX_ATALHOS} aplicam os perfis "
                                 "na ordem da lista.",
                     text_color=TEXTO_FRACO, wraplength=235, justify="left", anchor="w",
                     font=ctk.CTkFont(size=12)).pack(fill="x", padx=14, pady=(0, 12))

    def _passo(self, pai, numero: int, titulo: str, detalhe: str) -> None:
        """Título numerado de uma etapa do mixer."""
        faixa = ctk.CTkFrame(pai, fg_color="transparent")
        faixa.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(faixa, text=str(numero), width=24, height=24, corner_radius=12,
                     fg_color=AZUL, text_color="white", font=self.fonte_forte).pack(side="left")
        ctk.CTkLabel(faixa, text=titulo, font=self.fonte_forte).pack(side="left", padx=(8, 8))
        ctk.CTkLabel(faixa, text=detalhe, text_color=TEXTO_FRACO).pack(side="left")

    def _montar_mixer(self) -> None:
        quadro = ctk.CTkFrame(self.principal)
        quadro.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        mixer = self.cfg["mixer"]

        topo = ctk.CTkFrame(quadro, fg_color="transparent")
        topo.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(topo, text="  Mixer", image=icone("mixer", 20), compound="left",
                     font=self.fonte_secao).pack(side="left")
        ctk.CTkLabel(topo, text="junta várias entradas numa só (ex.: microfone + baixo)",
                     text_color=TEXTO_FRACO).pack(side="left", padx=10)
        self.var_ligado = ctk.BooleanVar(value=mixer["ligado"])
        ctk.CTkSwitch(topo, text="Ligado", variable=self.var_ligado,
                      command=self._alternar_mixer).pack(side="right")
        self.var_latencia = ctk.StringVar(
            value=mixer["latencia"] if mixer["latencia"] in LATENCIAS else "Normal")
        ctk.CTkOptionMenu(topo, variable=self.var_latencia, values=list(LATENCIAS), width=96,
                          command=self._mudou_latencia).pack(side="right", padx=(6, 24))
        ctk.CTkLabel(topo, text="Atraso do som", text_color=TEXTO_FRACO).pack(side="right")

        # Etapa 1: entradas
        self._passo(quadro, 1, "O que entra na mistura",
                    "Marque, em cada entrada, quem vai escutá-la.")
        self.quadro_canais = ctk.CTkFrame(quadro, fg_color="transparent")
        self.quadro_canais.pack(fill="x", padx=14)
        self.quadro_canais.grid_columnconfigure(1, weight=1)
        cabecalhos = ((1, None, "Entrada (microfone ou instrumento)", "w", TEXTO_FRACO),
                      (2, None, "Volume", "", TEXTO_FRACO),
                      (4, "mudo", " Mudo", "", TEXTO_FRACO),
                      (5, "fone", " Eu ouço", "", TEXTO),
                      (6, "virtual", " Outros ouvem", "", TEXTO),
                      (7, None, "Nível", "", TEXTO_FRACO))
        for coluna, simbolo, texto, lado, cor in cabecalhos:
            ctk.CTkLabel(self.quadro_canais, text=texto, text_color=cor, compound="left",
                         image=icone(simbolo, 15) if simbolo else None,
                         ).grid(row=0, column=coluna, sticky=lado,
                                padx=(14, 0) if coluna >= 4 else (12, 0) if coluna == 2 else 0)

        self.botao_adicionar = ctk.CTkButton(
            quadro, text="Adicionar entrada", image=icone("mais", 13), width=160, height=28,
            fg_color=NEUTRO, hover_color=NEUTRO_FORTE, text_color=TEXTO,
            command=self._adicionar_canal)
        self.botao_adicionar.pack(anchor="w", padx=14, pady=(4, 2))

        # Etapa 2: saídas
        self._passo(quadro, 2, "Para onde a mistura vai", "Você pode usar um, outro ou os dois.")
        destinos = ctk.CTkFrame(quadro, fg_color="transparent")
        destinos.pack(fill="x", padx=14)
        destinos.grid_columnconfigure((0, 1), weight=1, uniform="destinos")

        cartao_fone = ctk.CTkFrame(destinos, fg_color=CARTAO)
        cartao_fone.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ctk.CTkLabel(cartao_fone, text="  Eu ouço em", image=icone("fone", 18), compound="left",
                     font=self.fonte_forte).pack(anchor="w", padx=12, pady=(10, 4))
        self.var_monitor = ctk.StringVar()
        self.menu_monitor = ctk.CTkOptionMenu(
            cartao_fone, variable=self.var_monitor, values=[SEM_OUVIR], dynamic_resizing=False,
            command=self._mudou_monitor)
        self.menu_monitor.pack(fill="x", padx=12)
        ctk.CTkLabel(
            cartao_fone, justify="left", anchor="w", text_color=TEXTO_FRACO, wraplength=420,
            text="Toca neste fone as entradas marcadas em “Eu ouço”. É como você se escuta "
                 "tocando o baixo, por exemplo. Ninguém mais recebe esse som.",
        ).pack(fill="x", padx=12, pady=(6, 10))

        cartao_virtual = ctk.CTkFrame(destinos, fg_color=CARTAO)
        cartao_virtual.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(cartao_virtual, text="  Microfone virtual (os outros ouvem)",
                     image=icone("virtual", 18), compound="left", font=self.fonte_forte
                     ).pack(anchor="w", padx=12, pady=(10, 4))
        self.var_envio = ctk.StringVar()
        self.menu_envio = ctk.CTkOptionMenu(
            cartao_virtual, variable=self.var_envio, values=[SEM_VIRTUAL],
            dynamic_resizing=False, command=self._mudou_envio)
        self.menu_envio.pack(fill="x", padx=12)
        self.rotulo_virtual = ctk.CTkLabel(cartao_virtual, justify="left", anchor="w",
                                           text_color=TEXTO_FRACO, wraplength=420, text="")
        self.rotulo_virtual.pack(fill="x", padx=12, pady=(6, 4))
        self.botao_virtual = ctk.CTkButton(cartao_virtual, text="", height=28, fg_color=NEUTRO,
                                           hover_color=NEUTRO_FORTE, text_color=TEXTO,
                                           text_color_disabled=TEXTO_FRACO)
        self.botao_virtual.pack(anchor="w", padx=12, pady=(0, 10))

        self.faixa_status = ctk.CTkFrame(quadro, corner_radius=8)
        self.faixa_status.pack(fill="x", padx=14, pady=(12, 14))
        self.icone_status = ctk.CTkLabel(self.faixa_status, text="", width=22)
        self.icone_status.pack(side="left", anchor="n", padx=(12, 6), pady=8)
        self.rotulo_status = ctk.CTkLabel(self.faixa_status, text="", anchor="w",
                                          justify="left", wraplength=860)
        self.rotulo_status.pack(side="left", fill="x", expand=True, pady=6, padx=(0, 12))

    # ---------------------------------------------------- listas de dispositivos

    def _ciclo_dispositivos(self) -> None:
        try:
            self._atualizar_dispositivos()
        finally:  # um erro inesperado numa rodada não pode parar o acompanhamento
            self.after(1500, self._ciclo_dispositivos)

    def _atualizar_dispositivos(self) -> None:
        try:
            saidas, entradas = disp.listar(disp.SAIDA), disp.listar(disp.ENTRADA)
            padrao_saida, padrao_entrada = disp.padrao(disp.SAIDA), disp.padrao(disp.ENTRADA)
        except Exception as erro:  # o serviço de áudio do Windows pode estar reiniciando
            self._status(f"Não consegui ler os dispositivos de som: {erro}", "erro")
            return

        assinatura = (tuple(saidas), tuple(entradas), padrao_saida, padrao_entrada)
        if assinatura == self._assinatura:
            if self.cfg["mixer"]["ligado"]:
                if self._plano and not self.mixer.saudavel():
                    self._sincronizar_mixer(forcar=True)
                else:
                    self._mostrar_status_mixer()
            return

        self._assinatura = assinatura
        self.saidas, self.entradas = saidas, entradas
        self.padrao_saida, self.padrao_entrada = padrao_saida, padrao_entrada
        if self.cfg["ocultos"] is None:
            # Primeira vez: dispositivos virtuais começam ocultos nas listas.
            self.cfg["ocultos"] = [
                d.id for d in saidas + entradas
                if d.id not in (padrao_saida, padrao_entrada) and _virtual(d.nome)
            ]
        else:
            # Saída virtual que acabou de ser instalada (ex.: "CABLE Input") não é um
            # fone: fica fora da lista de fones até a pessoa decidir mostrar.
            self.cfg["ocultos"] += [
                d.id for d in saidas
                if d.id not in self.cfg["nomes"] and d.id != padrao_saida and _virtual(d.nome)
            ]
        for dispositivo in saidas + entradas:
            self.cfg["nomes"][dispositivo.id] = dispositivo.nome
        self._agendar_salvamento()

        self._desenhar_lista(disp.SAIDA)
        self._desenhar_lista(disp.ENTRADA)
        self._atualizar_menus()
        self._desenhar_perfis()
        self._sincronizar_mixer()

    def _dados_lista(self, fluxo: int):
        if fluxo == disp.SAIDA:
            return self.saidas, self.padrao_saida
        return self.entradas, self.padrao_entrada

    def _desenhar_lista(self, fluxo: int) -> None:
        lista = self.listas[fluxo]
        for filho in lista.winfo_children():
            filho.destroy()
        dispositivos, padrao = self._dados_lista(fluxo)
        ocultos = set(self.cfg["ocultos"] or ())
        visiveis = [d for d in dispositivos if d.id not in ocultos or d.id == padrao]
        escondidos = len(dispositivos) - len(visiveis)
        self.botoes_lista[fluxo].configure(
            text=f"Editar lista ({escondidos} ocultos)" if escondidos else "Editar lista",
            width=170 if escondidos else 110)
        if not visiveis:
            ctk.CTkLabel(lista, text="Nenhum dispositivo conectado.",
                         text_color=TEXTO_FRACO).pack(anchor="w", padx=8, pady=8)
        for dispositivo in visiveis:
            atual = dispositivo.id == padrao
            simbolo = ("virtual" if _virtual(dispositivo.nome)
                       else "fone" if fluxo == disp.SAIDA else "microfone")
            ctk.CTkButton(
                lista, text="  " + dispositivo.nome, anchor="w", height=36,
                image=icone_branco(simbolo, 18) if atual else icone(simbolo, 18),
                fg_color=AZUL if atual else NEUTRO,
                hover_color=AZUL_FORTE if atual else NEUTRO_FORTE,
                text_color="white" if atual else TEXTO,
                command=lambda d=dispositivo: self._escolher_padrao(d),
            ).pack(fill="x", padx=4, pady=3)

    def _fixar_microfone_dos_canais(self, novo_padrao: str) -> None:
        """Antes de um microfone virtual virar o padrão do Windows, troca “Microfone
        escolhido acima” pelo microfone real que estava em uso. Sem isso o canal passaria
        a captar o próprio microfone virtual e a sua voz sairia da mistura."""
        if novo_padrao not in {id_microfone for _, id_microfone, _ in self.cabos}:
            return
        anterior = self.padrao_entrada
        if not anterior or anterior == novo_padrao:
            return
        for canal in self.cfg["mixer"]["canais"]:
            if canal["entrada"] == SELECIONADO:
                canal["entrada"] = anterior

    def _escolher_padrao(self, dispositivo: disp.Dispositivo) -> None:
        self._fixar_microfone_dos_canais(dispositivo.id)
        try:
            disp.definir_padrao(dispositivo.id)
        except Exception as erro:
            messagebox.showerror("Plugue",
                                 f"O Windows não aceitou a troca para “{dispositivo.nome}”.\n\n{erro}")
            return
        self._atualizar_dispositivos()
        self._marcar_perfis()
        self._agendar_salvamento()

    def _editar_lista(self, fluxo: int) -> None:
        dispositivos, _ = self._dados_lista(fluxo)
        janela = ctk.CTkToplevel(self)
        janela.title("Dispositivos da lista")
        janela.geometry("560x460")
        janela.transient(self)
        janela.after(150, janela.lift)
        ctk.CTkLabel(janela, text="Marque os dispositivos que devem aparecer na lista.",
                     font=self.fonte_secao).pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(janela, text="O dispositivo padrão do momento aparece sempre.",
                     text_color=TEXTO_FRACO).pack(anchor="w", padx=16)
        quadro = ctk.CTkScrollableFrame(janela)
        quadro.pack(fill="both", expand=True, padx=12, pady=12)

        def alternar(id_dispositivo: str, var: ctk.BooleanVar) -> None:
            ocultos = set(self.cfg["ocultos"] or ())
            if var.get():
                ocultos.discard(id_dispositivo)
            else:
                ocultos.add(id_dispositivo)
            self.cfg["ocultos"] = sorted(ocultos)
            self._desenhar_lista(fluxo)
            self._agendar_salvamento()

        ocultos = set(self.cfg["ocultos"] or ())
        for dispositivo in dispositivos:
            var = ctk.BooleanVar(value=dispositivo.id not in ocultos)
            ctk.CTkCheckBox(quadro, text=dispositivo.nome, variable=var,
                            command=lambda i=dispositivo.id, v=var: alternar(i, v)
                            ).pack(anchor="w", padx=8, pady=5)
        ctk.CTkButton(janela, text="Fechar", command=janela.destroy).pack(pady=(0, 14))

    # ------------------------------------------------------- microfone virtual

    def _atualizar_cartao_virtual(self) -> None:
        """Explica, conforme a situação, o que fazer com o microfone virtual."""
        envio = self.cfg["mixer"]["envio"]
        cabo = next((c for c in self.cabos if c[2] == envio), None)
        estado = "normal"
        if not self.cabos:
            texto = ("Ainda não há microfone virtual neste computador. O Windows só cria um "
                     "por meio de um driver: o VB-CABLE faz isso e instala em 2 minutos.")
            botao, simbolo, comando = "Como criar um microfone virtual", "ajuda", self._ajuda_virtual
        elif cabo is None:
            texto = ("Escolha acima um microfone virtual. Discord, OBS e outros programas "
                     "passam a receber por ele as entradas marcadas em “Outros ouvem”.")
            botao, simbolo, comando = "Como criar outro microfone virtual", "ajuda", self._ajuda_virtual
        else:
            nome, id_microfone, _ = cabo
            texto = (f"Nos outros programas (Discord, OBS, gravador), escolha o microfone "
                     f"“{nome}”. Ele leva as entradas marcadas em “Outros ouvem”.")
            if id_microfone == self.padrao_entrada:
                botao, simbolo, comando = "Já é o microfone padrão do Windows", "certo", None
                estado = "disabled"
            else:
                botao, simbolo = "Tornar o microfone padrão do Windows", "microfone"
                comando = lambda: self._virtual_como_padrao(id_microfone)
        self.rotulo_virtual.configure(text=texto)
        self.botao_virtual.configure(text=botao, image=icone(simbolo, 14), command=comando,
                                     state=estado)

    def _virtual_como_padrao(self, id_microfone: str) -> None:
        self._fixar_microfone_dos_canais(id_microfone)
        try:
            disp.definir_padrao(id_microfone)
        except Exception as erro:
            messagebox.showerror("Plugue", f"O Windows não aceitou a troca.\n\n{erro}")
            return
        self._atualizar_dispositivos()
        self._marcar_perfis()
        self._agendar_salvamento()

    def _ajuda_virtual(self) -> None:
        janela = ctk.CTkToplevel(self)
        janela.title("Como criar um microfone virtual")
        janela.geometry("620x560")
        janela.transient(self)
        janela.after(150, janela.lift)
        ctk.CTkLabel(janela, text="  Como criar um microfone virtual", image=icone("virtual", 22),
                     compound="left", font=self.fonte_secao).pack(anchor="w", padx=18, pady=(16, 6))
        ctk.CTkLabel(
            janela, justify="left", anchor="w", wraplength=580,
            text="O Windows só cria microfones virtuais por meio de um driver, e nenhum "
                 "aplicativo consegue fazer isso sozinho. O VB-CABLE, da VB-Audio, é o mais "
                 "usado: funciona sem pagar e aceita doação de quem quiser contribuir.",
        ).pack(fill="x", padx=18)
        passos = (
            "Abra o site oficial pelo botão abaixo e baixe o arquivo “VBCABLE_Driver_Pack” "
            "(um .zip pequeno).",
            "Extraia todos os arquivos do .zip para uma pasta.",
            "Clique com o botão direito no instalador de 64 bits (VBCABLE_Setup_x64), escolha "
            "“Executar como administrador” e depois “Install Driver”.",
            "Reinicie o computador.",
            "Abra o Plugue: o microfone aparece sozinho em “Microfone virtual”.",
        )
        for numero, passo in enumerate(passos, start=1):
            linha = ctk.CTkFrame(janela, fg_color="transparent")
            linha.pack(fill="x", padx=18, pady=(10, 0))
            ctk.CTkLabel(linha, text=str(numero), width=24, height=24, corner_radius=12,
                         fg_color=AZUL, text_color="white", font=self.fonte_forte
                         ).pack(side="left", anchor="n")
            ctk.CTkLabel(linha, text=passo, justify="left", anchor="w", wraplength=530
                         ).pack(side="left", padx=(10, 0), fill="x")
        ctk.CTkLabel(
            janela, justify="left", anchor="w", wraplength=580, text_color=TEXTO_FRACO,
            text="Quer mais de um? No mesmo site há o “Hi-Fi Cable” e os pacotes “VB-CABLE A+B” "
                 "e “C+D”. Cada cabo instalado vira mais um microfone virtual na lista; o mixer "
                 "alimenta um deles de cada vez.",
        ).pack(fill="x", padx=18, pady=(14, 0))
        botoes = ctk.CTkFrame(janela, fg_color="transparent")
        botoes.pack(side="bottom", fill="x", padx=18, pady=16)
        ctk.CTkButton(botoes, text="Abrir o site do VB-CABLE", image=icone_branco("abrir", 14),
                      command=lambda: webbrowser.open(SITE_VB_CABLE)).pack(side="left")
        ctk.CTkButton(botoes, text="Fechar", fg_color=NEUTRO, hover_color=NEUTRO_FORTE,
                      text_color=TEXTO, command=janela.destroy).pack(side="right")

    # ------------------------------------------------------------------ mixer

    @staticmethod
    def _rotular(dispositivos: list[disp.Dispositivo]) -> dict[str, str]:
        """Rótulo exibido -> id, sem repetir rótulos quando há nomes iguais."""
        rotulos: dict[str, str] = {}
        for dispositivo in dispositivos:
            rotulo, numero = dispositivo.nome, 2
            while rotulo in rotulos:
                rotulo = f"{dispositivo.nome} ({numero})"
                numero += 1
            rotulos[rotulo] = dispositivo.id
        return rotulos

    def _rotulo(self, ref: str | None, rotulos: dict[str, str], selecionado: str | None,
                vazio: str) -> str:
        if ref is None:
            return vazio
        if ref == SELECIONADO and selecionado:
            return selecionado
        for rotulo, id_dispositivo in rotulos.items():
            if id_dispositivo == ref:
                return rotulo
        return f"{self.cfg['nomes'].get(ref, 'Dispositivo')} (desconectado)"

    @staticmethod
    def referencia(rotulo: str, rotulos: dict[str, str], selecionado: str | None, vazio: str,
                   atual: str | None) -> str | None:
        if rotulo == vazio:
            return None
        if selecionado and rotulo == selecionado:
            return SELECIONADO
        return rotulos.get(rotulo, atual)  # rótulo "(desconectado)" mantém o que estava

    def _atualizar_menus(self) -> None:
        self.rotulos_entrada = self._rotular(self.entradas)
        self.rotulos_saida = self._rotular(self.saidas)
        saida_por_nome = {d.nome: d.id for d in self.saidas}
        self.cabos = [(d.nome, d.id, saida_por_nome[_saida_do_cabo(d.nome)])
                      for d in self.entradas if _saida_do_cabo(d.nome) in saida_por_nome]
        self.rotulos_virtual = {nome: id_saida for nome, _, id_saida in self.cabos}

        mixer = self.cfg["mixer"]
        # Versões antigas deixavam enviar a mistura para qualquer saída (até um fone).
        # Hoje esse destino é só microfone virtual: uma saída comum conectada sai daqui.
        if (mixer["envio"] in {d.id for d in self.saidas}
                and mixer["envio"] not in self.rotulos_virtual.values()):
            mixer["envio"] = None

        opcoes_entrada = [MIC_SELECIONADO, *self.rotulos_entrada, NENHUMA]
        for linha in self.linhas:
            linha.menu.configure(values=opcoes_entrada)
            linha.var_entrada.set(self._rotulo(linha.dados["entrada"], self.rotulos_entrada,
                                               MIC_SELECIONADO, NENHUMA))
        self.menu_monitor.configure(values=[SEM_OUVIR, FONE_SELECIONADO, *self.rotulos_saida])
        self.var_monitor.set(self._rotulo(mixer["monitor"], self.rotulos_saida,
                                          FONE_SELECIONADO, SEM_OUVIR))
        if self.cabos or mixer["envio"]:
            self.menu_envio.configure(values=[DESLIGADO, *self.rotulos_virtual], state="normal")
            self.var_envio.set(self._rotulo(mixer["envio"], self.rotulos_virtual, None, DESLIGADO))
        else:
            self.menu_envio.configure(values=[SEM_VIRTUAL], state="disabled")
            self.var_envio.set(SEM_VIRTUAL)
        self._atualizar_cartao_virtual()

    def _montar_canais(self) -> None:
        for linha in self.linhas:
            linha.destruir()
        canais = self.cfg["mixer"]["canais"]
        self.linhas = [LinhaCanal(self, self.quadro_canais, i + 1, canal,
                                  removivel=len(canais) > 1)
                       for i, canal in enumerate(canais)]
        self.botao_adicionar.configure(
            state="normal" if len(canais) < MAX_CANAIS else "disabled")
        self._atualizar_menus()

    def _adicionar_canal(self) -> None:
        self.cfg["mixer"]["canais"].append(canal_novo())
        self._montar_canais()
        self.mixer_alterado(reiniciar=True)

    def remover_canal(self, dados: dict) -> None:
        canais = self.cfg["mixer"]["canais"]
        self.cfg["mixer"]["canais"] = [canal for canal in canais if canal is not dados]
        self._montar_canais()
        self.mixer_alterado(reiniciar=True)

    def _alternar_mixer(self) -> None:
        self.cfg["mixer"]["ligado"] = self.var_ligado.get()
        self.mixer_alterado(reiniciar=True)

    def _mudou_monitor(self, rotulo: str) -> None:
        mixer = self.cfg["mixer"]
        mixer["monitor"] = self.referencia(rotulo, self.rotulos_saida, FONE_SELECIONADO,
                                           SEM_OUVIR, mixer["monitor"])
        self.mixer_alterado(reiniciar=True)

    def _mudou_envio(self, rotulo: str) -> None:
        mixer = self.cfg["mixer"]
        mixer["envio"] = self.referencia(rotulo, self.rotulos_virtual, None, DESLIGADO,
                                         mixer["envio"])
        self._atualizar_cartao_virtual()
        self.mixer_alterado(reiniciar=True)

    def _mudou_latencia(self, rotulo: str) -> None:
        self.cfg["mixer"]["latencia"] = rotulo
        self.mixer_alterado(reiniciar=True)

    def mixer_alterado(self, reiniciar: bool) -> None:
        if reiniciar:
            self._sincronizar_mixer()
        else:
            self._aplicar_ganhos()
            self._mostrar_status_mixer()
        self._marcar_perfis()
        self._agendar_salvamento()

    def _resolver(self):
        """Traduz a configuração para nomes de dispositivos conectados agora."""
        mixer = self.cfg["mixer"]
        nomes_entrada = {d.id: d.nome for d in self.entradas}
        nomes_saida = {d.id: d.nome for d in self.saidas}
        ausentes: list[str] = []

        def nome(ref, nomes, padrao):
            if ref is None:
                return None
            achado = nomes.get(padrao if ref == SELECIONADO else ref)
            if achado is None:
                ausentes.append("o dispositivo padrão" if ref == SELECIONADO
                                else self.cfg["nomes"].get(ref, "um dispositivo"))
            return achado

        entradas = tuple(nome(c["entrada"], nomes_entrada, self.padrao_entrada)
                         for c in mixer["canais"])
        monitor = nome(mixer["monitor"], nomes_saida, self.padrao_saida)
        envio = nome(mixer["envio"], nomes_saida, self.padrao_saida)
        folga = LATENCIAS.get(mixer["latencia"], LATENCIAS["Normal"])
        return (entradas, monitor, envio, folga), ausentes

    def _sincronizar_mixer(self, forcar: bool = False) -> None:
        """Liga, desliga ou reinicia o motor para refletir a configuração atual."""
        if not self.cfg["mixer"]["ligado"]:
            self.mixer.parar()
            self._plano = None
            self._status("Mixer desligado. Ligue a chave “Ligado” para começar.", "neutro")
            return

        plano, ausentes = self._resolver()
        entradas, monitor, envio, folga = plano
        self._ausentes = ausentes
        if not any(entradas) or not (monitor or envio):
            self.mixer.parar()
            self._plano = None
            if ausentes:
                self._status("Aguardando conectar: " + ", ".join(ausentes) + ".", "aviso")
            elif not any(entradas):
                self._status("Etapa 1: escolha pelo menos uma entrada para o mixer.", "aviso")
            else:
                self._status("Etapa 2: escolha um fone em “Eu ouço em” ou um microfone "
                             "virtual. Sem isso a mistura não tem para onde ir.", "aviso")
            return

        if not forcar and plano == self._plano and self.mixer.saudavel():
            self._aplicar_ganhos()
            self._mostrar_status_mixer()
            return
        try:
            self.mixer.iniciar(list(entradas), monitor, envio, folga)
        except Exception as erro:
            self.mixer.parar()
            self._plano = None
            self._status(f"Não consegui abrir os dispositivos: {erro}", "erro")
            return
        self._plano = plano
        self._aplicar_ganhos()
        self._mostrar_status_mixer()

    def _rotas(self):
        """Para cada canal em uso: (número, vai para o fone?, vai para o virtual?)."""
        entradas, monitor, envio, _ = self._plano
        for i, canal in enumerate(self.cfg["mixer"]["canais"]):
            if i >= len(entradas) or not entradas[i]:
                continue
            yield (i,
                   bool(monitor) and canal["monitor"] and not _mesmo_cabo(entradas[i], monitor),
                   bool(envio) and canal["envio"] and not _mesmo_cabo(entradas[i], envio))

    def _aplicar_ganhos(self) -> None:
        if not self._plano or not self.mixer.ativo:
            return
        canais = self.cfg["mixer"]["canais"]
        for i, no_fone, no_virtual in self._rotas():
            self.mixer.ajustar(i, canais[i]["volume"] / 100, canais[i]["mudo"],
                               no_fone, no_virtual)

    def _mostrar_status_mixer(self) -> None:
        if not self._plano or not self.mixer.ativo:
            return
        entradas, monitor, envio, _ = self._plano
        canais = self.cfg["mixer"]["canais"]
        rotas = list(self._rotas())
        microfone = next((nome for nome in self.rotulos_virtual
                          if _saida_do_cabo(nome) == envio), envio)

        partes = [f"Ligado: {sum(1 for e in entradas if e)} entrada(s)"]
        if monitor:
            partes.append(f"você ouve em {monitor}")
        if envio:
            partes.append(f"os outros ouvem pelo microfone “{microfone}”")
        linhas = [" · ".join(partes) + "."]
        cor = "ok"

        avisos = ((monitor, 1, "“Eu ouço”", "nada toca no seu fone"),
                  (envio, 2, "“Outros ouvem”", "o microfone virtual fica em silêncio"))
        for destino, coluna, nome_coluna, efeito in avisos:
            if not destino:
                continue
            marcadas = [rota[0] for rota in rotas if rota[coluna]]
            if not marcadas:
                linhas.append(f"Atenção: nenhuma entrada está marcada em {nome_coluna}, "
                              f"então {efeito}.")
                cor = "aviso"
            elif all(canais[i]["mudo"] for i in marcadas):
                linhas.append(f"Atenção: as entradas marcadas em {nome_coluna} estão no "
                              f"mudo, então {efeito}.")
                cor = "aviso"
        for i, entrada in enumerate(entradas, start=1):
            if _mesmo_cabo(entrada, envio):
                linhas.append(f"A entrada {i} é o próprio microfone virtual, então não é "
                              "mandada de volta para ele (evita microfonia).")
        if self._ausentes:
            linhas.append("Desconectado: " + ", ".join(self._ausentes) + ".")
            cor = "aviso"
        falhas = self.mixer.falhas()
        if falhas:
            linhas.append(f"Cortes no áudio até agora: {falhas}. Se continuar, aumente o "
                          "“Atraso do som”.")
        self._status("\n".join(linhas), cor)

    def _status(self, texto: str, tipo: str) -> None:
        """Mostra a situação do mixer. tipo: "ok", "aviso", "erro" ou "neutro"."""
        if (texto, tipo) == (self._texto_status, getattr(self, "_tipo_status", None)):
            return
        self._texto_status, self._tipo_status = texto, tipo
        fundo, cor, simbolo = SITUACOES[tipo]
        self.faixa_status.configure(fg_color=fundo)
        self.rotulo_status.configure(text=texto, text_color=cor)
        self.icone_status.configure(image=icone(simbolo, 16, cor[0], cor[1]))

    def _ciclo_medidores(self) -> None:
        try:
            niveis = self.mixer.niveis() if self.mixer.ativo else []
            for i, linha in enumerate(self.linhas):
                pico = niveis[i] if i < len(niveis) and niveis[i] is not None else 0.0
                linha.mostrar_nivel(pico * linha.dados["volume"] / 100)
        finally:
            self.after(60, self._ciclo_medidores)

    # ----------------------------------------------------------------- perfis

    def conectado(self, id_dispositivo: str) -> bool:
        return any(d.id == id_dispositivo for d in self.saidas + self.entradas)

    def nome_dispositivo(self, id_dispositivo: str) -> str:
        nome = self.cfg["nomes"].get(id_dispositivo, "Dispositivo desconhecido")
        return nome if self.conectado(id_dispositivo) else f"{nome} (desconectado)"

    def valor_atual(self, chave: str):
        """O que está em uso agora numa parte de perfil ("saida", "entrada" ou "mixer")."""
        if chave == "saida":
            return self.padrao_saida
        if chave == "entrada":
            return self.padrao_entrada
        return copy.deepcopy(self.cfg["mixer"])

    def _corresponde(self, perfil: dict) -> bool:
        """True se tudo o que o perfil troca já está exatamente como ele guarda."""
        return all(perfil[chave] is None or perfil[chave] == self.valor_atual(chave)
                   for chave, _, _ in PARTES)

    def _desenhar_perfis(self) -> None:
        for filho in self.lista_perfis.winfo_children():
            filho.destroy()
        self.cartoes = [CartaoPerfil(self, self.lista_perfis, indice, perfil)
                        for indice, perfil in enumerate(self.cfg["perfis"])]
        if not self.cartoes:
            ctk.CTkLabel(self.lista_perfis, text="Nenhum perfil ainda.", anchor="w",
                         font=self.fonte_forte).pack(fill="x", padx=8, pady=(6, 0))
            ctk.CTkLabel(self.lista_perfis, anchor="w", justify="left", wraplength=225,
                         text_color=TEXTO_FRACO,
                         text="Deixe fone, microfone e mixer do jeito que gosta e clique em "
                              "“Novo perfil”. Exemplos: “Jogo” com o fone sem fio, “Baixo” "
                              "com o mixer ligado.").pack(fill="x", padx=8, pady=4)
        self._marcar_perfis()

    def _marcar_perfis(self) -> None:
        """Pinta de azul os perfis em uso e marca o último aplicado se algo mudou."""
        aplicado = self.cfg["perfil_aplicado"]
        for cartao in self.cartoes:
            ativo = self._corresponde(cartao.perfil)
            cartao.estilo(ativo, alterado=not ativo and cartao.perfil["nome"] == aplicado)

    def editar_perfil(self, indice: int | None) -> None:
        EditorPerfil(self, indice)

    def gravar_perfil(self, indice: int | None, perfil: dict) -> None:
        perfis = self.cfg["perfis"]
        if indice is None:
            perfis.append(perfil)
            if self._corresponde(perfil):
                self.cfg["perfil_aplicado"] = perfil["nome"]
        else:
            if self.cfg["perfil_aplicado"] == perfis[indice]["nome"]:
                self.cfg["perfil_aplicado"] = perfil["nome"]
            perfis[indice] = perfil
        self._desenhar_perfis()
        self._agendar_salvamento()

    def atualizar_perfil(self, indice: int) -> None:
        """Guarda no perfil o que está em uso agora, nas partes que ele já troca."""
        perfil = self.cfg["perfis"][indice]
        for chave, _, _ in PARTES:
            if perfil[chave] is not None:
                perfil[chave] = self.valor_atual(chave)
        self._desenhar_perfis()
        self._agendar_salvamento()

    def excluir_perfil(self, indice: int) -> None:
        perfil = self.cfg["perfis"].pop(indice)
        if self.cfg["perfil_aplicado"] == perfil["nome"]:
            self.cfg["perfil_aplicado"] = None
        self._desenhar_perfis()
        self._agendar_salvamento()

    def mover_perfil(self, indice: int, passo: int) -> None:
        perfis = self.cfg["perfis"]
        destino = indice + passo
        if 0 <= destino < len(perfis):
            perfis[indice], perfis[destino] = perfis[destino], perfis[indice]
            self._desenhar_perfis()
            self._agendar_salvamento()

    def aplicar_perfil(self, indice: int) -> None:
        if not 0 <= indice < len(self.cfg["perfis"]):
            return
        perfil = self.cfg["perfis"][indice]
        conectados = {d.id for d in self.saidas + self.entradas}
        falhas = []
        for chave in ("saida", "entrada"):
            id_dispositivo = perfil[chave]
            if id_dispositivo is None or id_dispositivo == self.valor_atual(chave):
                continue
            if chave == "entrada":
                self._fixar_microfone_dos_canais(id_dispositivo)
            try:
                if id_dispositivo not in conectados:
                    raise LookupError
                disp.definir_padrao(id_dispositivo)
            except Exception:
                falhas.append(self.cfg["nomes"].get(id_dispositivo, "dispositivo"))

        if perfil["mixer"] is not None:
            self.cfg["mixer"] = copy.deepcopy(perfil["mixer"])
            self.var_ligado.set(self.cfg["mixer"]["ligado"])
            self.var_latencia.set(self.cfg["mixer"]["latencia"])
            self._montar_canais()
        self.cfg["perfil_aplicado"] = perfil["nome"]
        self._assinatura = None  # força redesenho com o novo padrão
        self._atualizar_dispositivos()
        self._agendar_salvamento()
        if falhas:
            messagebox.showwarning(
                "Plugue",
                "Não consegui selecionar (desconectado?):\n\n" + "\n".join(falhas)
                + "\n\nO restante do perfil foi aplicado.")

    # ------------------------------------------------------------ salvamento

    def _agendar_salvamento(self) -> None:
        if self._salvamento is not None:
            self.after_cancel(self._salvamento)
        self._salvamento = self.after(500, self._salvar_agora)

    def _salvar_agora(self) -> None:
        self._salvamento = None
        try:
            salvar(self.cfg)
        except OSError:
            pass  # sem permissão de escrita: segue funcionando sem lembrar a configuração

    def _fechar(self) -> None:
        self.mixer.parar()
        self._salvar_agora()
        self.destroy()


def main() -> None:
    # Troca de contexto mais curta: os retornos de áudio não esperam a interface.
    sys.setswitchinterval(0.001)
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    App().mainloop()


if __name__ == "__main__":
    main()
