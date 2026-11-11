"""Cores usadas na interface (pares = tema claro, tema escuro)."""

AZUL = "#2f6fed"
AZUL_FORTE = "#2559c4"
AZUL_TEXTO_FRACO = "#dbe5ff"
NEUTRO = ("gray86", "gray23")
NEUTRO_FORTE = ("gray78", "gray30")
CARTAO = ("gray92", "gray20")
VERDE = "#2fbf71"
VERMELHO = "#e5484d"
FUNDO_MEDIDOR = ("gray78", "gray30")
AMARELO = ("#9a6700", "#e3b341")
TEXTO = ("gray10", "gray90")
TEXTO_FRACO = ("gray40", "gray62")

# Faixa de situação do mixer: fundo, texto e ícone de cada tipo de mensagem.
SITUACOES = {
    "ok": (("#e3f5ea", "#163021"), ("#1b7a43", "#6ad69a"), "certo"),
    "aviso": (("#fdf3d7", "#352c14"), ("#8a5a00", "#e9bd55"), "aviso"),
    "erro": (("#fde4e4", "#3a1b1c"), ("#b4232a", "#ff8a8e"), "erro"),
    "neutro": (("gray92", "gray20"), ("gray40", "gray62"), "info"),
}
