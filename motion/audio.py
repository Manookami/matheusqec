"""Monta a trilha do motion: música lo-fi do canal + efeitos com a MESMA paleta sonora da vinheta do canal
(.claude/skills/matheusqec/assets/vinheta/gen_audio.py): whoosh de ar, pop 1100->260 Hz, baixo, arpejo dedilhado em
Lá maior (A-C#-E-A), sino FM e reverb de sala 22%. Tudo sintetizado = sem direito autoral.

Uso: python audio.py   (depois de node gravar.js) -> motion_site_com_som.mp4
"""
import json
import subprocess
import wave
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
ASSETS = AQUI.parent.parent / ".claude" / "skills" / "matheusqec" / "assets"
SR = 48000
MUSICA = ASSETS / "music" / "sunglasses.wav"
rng = np.random.default_rng(42)

A4, Cs5, E5, A5 = 440.0, 554.37, 659.25, 880.0
ARPEJO = [A4, Cs5, E5, A5, A5 * Cs5 / A4, A5 * E5 / A4, A5 * 2, A5 * 2 * Cs5 / A4]   # Lá maior subindo


def carrega(arq, dur=None):
    cmd = ["ffmpeg", "-v", "error", "-i", str(arq)] + (["-t", str(dur)] if dur else []) + \
          ["-f", "f32le", "-ac", "2", "-ar", str(SR), "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32).reshape(-1, 2).astype(np.float64)


# ---------- sintetizadores (iguais aos da vinheta) ----------
def lowpass(x, fc):
    a = np.exp(-2 * np.pi * fc / SR); y = np.zeros_like(x); acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc; y[i] = acc
    return y


def env_ad(n, a, d):
    t = np.arange(n) / SR
    return np.minimum(t / max(a, 1e-4), 1.0) * np.exp(-np.maximum(t - a, 0) / d)


def whoosh(dur, sobe=True):
    n = int(dur * SR); t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    fc = np.linspace(300, 5200, n) if sobe else np.linspace(5200, 400, n)
    y = np.zeros(n); acc = 0.0
    for i in range(n):
        a = np.exp(-2 * np.pi * fc[i] / SR); acc = (1 - a) * noise[i] + a * acc; y[i] = acc
    y -= lowpass(y, 180)
    shape = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** (1.6 if sobe else 1.2)
    return y * shape / (np.abs(y).max() + 1e-9)


def pop(f0=1100, f1=260, dur=0.12):
    n = int(dur * SR); t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.018)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.035)


def pluck(freq, dur=1.2):
    n = int(dur * SR); p = int(SR / freq)
    buf = lowpass(rng.uniform(-1, 1, p), 6000); y = np.zeros(n)
    for i in range(n):
        y[i] = buf[i % p]
        buf[i % p] = 0.996 * 0.5 * (buf[i % p] + buf[(i + 1) % p])
    return y * env_ad(n, 0.004, 0.9)


def bell(freq, dur=1.8):
    n = int(dur * SR); t = np.arange(n) / SR
    idx = 2.2 * np.exp(-t / 0.35)
    return np.sin(2 * np.pi * freq * t + idx * np.sin(2 * np.pi * freq * 1.4 * t)) * env_ad(n, 0.003, 0.55)


def bass(freq, dur=1.4):
    n = int(dur * SR); t = np.arange(n) / SR
    f = freq * (1 + 0.6 * np.exp(-t / 0.03))
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.25 * np.sin(4 * np.pi * np.cumsum(f) / SR)
    return y * env_ad(n, 0.006, 0.45)


def pad(freqs, dur, att=0.35):
    n = int(dur * SR); t = np.arange(n) / SR; y = np.zeros(n)
    for f in freqs:
        for det in (-0.004, 0.0, 0.005):
            y += 2 * ((t * f * (1 + det)) % 1.0) - 1
    y = lowpass(y / (len(freqs) * 3), 1800)
    return y * np.minimum(t / att, 1.0) * np.clip((dur - t) / 0.8, 0, 1)


def mistura(*partes):
    """partes = (sinal, atraso_s, ganho, pan) -> um único som estéreo."""
    n = max(int(a * SR) + len(s) for s, a, g, p in partes)
    out = np.zeros((n, 2))
    for s, a, g, p in partes:
        i = int(a * SR); l, r = np.sqrt(.5 * (1 - p)), np.sqrt(.5 * (1 + p))
        out[i:i + len(s), 0] += s * g * l; out[i:i + len(s), 1] += s * g * r
    return out


def mono(s, g=1.0, pan=0.0):
    return mistura((s, 0, g, pan))


# ---------- os efeitos do motion ----------
TECLA = pop(2600, 1200, 0.035)               # tecla: o mesmo "pop" da vinheta, curtinho e agudo
SONS = {
    "pop": mono(pop(), 0.55),
    "tic": mono(pop(1800, 700, 0.06), 0.35),
    "tecla": mono(TECLA, 0.3),
    "clique": mistura((pop(1600, 500, 0.05), 0, .5, 0), (pop(1300, 420, 0.05), .055, .35, 0)),
    "sino": mistura((bell(A5 * 2), 0, .22, .2), (bell(E5 * 2), .1, .14, -.2)),
    "whoosh": mono(whoosh(0.55, True), 0.55),
    "swoosh": mono(whoosh(0.45, False), 0.32),
    # menor preço: o "baixo + arpejo" da vinheta
    "conquista": mistura((bass(110.0), 0, .7, 0),
                         *[(pluck(f), .095 * k, .4, p) for k, (f, p) in enumerate([(A4, -.35), (Cs5, -.1), (E5, .15), (A5, .35)])],
                         (bell(A5 * 2), .32, .2, .2)),
    # final: a assinatura completa da vinheta (baixo + arpejo + pad + sinos)
    "assinatura": mistura((bass(110.0), 0, .75, 0),
                          *[(pluck(f), .095 * k, .42, p) for k, (f, p) in enumerate([(A4, -.35), (Cs5, -.1), (E5, .15), (A5, .35)])],
                          (pad([A4 / 2, Cs5 / 2, E5 / 2], 2.2), .03, .28, 0)),
}
for i, f in enumerate(ARPEJO, 1):            # cada aba que o mouse passa toca uma nota do arpejo
    SONS[f"nota{i}"] = mono(pluck(f, 0.7), 0.38, -0.4 + 0.1 * i)


def reverb(x, molhado=0.22):
    """Sala pequena da vinheta (ruído com decaimento), via FFT."""
    ir_n = int(0.9 * SR); ti = np.arange(ir_n) / SR
    ir = rng.standard_normal((ir_n, 2)) * np.exp(-ti / 0.28)[:, None]; ir /= np.abs(ir).sum(axis=0) / 12
    n = len(x) + ir_n; m = 1 << (n - 1).bit_length()
    wet = np.stack([np.fft.irfft(np.fft.rfft(x[:, c], m) * np.fft.rfft(ir[:, c], m), m)[:len(x)] for c in range(2)], axis=1)
    return x + molhado * wet


def main():
    eventos = json.loads((AQUI / "eventos.json").read_text(encoding="utf-8"))
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(AQUI / "motion_site.mp4")], capture_output=True, text=True).stdout)
    total = int(dur * SR)

    efeitos = np.zeros((total, 2))
    for e in eventos:
        s = SONS[e["tipo"]] * e.get("vol", 1)
        ini = int(max(0, e["t"] - (0.3 if e["tipo"] in ("whoosh", "swoosh") else 0)) * SR)   # pico do whoosh na troca
        fim = min(total, ini + len(s))
        efeitos[ini:fim] += s[: fim - ini]
    efeitos = reverb(efeitos)

    m = carrega(MUSICA, dur + 1)[:total]
    t = np.arange(len(m)) / SR
    curva = np.minimum(1, t / 0.6) * np.minimum(1, np.maximum(0, (dur - t) / 1.8))
    mix = efeitos * 1.6
    mix[: len(m)] += m * curva[:, None] * 0.30

    mix /= max(1.0, np.abs(mix).max() / 0.89)
    with wave.open(str(AQUI / "trilha.wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32767).astype("<i2").tobytes())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(AQUI / "motion_site.mp4"), "-i", str(AQUI / "trilha.wav"),
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-shortest",
                    str(AQUI / "motion_site_com_som.mp4")], check=True)
    print("pronto: motion_site_com_som.mp4 |", len(eventos), "efeitos")


if __name__ == "__main__":
    main()
