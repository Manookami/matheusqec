// Grava o motion (index.html) quadro a quadro com o Chromium do Playwright e junta no ffmpeg.
// Uso: node gravar.js                -> motion_site.mp4 (60 fps)
//      node gravar.js previa 1.5 5   -> PNGs só desses tempos (para conferir)
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { chromium } = require('C:/Users/piner/Video Editing/videos/roblox-guga/intro-loren/motion/node_modules/playwright-core');

const AQUI = __dirname;
const FPS = 60;

(async () => {
  const browser = await chromium.launch();  // usa o Chromium "headless shell" já instalado pelo Playwright
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto('file:///' + path.join(AQUI, 'index.html').replace(/\\/g, '/'));
  await page.evaluate(() => window.prontas());
  // lista de sons (pop, tecla, whoosh...) com o tempo de cada um, para o audio.py montar a trilha
  fs.writeFileSync(path.join(AQUI, 'eventos.json'), JSON.stringify(await page.evaluate(() => window.EVENTOS), null, 1));
  const args = process.argv.slice(2);

  if (args[0] === 'previa') {
    for (const t of args.slice(1)) {
      await page.evaluate(x => window.seek(x), parseFloat(t));
      await page.screenshot({ path: path.join(AQUI, `previa_${t}.png`) });
    }
  } else {
    const dur = await page.evaluate(() => window.DURACAO);
    const saida = path.join(AQUI, 'motion_site.mp4');
    const ff = spawn('ffmpeg', ['-y', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-',
      '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', saida],
      { stdio: ['pipe', 'ignore', 'inherit'] });
    const total = Math.round(dur * FPS);
    for (let i = 0; i < total; i++) {
      await page.evaluate(x => window.seek(x), i / FPS);
      const img = await page.screenshot({ type: 'jpeg', quality: 95 });
      if (!ff.stdin.write(img)) await new Promise(r => ff.stdin.once('drain', r));
      if (i % 120 === 0) console.log(`quadro ${i}/${total}`);
    }
    ff.stdin.end();
    await new Promise(r => ff.on('close', r));
    console.log('pronto:', saida, fs.statSync(saida).size, 'bytes');
  }
  await browser.close();
})();
