// 회전초밥 벨트 시험장 UI (2026-10-08). 규칙은 전부 belt-core.js에 있고 여기는 입력/그리기/소리만 한다.
(function () {
  "use strict";
  var C = BeltCore, PL = C.PLATES, KINDS = C.KINDS, CM = false;   // CM: 색 모드(접시 색 = 주문)
  
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var params = new URLSearchParams(location.search);
  var TEST = params.has("test");
  var TIER_NAME = { 1: "흰 접시", 2: "파란 접시", 3: "금 접시" };
  var TIER_COLOR = { 1: "#f4efe4", 2: "#3b78c2", 3: "#d9a521" };

  var settings = {
    mode: params.get("mode") === "two" ? "two" : "bot",
    plates: params.get("plates") === "sushi" ? "sushi" : "color",
    seatRule: params.get("seatRule") === "fixed" ? "fixed" : "any",
    brake: ["cap", "free"].indexOf(params.get("brake")) >= 0 ? params.get("brake") : "budget",
    budget: +params.get("budget") || 48,
    cap: +params.get("cap") || 4,
    coop: params.has("coop") ? +params.get("coop") / 100 : 0.3,
    roundMs: +params.get("roundMs") || 5000,
    jitter: params.has("jitter") ? +params.get("jitter") * 1000 : 1000,
    rounds: +params.get("rounds") || 7,
    botRate: +params.get("botRate") || 3,
    seed: params.get("seed") ? +params.get("seed") : null,
    sound: params.get("sound") !== "0"
  };

  // ---------- 소리 (WebAudio, 첫 키/클릭 이후에만) ----------
  var actx = null;
  function beep(freq, dur, type, vol, delay) {
    if (!settings.sound) return;
    try {
      actx = actx || new (window.AudioContext || window.webkitAudioContext)();
      var t0 = actx.currentTime + (delay || 0), o = actx.createOscillator(), g = actx.createGain();
      o.type = type || "square"; o.frequency.value = freq;
      g.gain.setValueAtTime(vol || 0.05, t0); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
      o.connect(g); g.connect(actx.destination); o.start(t0); o.stop(t0 + dur + 0.02);
    } catch (e) { /* 소리는 없어도 된다 */ }
  }
  var SFX = {
    push: function (dir) { beep(dir > 0 ? 520 : 440, 0.05, "square", 0.035); },
    deny: function () { beep(130, 0.09, "sawtooth", 0.04); },
    cd: function (go) { beep(go ? 880 : 520, go ? 0.3 : 0.12, "triangle", 0.07); },
    win: function () { beep(660, 0.12, "triangle", 0.07); beep(880, 0.18, "triangle", 0.07, 0.11); },
    lose: function () { beep(180, 0.25, "sawtooth", 0.05); },
    end: function () { beep(392, 0.15, "triangle", 0.07); beep(523, 0.15, "triangle", 0.07, 0.14); beep(784, 0.3, "triangle", 0.07, 0.28); }
  };

  // ---------- 접시 그림 (SVG) ----------
  function topping(key) {
    switch (key) {
      case "salmon": return '<ellipse cx="50" cy="46" rx="28" ry="13" fill="#f08a4b"/><path d="M28 44q10-5 18 0M44 39q10-5 18 0M52 50q9-4 16 0" stroke="#ffd9bd" stroke-width="2.4" fill="none" stroke-linecap="round"/>';
      case "tuna": return '<ellipse cx="50" cy="46" rx="28" ry="13" fill="#b3262e"/><path d="M30 46q20-8 40 0" stroke="#e7727a" stroke-width="3" fill="none" stroke-linecap="round"/>';
      case "shrimp": return '<path d="M24 52q2-20 28-20q20 0 24 16q-6 6-26 6q-20 0-26-2z" fill="#f4a79b"/><path d="M36 36q3 10 0 18M48 33q3 12 0 22M60 34q3 11 0 20" stroke="#dd6f64" stroke-width="2.6" fill="none" stroke-linecap="round"/><path d="M74 46l10-6l-2 10z" fill="#dd6f64"/>';
      case "egg": return '<rect x="26" y="34" width="48" height="26" rx="6" fill="#f4cf4a"/><rect x="45" y="30" width="10" height="32" rx="2" fill="#1f2a24"/>';
      case "eel": return '<ellipse cx="50" cy="46" rx="29" ry="13" fill="#6b3a1e"/><path d="M26 44q24-9 48 0" stroke="#b27a47" stroke-width="3.2" fill="none" stroke-linecap="round"/><path d="M34 52q16 4 32 0" stroke="#3f200d" stroke-width="2.4" fill="none" stroke-linecap="round"/>';
      case "octopus": return '<ellipse cx="50" cy="46" rx="28" ry="13" fill="#f3dbe1"/><path d="M24 46q26-14 52 0" stroke="#9c4f73" stroke-width="4" fill="none" stroke-linecap="round"/><circle cx="38" cy="48" r="2.2" fill="#c98aa6"/><circle cx="50" cy="50" r="2.2" fill="#c98aa6"/><circle cx="62" cy="48" r="2.2" fill="#c98aa6"/>';
      case "ikura": return '<rect x="28" y="36" width="44" height="26" rx="9" fill="#1f2a24"/><ellipse cx="50" cy="38" rx="19" ry="8" fill="#f26a2e"/><circle cx="41" cy="36" r="3.4" fill="#ff9a58"/><circle cx="50" cy="33" r="3.4" fill="#ff8a45"/><circle cx="59" cy="36" r="3.4" fill="#ff9a58"/><circle cx="46" cy="40" r="3.2" fill="#e85a22"/><circle cx="55" cy="40" r="3.2" fill="#e85a22"/>';
      case "tofu": return '<path d="M24 56q-2-22 26-24q28 2 26 24z" fill="#d9922e"/><path d="M30 44h40" stroke="#b36f17" stroke-width="2.4" stroke-dasharray="4 4"/><ellipse cx="50" cy="35" rx="14" ry="5" fill="#fdfbf4"/>';
    }
    return "";
  }
  function markShape(pt, x, y, a, ink) {
    var t = 'transform="translate(' + x.toFixed(1) + " " + y.toFixed(1) + ") rotate(" + a.toFixed(0) + ") scale(1.55)" + '"';
    switch (pt) {
      case "dots": return '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="3.4" fill="' + ink + '"/>';
      case "stripes": return '<rect ' + t + ' x="-1" y="-3.4" width="2" height="6.8" fill="' + ink + '"/>';
      case "check": return '<rect ' + t + ' x="-2.2" y="-2.2" width="4.4" height="4.4" fill="' + ink + '"/>';
      case "heart": return '<path ' + t + ' d="M0 3l-3.2-3.3a1.9 1.9 0 0 1 3.2-1.8a1.9 1.9 0 0 1 3.2 1.8z" fill="' + ink + '"/>';
      case "star": return '<path ' + t + ' d="M0-3.4l1 2.4 2.6.2-2 1.7.6 2.5L0 1.9l-2.2 1.5.6-2.5-2-1.7 2.6-.2z" fill="' + ink + '"/>';
    }
    return "";
  }
  function plateSvg(p) {
    var pl = PL[p];
    if (CM) {
      var c = KINDS[pl.kind], rgb = [1, 3, 5].map(function (i) { return parseInt(c.hex.substr(i, 2), 16); });
      var lum = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255, ink = lum > 0.6 ? "rgba(40,30,20,.8)" : "rgba(255,255,255,.9)", marks = "", k, pat = C.PATTERNS[pl.pattern].key;
      for (k = 0; k < 8; k++) { var a = k * 45 * Math.PI / 180; marks += markShape(pat, 50 + 42 * Math.sin(a), 50 - 42 * Math.cos(a), k * 45, ink); }
      return '<svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="48" fill="' + c.hex + '"/><circle cx="50" cy="50" r="48" fill="none" stroke="rgba(0,0,0,.3)" stroke-width="1.5"/>' +
        marks +
        '<circle cx="50" cy="50" r="36" fill="rgba(255,255,255,.28)" stroke="rgba(0,0,0,.14)"/></svg>';
    }
    return '<svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="48" fill="' + TIER_COLOR[pl.tier] + '"/><circle cx="50" cy="50" r="48" fill="none" stroke="rgba(0,0,0,.28)" stroke-width="1.5"/>' +
      '<circle cx="50" cy="50" r="38" fill="#fffaf0" stroke="rgba(0,0,0,.12)"/><ellipse cx="50" cy="58" rx="25" ry="12" fill="#fdfbf4" stroke="#d9d2c0"/>' + topping(pl.key) + "</svg>";
  }
  function sushiSvg(key) { return '<svg viewBox="12 24 76 50" aria-hidden="true"><ellipse cx="50" cy="58" rx="25" ry="12" fill="#fdfbf4" stroke="#d9d2c0"/>' + topping(key) + "</svg>"; }
  var SUSHI_NAME = { egg: "계란", shrimp: "새우", salmon: "연어", tuna: "참치" };
  // 주문을 글로 (색 모드)
  function orderText(o) {
    var T = C.ORDER_TYPES[o.type], names = o.colors.map(function (c) { return C.COLORS[c].name; });
    if (o.type === "normal") return names.join(" 또는 ") + " 접시";
    if (o.type === "fixed") return o.pattern != null ? C.PATTERNS[o.pattern].name + " 무늬 접시" : names[0] + " 접시";
    return names[0] + " 접시";
  }
  function orderRule(o) {
    return { normal: "둘 중 아무 접시나", fixed: o.pattern != null ? "무늬가 같은 접시면 어느 쪽이든" : "지정된 이 색만", fragile: "정확히 이 색만", valuable: "정확히 이 색만" }[o.type];
  }
  function want(i, p) { return CM ? g.accepts(i, p) : g.state.targets[i] === PL[p].kind; }

  // ---------- 상태 ----------
  var g, bot = null, ui = { phase: "idle", cdStep: 0, cdTimer: 0, lastResult: null, front: [-1, -1] };
  var els = {};
  var ANG0 = 180;   // 0번 칸의 각도 (CSS 기준 180 = 9시, 90 = 6시). 10칸 벨트의 공유 칸을 6시에 놓으려고 90으로 돌린다

  function seatLabel(i) { return settings.mode === "bot" ? (i === 0 ? "나" : "봇") : (i === 0 ? "1P" : "2P"); }
  function targetVisible(i) { return settings.mode === "two" || i === 0; }
  function nowMs() { return performance.now(); }

  function newGame() {
    clearTimeout(ui.cdTimer);
    var rng = settings.seed != null ? C.mulberry32(settings.seed) : Math.random;
    CM = settings.plates === "color";
    ANG0 = CM && settings.seatRule === "any" ? 90 : 180;
    var layout = CM ? { plates: C.PLATES_COLOR, pointsBy: "order" } : {};
    layout.seats = CM ? (settings.seatRule === "fixed" ? [0, 5] : [0, 5]) : (settings.seatRule === "fixed" ? [0, 6] : [9, 3]);
    PL = layout.plates || C.PLATES; KINDS = CM ? C.COLORS : C.KINDS;
    g = C.create({ plates: layout.plates || C.PLATES, pointsBy: layout.pointsBy || "plate", seats: layout.seats, seatRule: settings.seatRule, brake: settings.brake, budget: settings.budget, cap: settings.cap, roundMs: settings.roundMs, endJitter: Math.min(settings.jitter, Math.max(0, settings.roundMs - 500)), coopDeal: settings.coop, rounds: settings.rounds, rng: rng });
    bot = settings.mode === "bot" ? C.makeBot(g, 1, { rate: settings.botRate }, rng) : null;
    ui.phase = "idle"; ui.lastResult = null; ui.front = [-1, -1];
    if (TEST) window.__belt = { game: g, ui: ui, settings: settings };
    build(); render();
  }

  // ---------- DOM ----------
  function build() {
    var rot = $(".rot"), U = 360 / g.N;
    $(".belt").style.setProperty("--u", U + "deg");
    rot.innerHTML = PL.map(function (p, i) {
      return '<div class="plate" data-p="' + i + '" style="--a:' + (ANG0 + U * i) + '"><span class="flag f0">' + seatLabel(0).slice(0, 2) + '</span><span class="flag f1">' + seatLabel(1).slice(0, 2) + "</span>" + plateSvg(i) + '<span class="pl-name">' + p.name + (CM ? "·" + C.PATTERNS[p.pattern].name : "") + "</span></div>";
    }).join("");
    var frames = "";
    if (g.cfg.seatRule === "any") frames = '<div class="seatf both" data-f="any" style="--a:' + (ANG0 + U * g.cfg.seats[0]) + '"><span class="st">먹는 칸</span></div>';
    else frames = [0, 1].map(function (i) { return '<div class="seatf s' + i + '" data-f="' + i + '" style="--a:' + (ANG0 + U * g.cfg.seats[i]) + '"><span class="st">' + seatLabel(i) + "</span></div>"; }).join("");
    $(".frames").innerHTML = frames;
    els.plates = $$(".plate");
    els.frames = $$(".seatf");
    [0, 1].forEach(function (i) {
      $("#h" + i).innerHTML = '<span class="seat-tag">' + seatLabel(i) + "</span> " + (settings.mode === "bot" ? (i === 0 ? "내 자리" : "컴퓨터") : "자리 " + (i + 1));
      $("#k" + i).innerHTML = settings.mode === "bot" ? (i === 0 ? "<kbd>←</kbd> <kbd>→</kbd> 또는 <kbd>A</kbd> <kbd>D</kbd>" : "연타 속도 초당 " + settings.botRate + "회") : (i === 0 ? "<kbd>A</kbd> <kbd>D</kbd>" : "<kbd>←</kbd> <kbd>→</kbd>");
      $("#pad" + i).classList.toggle("invisible", settings.mode === "bot" && i === 1);
    });
    var shared = g.cfg.seatRule === "any";
    $("#plateNote").textContent = CM
      ? "벨트에는 색이 다른 접시 10장이 있고(빨강 주황 노랑 초록 파랑 보라 분홍 흰색 검정 회색), 무늬 5종이 각각 두 장씩 그려져 있어요. 주문은 접시 색이 목적지입니다. 일반 초밥은 두 색 중 아무 접시나, 지정 주문은 정해진 색 한 가지 또는 같은 무늬면 어느 접시든, 중급과 특선은 정확히 한 색에 올라가야 인정돼요. 점수는 일반 2 · 지정 3 · 중급 5 · 특선 10."
      : "벨트에는 접시 12개가 고정 순서로 실려 있고, 맛은 8가지예요. 연어·참치·계란·유부는 두 개씩이라 어느 쪽을 가져와도 돼요. 정반대에 있는 접시끼리는 같은 가격대입니다.";
    $("#frontLbl0").textContent = $("#frontLbl1").textContent = shared ? "지금 먹는 칸의 접시 (둘이 같이 씀)" : "지금 내 앞 접시";
    $("#subRule").textContent = shared
      ? "벨트는 끝이 없이 한 바퀴를 돕니다. 먹는 칸은 아래쪽 한 곳뿐이고 두 사람이 같이 써요. 5초 동안 서로 밀고, 멈췄을 때 그 칸에 내 주문이 와 있으면 점수를 받아요. 내가 당기면 상대의 접시도 같이 움직입니다."
      : "벨트는 끝이 없이 한 바퀴를 돕니다. 5초 동안 두 사람이 서로 밀고, 멈췄을 때 내 자리 앞에 내 주문이 와 있으면 점수를 받아요. 내가 당긴 만큼 상대의 접시도 같이 움직입니다.";
    $("#budgetLabel0").textContent = $("#budgetLabel1").textContent = settings.brake === "budget" ? "남은 밀기" : settings.brake === "cap" ? "이번 라운드 이동 범위" : "밀기 (제한 없음)";
    $("#ov").innerHTML = "";
  }

  function orderHtml(i) {
    var s = g.state, hasTarget = (ui.phase !== "idle" || s.dealt) && s.targets[i] != null;
    if (!hasTarget) return '<div class="order hidden">·</div>';
    if (!targetVisible(i)) return '<div class="order hidden" title="상대 주문은 숨겨져 있어요">?</div>';
    var kd = KINDS[s.targets[i]], copies = PL.filter(function (x) { return x.kind === s.targets[i]; }), pi = PL.indexOf(copies[0]);
    if (CM) {
      var o = s.orders[i], T = C.ORDER_TYPES[o.type];
      return '<div class="order cm t-' + o.type + '"><div class="orow"><div class="osushi">' + sushiSvg(o.sushi) + '</div><div><div class="on">' + C.SUSHI_NAMES[o.sushi] + ' 초밥</div><div class="op"><b>' + T.name + " · " + T.points + '점</b></div></div></div><div class="orow owhere"><div class="ois">' + o.plates.map(function (pp) { return '<div class="oi">' + plateSvg(pp) + "</div>"; }).join("") + "</div><div><div class=\"ow\">" + orderText(o) + '에 올리기</div><div class="op">' + orderRule(o) + "</div></div></div></div>";
    }
    return '<div class="order"><div class="oi">' + plateSvg(pi) + '</div><div><div class="on">' + kd.name + '</div><div class="op">' + TIER_NAME[kd.tier] + " · " + g.cfg.tierPoints[kd.tier] + "점 · " + copies.length + "개</div></div></div>";
  }

  function render() {
    var s = g.state, k, i, shared = g.cfg.seatRule === "any";
    $(".belt").style.setProperty("--off", s.off);
    var showT = (ui.phase !== "idle" || s.dealt) && s.phase !== "end";
    els.plates.forEach(function (el, p) {
      el.classList.toggle("t0", showT && targetVisible(0) && want(0, p));
      el.classList.toggle("t1", showT && targetVisible(1) && want(1, p));
    });
    for (i = 0; i < 2; i++) {
      $("#order" + i).innerHTML = orderHtml(i);
      var eat = g.eatenBy(i), fr = $("#front" + i), match = showT && want(i, eat) && targetVisible(i);
      fr.className = "front" + (match ? " match" : "");
      fr.innerHTML = (shared ? "먹는 칸: <b>" : "지금 앞: <b>") + PL[eat].name + (CM ? " · " + C.PATTERNS[PL[eat].pattern].name : "") + "</b>" + (CM ? "" : " <small>" + g.cfg.tierPoints[PL[eat].tier] + "점</small>");
      $("#score" + i).innerHTML = s.scores[i] + "<small>점</small>";
      var left, max;
      if (g.cfg.brake === "budget") { left = s.budget[i]; max = g.cfg.budget; $("#bn" + i).innerHTML = "<span>이번 라운드 " + s.pushes[i] + "회</span><b>" + left + " / " + max + "</b>"; }
      else if (g.cfg.brake === "cap") { left = Math.max(0, g.cfg.cap - Math.abs(s.off - s.startOff)); max = g.cfg.cap; $("#bn" + i).innerHTML = "<span>시작 위치 ±" + g.cfg.cap + "칸</span><b>" + (s.off - s.startOff > 0 ? "+" : "") + (s.off - s.startOff) + "</b>"; }
      else { left = max = 1; $("#bn" + i).innerHTML = "<span>이번 라운드 " + s.pushes[i] + "회</span><b>∞</b>"; }
      $("#bar" + i).style.width = (100 * left / max) + "%";
      if (settings.mode === "bot" && i === 1) { /* 봇 패널에는 방향 버튼 없음 */ }
    }
    var anyMatch = (g.cfg.seatRule === "any") && showT && (want(0, g.eatenBy(0)) || want(1, g.eatenBy(0)));
    els.frames.forEach(function (f) {
      var idx = f.getAttribute("data-f");
      f.classList.toggle("match", idx === "any" ? anyMatch : showT && targetVisible(+idx) && want(+idx, g.eatenBy(+idx)));
    });
    // 가운데 표시
    var round = s.phase === "active" || s.phase === "result" || s.phase === "end" ? s.round : s.round + 1;
    $("#round").textContent = s.phase === "end" ? "게임 종료" : "라운드 " + Math.min(round, g.cfg.rounds) + " / " + g.cfg.rounds;
    if (TEST) document.body.setAttribute("data-phase", s.phase + "/" + ui.phase);
  }

  var lastFrameFront = [-1, -1];
  function frame() {
    var t = nowMs(), s = g.state;
    if (s.phase === "active") {
      if (bot) { var d = bot.step(t); if (d) { SFX.push(d); render(); } }
      var res = g.tick(t);
      if (res) { onResult(res); }
      else {
        // 종료 시각이 흔들리는 규칙이면 시계는 "가장 이른 종료"까지만 센다. 그 뒤로는 언제 끝날지 모른다.
        var left = Math.max(0, s.earliestEnd - t), hiding = g.cfg.endJitter > 0;
        if (left > 0 || !hiding) {
          $("#clock").textContent = (left / 1000).toFixed(1);
          $("#clock").classList.toggle("low", left < 1500);
        } else { $("#clock").textContent = "!"; $("#clock").classList.add("low"); }
        $(".timebar > i").style.width = (100 * left / Math.max(1, g.cfg.roundMs - g.cfg.endJitter)) + "%";
        $("#msg").textContent = left > 0 || !hiding ? "밀어요!" : "언제든 끝나요!";
      }
    }
    requestAnimationFrame(frame);
  }

  // ---------- 흐름 ----------
  function holeMsg(msg, btn) {
    $("#msg").textContent = msg || "";
    var b = $("#holeBtn");
    if (btn) { b.textContent = btn; b.classList.remove("hidden-el"); } else b.classList.add("hidden-el");
  }

  function setIdleUI() {
    ui.phase = "idle";
    $("#clock").textContent = (g.cfg.roundMs / 1000).toFixed(1); $("#clock").classList.remove("low");
    $(".timebar > i").style.width = "100%";
    var first = g.state.round === 0;
    holeMsg(first ? "내 주문을 내 앞으로" : "", (first ? "시작" : g.state.round + 1 + "라운드 시작") + "  (Space)");
    render();
  }

  function startRound() {
    if (g.state.phase !== "idle" || ui.phase === "cd") return;
    g.deal();
    ui.phase = "cd"; ui.cdStep = 3;
    holeMsg("주문을 확인하세요", null);
    render();
    (function step() {
      if (ui.cdStep > 0) {
        $("#clock").textContent = ui.cdStep; SFX.cd(false); render();
        ui.cdStep--; ui.cdTimer = setTimeout(step, 650);
      } else {
        SFX.cd(true);
        g.begin(nowMs());
        ui.phase = "play";
        holeMsg("밀어요!  " + (settings.mode === "two" ? "" : ""), null);
        render();
      }
    })();
  }

  function onResult(res) {
    ui.phase = "result"; ui.lastResult = res;
    $("#clock").textContent = "끝"; $("#clock").classList.remove("low");
    $(".timebar > i").style.width = "0%";
    holeMsg("", null);
    var any = res.success[0] || res.success[1];
    if (any) SFX.win(); else SFX.lose();
    render();
    if (CM) putSushi(res);
    var last = g.state.round >= g.cfg.rounds;
    var rows = [0, 1].map(function (i) {
      var t = KINDS[res.targets[i]], e = PL[res.eaten[i]];
      if (CM) e = { name: e.name + " · " + C.PATTERNS[e.pattern].name, tier: 1 };
      var vis = targetVisible(i) || true;  // 결과에서는 숨긴 주문도 공개
      return '<div class="row" style="--pc:' + (i ? "var(--p2)" : "var(--p1)") + '"><span class="st">' + seatLabel(i) + "</span><span>주문 <b>" + (CM ? C.SUSHI_NAMES[res.orders[i].sushi] + " 초밥 → " + orderText(res.orders[i]) : t.name) + "</b>" + (CM ? " (" + C.ORDER_TYPES[res.orders[i].type].name + " " + res.orders[i].points + "점)" : "") + " → 먹은 접시 <b>" + e.name + (CM ? "" : " (" + TIER_NAME[e.tier] + ")") + "</b></span>" +
        (res.success[i] ? '<span class="ok">+' + res.points[i] + "점</span>" : '<span class="no">실패</span>') + "</div>";
    }).join("");
    var tag = res.success[0] && res.success[1] ? "둘 다 먹었어요" : any ? "한 자리만 먹었어요" : "아무도 못 먹었어요";
    $("#ov").innerHTML = '<div class="overlay"><div class="card"><h3>라운드 ' + res.round + " 결과 · " + tag + "</h3>" + rows +
      '<div class="stats">이번 라운드 밀기 <b>' + seatLabel(0) + " " + res.pushes[0] + "회 · " + seatLabel(1) + " " + res.pushes[1] + "회</b> / 벨트 이동 <b>" + (res.moved > 0 ? "+" : "") + res.moved + "칸</b></div>" +
      '<button class="btn big" id="nextBtn">' + (last ? "결과 보기" : "다음 라운드") + "  (Space)</button></div></div>";
    $("#nextBtn").addEventListener("click", advance);
  }

  // 결과 순간: 먹는 칸의 접시 위에 두 사람이 만든 초밥을 올려 보여 준다 (맞으면 그대로, 틀리면 흐리게 + 표시)
  function clearSushi() { $$(".pon").forEach(function (e) { e.remove(); }); }
  function putSushi(res) {
    clearSushi();
    [0, 1].forEach(function (i) {
      var el = els.plates[res.eaten[i]]; if (!el) return;
      var box = $(".pon", el); if (!box) { box = document.createElement("div"); box.className = "pon"; el.appendChild(box); }
      var d = document.createElement("div");
      d.className = "pi p" + i + (res.success[i] ? " ok" : " no");
      d.innerHTML = sushiSvg(res.orders[i].sushi) + "<b>" + (res.success[i] ? "O" : "X") + "</b>";
      box.appendChild(d);
    });
  }

  function advance() {
    if (ui.phase !== "result") return;
    clearSushi();
    $("#ov").innerHTML = "";
    g.next();
    if (g.state.phase === "end") return showEnd();
    setIdleUI(); startRound();
  }

  function showEnd() {
    ui.phase = "end"; SFX.end();
    var sm = g.summary(), h = g.state.history, win = sm.scores[0] === sm.scores[1] ? "무승부" : seatLabel(sm.scores[0] > sm.scores[1] ? 0 : 1) + " 승리";
    var table = '<table><tr><th>R</th><th>' + seatLabel(0) + " 주문</th><th>먹음</th><th>" + seatLabel(1) + " 주문</th><th>먹음</th><th>밀기</th><th>이동</th></tr>" +
      h.map(function (r) {
        return "<tr><td>" + r.round + "</td><td>" + (CM ? C.SUSHI_NAMES[r.orders[0].sushi] + " → " + orderText(r.orders[0]) : KINDS[r.targets[0]].name) + "</td><td class=\"" + (r.success[0] ? "ok" : "no") + '">' + PL[r.eaten[0]].name + "</td><td>" + (CM ? C.SUSHI_NAMES[r.orders[1].sushi] + " → " + orderText(r.orders[1]) : KINDS[r.targets[1]].name) + "</td><td class=\"" + (r.success[1] ? "ok" : "no") + '">' + PL[r.eaten[1]].name + "</td><td>" + r.pushes[0] + "/" + r.pushes[1] + "</td><td>" + (r.moved > 0 ? "+" : "") + r.moved + "</td></tr>";
      }).join("") + "</table>";
    $("#clock").textContent = "끝"; holeMsg("", null); render();
    $("#ov").innerHTML = '<div class="overlay"><div class="card"><h3>' + win + " · " + sm.scores[0] + " : " + sm.scores[1] + '</h3><div class="stats">둘 다 먹은 라운드 <b>' + sm.both + "</b> · 한쪽만 <b>" + sm.one + "</b> · 아무도 못 먹음 <b>" + sm.none +
      "</b><br>밀기 사용 <b>" + seatLabel(0) + " " + sm.used[0] + "회 · " + seatLabel(1) + " " + sm.used[1] + "회</b> · 라운드당 평균 이동 <b>" + sm.avgMoved.toFixed(1) + "칸</b></div>" + table +
      '<button class="btn big" id="againBtn">한 판 더  (R)</button></div></div>';
    $("#againBtn").addEventListener("click", function () { newGame(); setIdleUI(); });
  }

  // ---------- 입력 ----------
  var KEYMAP = {
    bot: { ArrowLeft: [0, -1], ArrowRight: [0, 1], KeyA: [0, -1], KeyD: [0, 1] },
    two: { KeyA: [0, -1], KeyD: [0, 1], ArrowLeft: [1, -1], ArrowRight: [1, 1] }
  };
  function doPush(seat, dir) {
    var r = g.push(seat, dir, nowMs());
    if (r.ok) { SFX.push(dir); render(); }
    else if (r.reason !== "inactive") { SFX.deny(); }
    return r;
  }
  document.addEventListener("keydown", function (e) {
    if (e.target && /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.repeat) { if (e.code === "Space" || KEYMAP[settings.mode][e.code]) e.preventDefault(); return; }   // 꾹 누르기 금지: 한 번에 한 번
    if (e.code === "Space") {
      e.preventDefault();
      if (ui.phase === "idle") startRound(); else if (ui.phase === "result") advance();
      return;
    }
    if (e.code === "KeyR" && (ui.phase === "end" || ui.phase === "idle")) { newGame(); setIdleUI(); return; }
    var m = KEYMAP[settings.mode][e.code];
    if (m) { e.preventDefault(); doPush(m[0], m[1]); }
  });

  // ---------- 설정 패널 ----------
  function bindSettings() {
    function sync() {
      $("#sMode").value = settings.mode; $("#sRule").value = settings.seatRule; $("#sPlates").value = settings.plates; $("#sBrake").value = settings.brake;
      $("#sBudget").value = settings.budget; $("#sCoop").value = Math.round(settings.coop * 100); $("#sCap").value = settings.cap; $("#sMs").value = settings.roundMs / 1000; $("#sJit").value = settings.jitter / 1000; $("#sBot").value = settings.botRate;
      $("#sSound").checked = settings.sound;
      $("#rowBudget").classList.toggle("hidden-el", settings.brake !== "budget");
      $("#rowCap").classList.toggle("hidden-el", settings.brake !== "cap");
      $("#rowBot").classList.toggle("hidden-el", settings.mode !== "bot");
      $("#publicNote").classList.toggle("hidden-el", settings.mode !== "two");
    }
    [["sMode", "mode"], ["sPlates", "plates"], ["sRule", "seatRule"], ["sBrake", "brake"]].forEach(function (p) { $("#" + p[0]).addEventListener("change", function (e) { settings[p[1]] = e.target.value; sync(); newGame(); setIdleUI(); }); });
    [["sBudget", "budget", 1], ["sCap", "cap", 1], ["sMs", "roundMs", 1000], ["sJit", "jitter", 1000], ["sBot", "botRate", 1], ["sCoop", "coop", 0.01]].forEach(function (p) {
      $("#" + p[0]).addEventListener("change", function (e) { var v = +e.target.value; if (!(v >= 0) || (p[1] !== "jitter" && p[1] !== "coop" && v <= 0)) return; settings[p[1]] = v * p[2]; newGame(); setIdleUI(); });
    });
    $("#sSound").addEventListener("change", function (e) { settings.sound = e.target.checked; });
    sync();
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindSettings();
    $("#holeBtn").addEventListener("click", function () { if (ui.phase === "idle") startRound(); });
    [0, 1].forEach(function (i) {
      $$("#pad" + i + " button").forEach(function (b) { b.addEventListener("click", function () { doPush(i, +b.getAttribute("data-dir")); }); });
    });
    $("#restart").addEventListener("click", function () { newGame(); setIdleUI(); });
    newGame(); setIdleUI();
    requestAnimationFrame(frame);
  });
})();
