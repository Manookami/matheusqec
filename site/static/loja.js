// Qual Eu Compro? · comportamento da loja (sem dependências)
(function () {
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------- tema: claro / sistema / escuro ---------- */
  var raiz = document.documentElement;
  function lerTema() { try { return localStorage.getItem('tema') || 'sistema'; } catch (e) { return 'sistema'; } }
  function aplicaTema(t) {
    if (t === 'claro') raiz.dataset.theme = 'light';
    else if (t === 'escuro') raiz.dataset.theme = 'dark';
    else delete raiz.dataset.theme;
    $$('.temas button').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.tema === t); });
  }
  $$('.temas button').forEach(function (b) {
    b.addEventListener('click', function () {
      try { localStorage.setItem('tema', b.dataset.tema); } catch (e) {}
      aplicaTema(b.dataset.tema);
    });
  });
  aplicaTema(lerTema());

  /* ---------- abas do topo: setas quando não cabem, arrastar com o mouse, aba atual sempre visível ---------- */
  var abas = $('.cats');
  if (abas) {
    var esq = $('.cats-seta.esq'), dir = $('.cats-seta.dir');
    var confere = function () {
      var max = abas.scrollWidth - abas.clientWidth;
      esq.hidden = abas.scrollLeft <= 4;
      dir.hidden = abas.scrollLeft >= max - 4;
      abas.parentNode.classList.toggle('mais-esq', !esq.hidden);
      abas.parentNode.classList.toggle('mais-dir', !dir.hidden);
    };
    esq.addEventListener('click', function () { abas.scrollBy({ left: -abas.clientWidth * 0.7, behavior: 'smooth' }); });
    dir.addEventListener('click', function () { abas.scrollBy({ left: abas.clientWidth * 0.7, behavior: 'smooth' }); });
    abas.addEventListener('scroll', confere, { passive: true });
    window.addEventListener('resize', confere);
    var ativa = $('a.ativo', abas);
    if (ativa) abas.scrollLeft = ativa.offsetLeft - (abas.clientWidth - ativa.offsetWidth) / 2;
    // arrastar com o mouse (no dedo o navegador já desliza sozinho)
    var arrasto = null, moveu = false;
    abas.addEventListener('mousedown', function (e) { arrasto = { x: e.pageX, s: abas.scrollLeft }; moveu = false; });
    window.addEventListener('mousemove', function (e) {
      if (!arrasto) return;
      var d = e.pageX - arrasto.x;
      if (Math.abs(d) > 5) { moveu = true; abas.scrollLeft = arrasto.s - d; }
    });
    window.addEventListener('mouseup', function () { arrasto = null; });
    abas.addEventListener('click', function (e) { if (moveu) { e.preventDefault(); moveu = false; } }, true);
    confere();
  }

  /* ---------- no celular os filtros começam recolhidos, para os produtos aparecerem logo ---------- */
  var caixaFiltros = $('details.filtros');
  if (caixaFiltros && window.matchMedia && matchMedia('(max-width: 900px)').matches) caixaFiltros.open = false;

  /* ---------- filtros dos cartões (busca + abas + faixa de preço + só desconto) ---------- */
  var estado = { busca: '', aba: '', faixa: '', soDesconto: false };
  function passa(c, ignorarAba) {
    if (estado.busca) {
      // todas as palavras precisam aparecer (em qualquer ordem): "tv 55 samsung"
      var palavras = estado.busca.split(/\s+/);
      for (var i = 0; i < palavras.length; i++) if (c.dataset.busca.indexOf(palavras[i]) < 0) return false;
    } else if ($('[data-busca-pagina]')) return false;  // página de busca vazia: nada até digitar
    if (!ignorarAba && estado.aba && c.closest('[data-secao="destaques"]') && c.dataset.cat !== estado.aba) return false;
    if (estado.faixa) {
      var p = parseFloat(c.dataset.preco), f = estado.faixa.split('-');
      if (!(p > +f[0] && p <= +f[1])) return false;
    }
    if (estado.soDesconto && !(+c.dataset.desc > 0)) return false;
    return true;
  }
  function aplica() {
    var vis = 0;
    $$('.card').forEach(function (c) { var ok = passa(c); c.hidden = !ok; if (ok) vis++; });
    $$('[data-secao]').forEach(function (s) { s.hidden = !s.querySelector('.card:not([hidden])'); });
    var v = $('#vazio'); if (v) v.hidden = vis > 0;
    var n = $('[data-contagem]'); if (n) n.textContent = vis;
  }

  // busca: na página inicial o formulário leva para /busca/?q=...; na busca e nas categorias filtra na hora
  var form = $('.busca'), campo = form && $('input', form);
  var q = new URLSearchParams(location.search).get('q') || '';
  var paginaBusca = $('[data-busca-pagina]');
  var semAcento = function (t) { return t.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim(); };
  $$('.card').forEach(function (c) { c.dataset.busca = semAcento(c.dataset.busca); });
  function buscaPor(t) {
    estado.busca = semAcento(t);
    if (paginaBusca) {
      var termo = $('[data-termo]'); if (termo) termo.textContent = t ? '“' + t + '”' : 'Buscar';
      if (history.replaceState) history.replaceState(null, '', t ? '?q=' + encodeURIComponent(t) : location.pathname);
    }
    aplica();
  }
  if (form && $('.cat-corpo')) {
    form.addEventListener('submit', function (ev) { ev.preventDefault(); buscaPor(campo.value); });
    campo.addEventListener('input', function () { buscaPor(campo.value); });
    if (q) campo.value = q;
    if (paginaBusca) { buscaPor(q); campo.focus(); }
  }

  $$('.abas button').forEach(function (b) {
    b.addEventListener('click', function () {
      $$('button', b.parentNode).forEach(function (x) { x.classList.toggle('ativo', x === b); });
      estado.aba = b.dataset.cat; aplica();
    });
  });

  $$('input[name="faixa"]').forEach(function (r) {
    r.addEventListener('change', function () { estado.faixa = r.value; aplica(); });
  });
  var so = $('[data-so-desconto]');
  if (so) so.addEventListener('change', function () { estado.soDesconto = so.checked; aplica(); });
  var limpar = $('[data-limpar]');
  if (limpar) limpar.addEventListener('click', function () {
    estado.faixa = ''; estado.soDesconto = false;
    var r = $('input[name="faixa"][value=""]'); if (r) r.checked = true;
    if (so) so.checked = false;
    aplica();
  });

  /* ---------- ordenação (página de categoria) ---------- */
  var grade = $('.cat-corpo .grade');
  if (grade) {
    var original = $$('.card', grade);
    $$('.ordem button').forEach(function (b) {
      b.addEventListener('click', function () {
        $$('.ordem button').forEach(function (x) { x.classList.toggle('ativo', x === b); });
        var lista = original.slice(), o = b.dataset.ordem;
        var preco = function (c) { return c.dataset.preco ? +c.dataset.preco : Infinity; };
        if (o === 'menor') lista.sort(function (a, z) { return preco(a) - preco(z); });
        if (o === 'maior') lista.sort(function (a, z) { return (+z.dataset.preco || 0) - (+a.dataset.preco || 0); });
        if (o === 'desconto') lista.sort(function (a, z) { return +z.dataset.desc - +a.dataset.desc; });
        lista.forEach(function (c) { grade.appendChild(c); });
      });
    });
  }

  /* ---------- carrossel: passa sozinho a cada 3 s, deslizando para o lado ---------- */
  var car = $('.carrossel');
  if (car) {
    var trilho = $('.trilho', car), pontos = $$('.pontos button', car), slides = $$('.slide', trilho);
    var atual = 0, timer = null, parado = false;
    var reduz = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    function vai(i) {
      atual = (i + slides.length) % slides.length;
      trilho.scrollTo({ left: slides[atual].offsetLeft - trilho.offsetLeft, behavior: reduz ? 'auto' : 'smooth' });
      marca();
    }
    function marca() { pontos.forEach(function (p, i) { p.setAttribute('aria-current', i === atual); }); }
    function liga() { if (!reduz && !timer) timer = setInterval(function () { if (!parado && !document.hidden) vai(atual + 1); }, 3000); }
    pontos.forEach(function (p, i) { p.addEventListener('click', function () { vai(i); }); });
    car.addEventListener('mouseenter', function () { parado = true; });
    car.addEventListener('mouseleave', function () { parado = false; });
    car.addEventListener('focusin', function () { parado = true; });
    car.addEventListener('focusout', function () { parado = false; });
    // arrastar com o dedo: acompanha o slide que ficou visível
    var fim;
    trilho.addEventListener('scroll', function () {
      clearTimeout(fim);
      fim = setTimeout(function () {
        var i = Math.round(trilho.scrollLeft / trilho.clientWidth);
        if (i !== atual) { atual = i; marca(); }
      }, 120);
    }, { passive: true });
    marca(); liga();
  }
})();
