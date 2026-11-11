"""Testes que rodam em qualquer Windows, sem abrir dispositivos de som nem janelas.

    python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app  # noqa: E402
import mixer  # noqa: E402
import perfis  # noqa: E402
from config import mixer_padrao  # noqa: E402

TAXA = mixer.TAXA


class TestAnel(unittest.TestCase):
    """Entrada e saída com relógios diferentes: o som tem de sair contínuo."""

    def simular(self, ppm, alvo_ms, segundos=120, bloco_e=480, bloco_s=480):
        anel = mixer.Anel(int(TAXA * alvo_ms / 1000))
        freq = 110.0  # nota grave, como um baixo
        taxa_entrada = TAXA * (1 + ppm / 1e6)
        t_e = t_s = 0.0
        fase = 0
        saidas = []
        while t_s < segundos:
            if t_e <= t_s:
                n = np.arange(fase, fase + bloco_e)
                anel.escrever(np.sin(2 * np.pi * freq * n / TAXA).astype(np.float32))
                fase += bloco_e
                t_e += bloco_e / taxa_entrada
            else:
                saidas.append(anel.ler(bloco_s))
                t_s += bloco_s / TAXA
        sinal = np.concatenate(saidas)[TAXA:]  # ignora o enchimento inicial
        salto_maximo = float(np.abs(np.diff(sinal)).max())
        return anel.falhas, salto_maximo, 2 * np.pi * freq / TAXA

    def test_relogios_diferentes_sem_cortes(self):
        casos = [(0, 30, 480, 480), (300, 30, 480, 480), (-300, 30, 480, 480),
                 (1000, 30, 480, 480), (-1000, 30, 480, 480), (-300, 15, 441, 480),
                 (300, 60, 480, 1024)]
        for ppm, alvo, bloco_e, bloco_s in casos:
            with self.subTest(ppm=ppm, alvo=alvo, blocos=(bloco_e, bloco_s)):
                falhas, salto, salto_seno = self.simular(ppm, alvo, bloco_e=bloco_e,
                                                         bloco_s=bloco_s)
                self.assertEqual(falhas, 0)
                self.assertLess(salto, salto_seno * 1.5)  # sem estalo


class TestEntradaMono(unittest.TestCase):
    """Plugue mono numa entrada estéreo não pode perder metade do volume."""

    def pico(self, dados):
        canal = mixer._Canal(1, 480)
        mixer.Mixer()._ao_entrar(canal)(dados, len(dados), None, None)
        return canal.pico

    def test_lados(self):
        t = np.arange(480)
        seno = (0.5 * np.sin(2 * np.pi * 110 * t / TAXA)).astype(np.float32)
        zero = np.zeros(480, np.float32)
        self.assertAlmostEqual(self.pico(np.column_stack((seno, zero))), 0.5, places=2)
        self.assertAlmostEqual(self.pico(np.column_stack((zero, seno))), 0.5, places=2)
        self.assertAlmostEqual(self.pico(np.column_stack((seno, seno))), 0.5, places=2)
        self.assertAlmostEqual(self.pico(seno[:, None]), 0.5, places=2)


class TestCabosVirtuais(unittest.TestCase):
    def test_pares(self):
        self.assertEqual(app._saida_do_cabo("CABLE Output (VB-Audio Virtual Cable)"),
                         "CABLE Input (VB-Audio Virtual Cable)")
        self.assertEqual(app._saida_do_cabo("CABLE-A Output (VB-Audio Cable A)"),
                         "CABLE-A Input (VB-Audio Cable A)")
        self.assertEqual(app._saida_do_cabo("Hi-Fi Cable Output (VB-Audio Hi-Fi Cable)"),
                         "Hi-Fi Cable Input (VB-Audio Hi-Fi Cable)")
        self.assertIsNone(app._saida_do_cabo("Microfone (USB Microphone)"))
        self.assertIsNone(app._saida_do_cabo(None))

    def test_microfonia(self):
        self.assertTrue(app._mesmo_cabo("CABLE Output (VB-Audio Virtual Cable)",
                                        "CABLE Input (VB-Audio Virtual Cable)"))
        self.assertFalse(app._mesmo_cabo("Microfone (USB Microphone)",
                                         "CABLE Input (VB-Audio Virtual Cable)"))


class TestPerfis(unittest.TestCase):
    def test_nome_curto(self):
        self.assertEqual(perfis.curto("Alto-falantes (PRO X Wireless Gaming Headset)"),
                         "PRO X Wireless Gaming Headset")
        self.assertEqual(perfis.curto("Sem parênteses"), "Sem parênteses")
        self.assertEqual(len(perfis.curto("x" * 50, 20)), 20)

    def test_resumo_mixer(self):
        mixer_teste = mixer_padrao()
        self.assertEqual(perfis.resumo_mixer(mixer_teste), "Mixer desligado · 1 entrada")
        mixer_teste["ligado"] = True
        mixer_teste["canais"][1]["entrada"] = "algum-id"
        self.assertEqual(perfis.resumo_mixer(mixer_teste), "Mixer ligado · 2 entradas")

    def test_perfil_antigo(self):
        antigo = {"nome": "Velho", "saida": "a", "entrada": "b", "mixer": None}
        self.assertEqual(perfis.normalizar(antigo)["icone"], "estrela")
        sem_partes = perfis.normalizar({"nome": "X", "icone": "inexistente"})
        self.assertEqual(sem_partes["icone"], "estrela")
        self.assertIsNone(sem_partes["saida"])


if __name__ == "__main__":
    unittest.main()
