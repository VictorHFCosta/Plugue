"""Motor do mixer: capta várias entradas e envia a mistura para até duas saídas."""
from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

TAXA = 48000

# Correção de velocidade por amostra de erro no buffer, e o limite dessa correção.
# Valores pequenos de propósito: a mudança de afinação fica inaudível (< 0,3 %).
_GANHO_CORRECAO = 0.001 / 480
_CORRECAO_MAXIMA = 0.003


class Anel:
    """Fila circular mono entre uma entrada e uma saída.

    Cada dispositivo de som tem o próprio relógio, então a entrada produz um
    pouco mais (ou menos) amostras do que a saída consome. Para o buffer não
    encher nem esvaziar, a leitura reamostra o áudio bem de leve, mantendo o
    nível do buffer perto do alvo.
    """

    def __init__(self, alvo: int, capacidade: int = TAXA):
        self.alvo = alvo
        self.cap = capacidade
        self.buf = np.zeros(capacidade, dtype=np.float32)
        self.escritos = 0  # total de amostras já escritas
        self.lidos = 0  # total de amostras já consumidas
        self.frac = 0.0  # posição fracionária da leitura
        self.media = float(alvo)  # nível médio do buffer após cada leitura
        self.pronto = False
        self.falhas = 0
        self.trava = threading.Lock()

    def escrever(self, dados: np.ndarray) -> None:
        n = len(dados)
        if n >= self.cap:
            dados = dados[-(self.cap - 1):]
            n = len(dados)
        with self.trava:
            inicio = self.escritos % self.cap
            fim = inicio + n
            if fim <= self.cap:
                self.buf[inicio:fim] = dados
            else:
                corte = self.cap - inicio
                self.buf[inicio:] = dados[:corte]
                self.buf[: n - corte] = dados[corte:]
            self.escritos += n
            excesso = (self.escritos - self.lidos) - (self.cap - 1)
            if excesso > 0:  # ninguém está lendo: descarta o mais antigo
                self.lidos += excesso

    def _recomecar(self, n: int) -> None:
        self.lidos = self.escritos - (self.alvo + n)
        self.frac = 0.0
        self.media = float(self.alvo)
        self.pronto = True

    def ler(self, n: int) -> np.ndarray:
        with self.trava:
            disponivel = self.escritos - self.lidos
            if not self.pronto:
                if disponivel < self.alvo + n:
                    return np.zeros(n, dtype=np.float32)
                self._recomecar(n)
                disponivel = self.alvo + n

            sobra = disponivel - n
            if sobra > self.alvo + max(2 * self.alvo, TAXA // 10):
                # Atraso acumulado demais (a saída travou por um tempo): pula.
                self.falhas += 1
                self._recomecar(n)
                disponivel = self.alvo + n
                sobra = self.alvo

            self.media += 0.005 * (sobra - self.media)
            correcao = (self.media - self.alvo) * _GANHO_CORRECAO
            passo = 1.0 + max(-_CORRECAO_MAXIMA, min(_CORRECAO_MAXIMA, correcao))

            final = self.frac + passo * n
            necessario = int(final) + 2
            if disponivel < necessario:
                # A entrada atrasou: silêncio até o buffer encher de novo.
                self.falhas += 1
                self.pronto = False
                return np.zeros(n, dtype=np.float32)

            inicio = self.lidos % self.cap
            fim = inicio + necessario
            if fim <= self.cap:
                trecho = self.buf[inicio:fim]
            else:
                trecho = np.concatenate((self.buf[inicio:], self.buf[: fim - self.cap]))

            posicoes = self.frac + passo * np.arange(n)
            saida = np.interp(posicoes, np.arange(necessario), trecho).astype(np.float32)
            avanco = int(final)
            self.lidos += avanco
            self.frac = final - avanco
            return saida


class _Canal:
    def __init__(self, destinos: int, alvo: int):
        self.aneis = [Anel(alvo) for _ in range(destinos)]
        self.ganhos = [0.0] * destinos  # ganho pedido para cada destino
        self.aplicados = [0.0] * destinos  # ganho em uso (para transição suave)
        self.pico = 0.0


def _localizar(nome: str, entrada: bool) -> tuple[int, dict]:
    """Acha o dispositivo pelo nome que o Windows mostra, dentro da API WASAPI."""
    apis = sd.query_hostapis()
    wasapi = next((i for i, api in enumerate(apis) if "WASAPI" in api["name"]), None)
    campo = "max_input_channels" if entrada else "max_output_channels"
    for indice, info in enumerate(sd.query_devices()):
        if info["hostapi"] == wasapi and info["name"] == nome and info[campo] > 0:
            return indice, info
    raise LookupError(f"Dispositivo não encontrado: {nome}")


class Mixer:
    def __init__(self):
        self._fluxos: list = []
        self._canais: list[_Canal | None] = []
        self._papeis: list[set[str]] = []
        self.ativo = False

    def iniciar(self, entradas: list[str | None], monitor: str | None,
                envio: str | None, alvo_ms: int) -> None:
        """Abre os dispositivos e começa a mixar.

        entradas: nome do dispositivo de cada canal (None = canal vazio).
        monitor:  saída onde você se ouve (fone). envio: saída que recebe a
        mistura para outros programas. Qualquer uma das duas pode ser None.
        """
        self.parar()
        # Recarrega a lista de dispositivos (o PortAudio só a lê ao inicializar).
        sd._terminate()
        sd._initialize()

        destinos: list[tuple[str, set[str]]] = []
        if monitor:
            destinos.append((monitor, {"monitor"}))
        if envio:
            if envio == monitor:
                destinos[0][1].add("envio")
            else:
                destinos.append((envio, {"envio"}))

        alvo = int(TAXA * alvo_ms / 1000)
        self._papeis = [papeis for _, papeis in destinos]
        self._canais = [_Canal(len(destinos), alvo) if nome else None for nome in entradas]
        opcoes = dict(samplerate=TAXA, dtype="float32", latency="low",
                      extra_settings=sd.WasapiSettings(auto_convert=True))
        try:
            for d, (nome, _) in enumerate(destinos):
                indice, info = _localizar(nome, entrada=False)
                self._fluxos.append(sd.OutputStream(
                    device=indice, channels=min(2, info["max_output_channels"]),
                    callback=self._ao_sair(d), **opcoes))
            for nome, canal in zip(entradas, self._canais):
                if canal is None:
                    continue
                indice, info = _localizar(nome, entrada=True)
                self._fluxos.append(sd.InputStream(
                    device=indice, channels=min(2, info["max_input_channels"]),
                    callback=self._ao_entrar(canal), **opcoes))
            for fluxo in self._fluxos:
                fluxo.start()
        except Exception:
            self.parar()
            raise
        self.ativo = True

    def parar(self) -> None:
        for fluxo in self._fluxos:
            try:
                fluxo.abort()
                fluxo.close()
            except Exception:
                pass
        self._fluxos = []
        self._canais = []
        self._papeis = []
        self.ativo = False

    def ajustar(self, indice: int, ganho: float, mudo: bool, monitor: bool, envio: bool) -> None:
        """Muda volume e rotas de um canal sem interromper o áudio."""
        if indice >= len(self._canais) or self._canais[indice] is None:
            return
        canal = self._canais[indice]
        for d, papeis in enumerate(self._papeis):
            ligado = (monitor and "monitor" in papeis) or (envio and "envio" in papeis)
            canal.ganhos[d] = ganho if ligado and not mudo else 0.0

    def niveis(self) -> list[float | None]:
        """Pico de cada canal desde a última chamada (None = canal vazio)."""
        resultado = []
        for canal in self._canais:
            if canal is None:
                resultado.append(None)
            else:
                resultado.append(canal.pico)
                canal.pico = 0.0
        return resultado

    def falhas(self) -> int:
        return sum(anel.falhas for canal in self._canais if canal for anel in canal.aneis)

    def saudavel(self) -> bool:
        return self.ativo and all(fluxo.active for fluxo in self._fluxos)

    def _ao_entrar(self, canal: _Canal):
        # Um plugue mono (instrumento, microfone simples) numa entrada estéreo só traz
        # sinal de um lado; tirar a média com o lado vazio cortaria o volume pela metade.
        # "lado" guarda qual lado usar sozinho (None = média dos dois).
        estado = {"lado": None}

        def callback(dados, quadros, tempo, status):
            if not quadros:
                return
            if dados.shape[1] == 1:
                mono = dados[:, 0]
            else:
                picos = np.abs(dados[:, :2]).max(axis=0)
                forte, fraco = (0, 1) if picos[0] >= picos[1] else (1, 0)
                # Entra no modo "um lado só" abaixo de 5 % e só sai acima de 20 %,
                # para não ficar alternando no meio de uma nota.
                if picos[fraco] < 0.05 * picos[forte]:
                    estado["lado"] = forte
                elif picos[fraco] > 0.20 * picos[forte]:
                    estado["lado"] = None
                lado = estado["lado"]
                mono = dados[:, lado] if lado is not None else dados[:, :2].mean(axis=1)
            pico = float(np.abs(mono).max())
            if pico > canal.pico:
                canal.pico = pico
            for anel in canal.aneis:
                anel.escrever(mono)
        return callback

    def _ao_sair(self, destino: int):
        canais = [canal for canal in self._canais if canal is not None]

        def callback(saida, quadros, tempo, status):
            mistura = np.zeros(quadros, dtype=np.float32)
            for canal in canais:
                # Lê sempre, mesmo com ganho zero, para o buffer não acumular.
                dados = canal.aneis[destino].ler(quadros)
                anterior, pedido = canal.aplicados[destino], canal.ganhos[destino]
                if anterior == pedido:
                    if pedido:
                        mistura += dados * np.float32(pedido)
                else:
                    mistura += dados * np.linspace(anterior, pedido, quadros, dtype=np.float32)
                    canal.aplicados[destino] = pedido
            np.clip(mistura, -1.0, 1.0, out=mistura)
            saida[:] = mistura[:, None]
        return callback
