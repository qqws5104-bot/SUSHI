// 회전초밥 벨트 규칙 코어 (2026-10-08).
// 순환 벨트(기본 12칸, 맛 8종)를 두 사람이 서로 밀고, 끝났을 때 자기 자리 앞에 멈춘 접시가 내 주문(맛)이면 그 접시의 점수.
// 시간(now, ms)과 난수(rng)를 밖에서 넣어 주는 순수 모듈 -- 브라우저(UI)와 node(테스트/시뮬레이션) 둘 다에서 쓴다.
//
// 용어
//   칸(slot)   : 벨트 위의 고정 위치 0..N-1. 숫자가 커지는 쪽 = 시계 방향.
//   접시(plate): 벨트에 실린 접시. 인덱스 p는 벨트가 회전해도 안 바뀐다. 접시 p가 있는 칸 = (p + off) mod N.
//   맛(kind)   : 접시의 종류(0..K-1). 같은 맛 접시가 벨트에 여러 개 있을 수 있다. 주문은 "맛"이다 -- 어느 복사본을 먹어도 된다.
//   off        : 벨트가 지금까지 돈 칸 수(누적 정수, 음수 가능). 밀기 +1 = 시계 방향 한 칸.
//   자리(seat) : 사람 0/1이 앉은 칸 번호(cfg.seats). seatRule "fixed"에서만 각자 자리, "any"(기본)에서는 seats[0] 한 칸을 둘이 공유.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.BeltCore = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // 맛 8종. tier = 접시 색(가격대): 1 흰(1점) / 2 파랑(2점) / 3 금(3점).
  var KINDS = [
    { key: "salmon", name: "연어", tier: 2 },
    { key: "tuna", name: "참치", tier: 3 },
    { key: "egg", name: "계란", tier: 1 },
    { key: "shrimp", name: "새우", tier: 2 },
    { key: "eel", name: "장어", tier: 3 },
    { key: "tofu", name: "유부", tier: 1 },
    { key: "octopus", name: "문어", tier: 2 },
    { key: "ikura", name: "연어알", tier: 3 }
  ];
  // 벨트 12칸의 배치(맛 인덱스). 설계 규칙:
  //  1) 정반대 칸 쌍(i, i+6)은 같은 가격대 -- 둘의 주문이 맞물려 둘 다 먹는 경우가 한쪽에만 이득이 되지 않게.
  //  2) 같은 맛 복사본(연어, 참치, 계란, 유부)은 서로 정반대가 아니고 3칸 떨어져 있다 -- 정반대면 두 자리가 항상 같은 맛을 보게 된다.
  //  3) 가격대가 칸마다 2-3-1 순서로 번갈아 돈다 (싼 접시와 비싼 접시가 고르게 섞임).
  var LAYOUT = [0, 1, 2, 3, 4, 5, 6, 7, 5, 0, 1, 2];
  var PLATES = LAYOUT.map(function (k) { return { key: KINDS[k].key, name: KINDS[k].name, tier: KINDS[k].tier, kind: k }; });

  // 처음 만든 6칸 6종(맛이 전부 한 번씩). 규칙 테스트와 비교용으로 남겨 둔다.
  var PLATES6 = [0, 1, 2, 3, 4, 5].map(function (k) { return { key: KINDS[k].key, name: KINDS[k].name, tier: KINDS[k].tier, kind: k }; });

  // ---- 색 모드 (2026-10-08): 접시 색 = 목적지 ("층"). 주문 종류가 몇 색(또는 무늬)을 받아 주는지 정한다 ----
  // 색 10가지, 벨트 10칸에 한 장씩. 비슷한 색(빨-분홍, 주-노, 검-회, 파-보)이 이웃하지 않도록 배치.
  var COLORS = [
    { key: "red", name: "빨강", hex: "#d8432f" },
    { key: "orange", name: "주황", hex: "#ef8a2b" },
    { key: "yellow", name: "노랑", hex: "#f2cf3a" },
    { key: "green", name: "초록", hex: "#4aa35a" },
    { key: "blue", name: "파랑", hex: "#3b78c2" },
    { key: "purple", name: "보라", hex: "#7d5bb5" },
    { key: "pink", name: "분홍", hex: "#f08fb4" },
    { key: "white", name: "흰색", hex: "#f4efe4" },
    { key: "black", name: "검정", hex: "#2b2b30" },
    { key: "gray", name: "회색", hex: "#9a9aa3" }
  ];
  // 무늬 5종, 각각 접시 두 장에 그려진다 (색과 무늬는 독립). 색만으로 구분하지 않게 하는 역할도 겸한다.
  var PATTERNS = [
    { key: "dots", name: "물방울" }, { key: "stripes", name: "줄무늬" }, { key: "star", name: "별" },
    { key: "heart", name: "하트" }, { key: "check", name: "체크" }
  ];
  var LAYOUT_COLOR = [0, 4, 2, 8, 3, 6, 1, 9, 5, 7];       // 칸 순서: 빨 파 노 검 초 분 주 회 보 흰
  var LAYOUT_PATTERN = [0, 1, 2, 3, 0, 4, 1, 2, 3, 4];     // 같은 무늬 두 장은 서로 이웃하지 않고 4~5칸 떨어짐
  var PLATES_COLOR = LAYOUT_COLOR.map(function (c, i) { return { key: COLORS[c].key, name: COLORS[c].name, tier: 1, kind: c, pattern: LAYOUT_PATTERN[i] }; });
  // 주문표 = "무슨 초밥을(sushi) 어느 접시에(plate rule) 올려라". 주문 종류가 만들 초밥의 급을 정한다 (택배 4종의 초밥 버전).
  //   points = 원래 보상금(2500/3000/5000/10000)을 비율대로 반올림, weight = 원래 택배 수(4/6/4/3).
  //   접시 규칙 -- normal: 두 색 중 아무 접시나 / fixed: 지정된 색 한 가지 또는 무늬 한 가지 / fragile, valuable: 정확히 한 색
  //   sushis = 이 종류의 주문표에 나올 수 있는 초밥 (쉬운 것 -> 비싼 것). 주문마다 이 중 하나가 무작위로 붙는다.
  var SUSHI_NAMES = { egg: "계란", tofu: "유부", shrimp: "새우", octopus: "문어", salmon: "연어", ikura: "연어알", eel: "장어", tuna: "참치" };
  var ORDER_TYPES = {
    normal: { name: "일반", points: 2, weight: 4, sushis: ["egg", "tofu"] },
    fixed: { name: "지정", points: 3, weight: 6, sushis: ["shrimp", "octopus"] },
    fragile: { name: "중급", points: 5, weight: 4, sushis: ["salmon", "ikura"] },
    valuable: { name: "특선", points: 10, weight: 3, sushis: ["eel", "tuna"] }
  };
  var PRESET_COLOR = { plates: PLATES_COLOR, seats: [0, 5], seatRule: "any", pointsBy: "order" };

  var DEFAULTS = {
    plates: PLATES,
    seats: [9, 3],          // 사람 0/1의 자리(칸 번호). "any"(한 칸 공유)에서는 seats[0]이 공유하는 먹는 칸이고 seats[1]은 안 쓰인다 (기본 9 = 6시 방향)
    seatRule: "any",        // "any": 한 칸을 같이 쓴다 -- 끝났을 때 그 칸에 멈춘 접시를 둘 다 자기 주문과 비교한다 (엘리베이터와 같은 규칙) / "fixed": 각자 자리가 있고 내 앞 접시만 먹는다 (seats [0, 6] 같은 정반대 두 칸)
    brake: "budget",        // "budget": 하프 전체 밀기 총량 제한 / "cap": 라운드 시작 위치에서 최대 cap칸 / "free": 제한 없음
    budget: 48,             // brake==="budget"일 때 한 사람의 하프 전체 밀기 횟수
    cap: 4,                 // brake==="cap"일 때 라운드 시작 위치에서 벗어날 수 있는 최대 칸 수
    rounds: 7,
    roundMs: 5000,
    endJitter: 1000,        // 막판 매복 방지: 실제 종료는 roundMs ±endJitter 사이 무작위(플레이어는 모른다). 0이면 정확히 roundMs
    coopDeal: 0.3,          // 주문을 나눌 때 이 확률로 "벨트를 어느 위치로 돌리면 두 사람 주문이 동시에 맞는" 쌍을 준다 (본인들은 모른다)
    tierPoints: { 1: 1, 2: 2, 3: 3 },
    pointsBy: "plate",      // "plate": 먹은 접시의 가격대(tier)가 점수 / "order": 주문에 붙은 초밥 등급(state.grades)이 점수 (색 모드)
    rng: Math.random
  };

  function mod(a, n) { return ((a % n) + n) % n; }
  function mulberry32(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function create(userCfg) {
    var cfg = {}, k;
    for (k in DEFAULTS) cfg[k] = DEFAULTS[k];
    for (k in (userCfg || {})) cfg[k] = userCfg[k];
    var N = cfg.plates.length;
    var K = 1 + Math.max.apply(null, cfg.plates.map(function (p) { return p.kind; }));
    if (cfg.seats.length !== 2 || cfg.seats.some(function (s) { return s < 0 || s >= N; }) || cfg.seats[0] === cfg.seats[1]) throw new Error("seats must be two different slots in 0.." + (N - 1));
    if (["fixed", "any"].indexOf(cfg.seatRule) < 0) throw new Error("bad seatRule");
    if (["budget", "cap", "free"].indexOf(cfg.brake) < 0) throw new Error("bad brake");

    var state = {
      round: 0, phase: "idle",            // idle(라운드 시작 대기) / active / result / end
      off: 0, startOff: 0,
      budget: [cfg.budget, cfg.budget], used: [0, 0],   // used: 하프 전체에서 실제로 민 횟수
      pushes: [0, 0],                     // 이번 라운드에서 민 횟수
      targets: [null, null],              // 맛 또는 색(kind) 인덱스
      orders: [null, null],               // pointsBy 'order'(색 모드)일 때 각자 주문 {type, colors, pattern, plates, points}
      scores: [0, 0],
      endAt: 0, earliestEnd: 0, dealt: false,
      events: [],                         // 이번 라운드의 밀기 기록 {t(라운드 시작 후 ms), seat, dir}
      roundStart: 0,
      history: []
    };

    function slotOf(p) { return mod(p + state.off, N); }
    function plateAt(slot) { return mod(slot - state.off, N); }
    function kindAtSlot(slot, off) { return cfg.plates[mod(slot - (off == null ? state.off : off), N)].kind; }
    function goalSlot(i) { return cfg.seatRule === "any" ? cfg.seats[0] : cfg.seats[i]; }
    // 사람 i가 먹게 되는 접시 (지금 벨트가 이 자리에서 멈춘다면)
    function eatenBy(i) { return plateAt(goalSlot(i)); }
    // 맛 kind의 접시를 사람 i의 자리 앞으로 가져오는 방법 전부: 복사본마다 {plate, steps(부호 포함, +는 시계 방향)}. 가까운 순.
    function optionsToSeat(kind, i) {
      var goal = goalSlot(i), out = [];
      cfg.plates.forEach(function (pl, p) {
        if (pl.kind !== kind) return;
        var d = mod(goal - slotOf(p), N);
        out.push({ plate: p, steps: d === 0 ? 0 : (d <= N / 2 ? d : d - N) });
      });
      out.sort(function (a, b) { return Math.abs(a.steps) - Math.abs(b.steps) || b.steps - a.steps; });
      return out;
    }
    // 가장 가까운 복사본까지 필요한 이동 (부호 포함, 0이면 이미 와 있음)
    function stepsToSeat(kind, i) { return optionsToSeat(kind, i)[0].steps; }

    // 라운드 시작 전에 주문(맛)을 미리 뽑아 보여 줄 수 있다 (카운트다운 동안 계획 세울 시간).
    // coopDeal 확률로: 벨트를 s칸 돌렸을 때 두 자리 앞에 오는 맛을 각각의 주문으로 준다 -- 동시에 맞출 길이 반드시 하나 있는 쌍.
    // 색 모드: 접시 m을 반드시 받아 주는 주문 하나를 만든다 (m이 null이면 무작위 접시). 종류는 원래 택배 비율대로.
    function makeOrder(mustPlate) {
      var keys = Object.keys(ORDER_TYPES), total = 0, r, type = keys[0], i;
      keys.forEach(function (k) { total += ORDER_TYPES[k].weight; });
      r = cfg.rng() * total;
      for (i = 0; i < keys.length; i++) { r -= ORDER_TYPES[keys[i]].weight; if (r < 0) { type = keys[i]; break; } }
      var m = mustPlate == null ? Math.floor(cfg.rng() * N) : mustPlate, mp = cfg.plates[m], colors = [mp.kind], pattern = null;
      if (type === "normal") {
        var other;
        do { other = Math.floor(cfg.rng() * K); } while (other === mp.kind);
        colors = cfg.rng() < 0.5 ? [mp.kind, other] : [other, mp.kind];
      } else if (type === "fixed" && cfg.rng() < 0.5) {
        colors = []; pattern = mp.pattern;
      }
      var plates = [];
      cfg.plates.forEach(function (pl, p) { if (pattern != null ? pl.pattern === pattern : colors.indexOf(pl.kind) >= 0) plates.push(p); });
      var pool = ORDER_TYPES[type].sushis;
      return { type: type, sushi: pool[Math.floor(cfg.rng() * pool.length)], colors: colors, pattern: pattern, plates: plates, points: ORDER_TYPES[type].points };
    }
    // 사람 i의 주문이 접시 p를 받아 주는가
    function accepts(i, p) {
      if (cfg.pointsBy === "order") return state.orders[i] != null && state.orders[i].plates.indexOf(p) >= 0;
      return cfg.plates[p].kind === state.targets[i];
    }
    // 사람 i의 주문을 만족시키는 접시 전부와 그 접시를 자리 앞으로 가져오는 이동 (부호 포함), 가까운 순
    function optionsToOrder(i) {
      var goal = goalSlot(i), out = [];
      cfg.plates.forEach(function (pl, p) {
        if (!accepts(i, p)) return;
        var d = mod(goal - slotOf(p), N);
        out.push({ plate: p, steps: d === 0 ? 0 : (d <= N / 2 ? d : d - N) });
      });
      out.sort(function (a, b) { return Math.abs(a.steps) - Math.abs(b.steps) || b.steps - a.steps; });
      return out;
    }
    function stepsToOrder(i) { var o = optionsToOrder(i); return o.length ? o[0].steps : 0; }

    function deal() {
      if (state.phase !== "idle" || state.dealt) return false;
      var coop = cfg.rng() < cfg.coopDeal, s = coop ? Math.floor(cfg.rng() * N) : 0;
      if (cfg.pointsBy === "order") {
        var m0 = coop ? plateAt2(goalSlot(0), state.off + s) : null, m1 = coop ? plateAt2(goalSlot(1), state.off + s) : null;
        state.orders = [makeOrder(m0), makeOrder(m1)];
        state.targets = [state.orders[0].colors.length ? state.orders[0].colors[0] : cfg.plates[state.orders[0].plates[0]].kind, state.orders[1].colors.length ? state.orders[1].colors[0] : cfg.plates[state.orders[1].plates[0]].kind];
      } else if (coop) {
        state.targets = [kindAtSlot(goalSlot(0), state.off + s), kindAtSlot(goalSlot(1), state.off + s)];
      } else {
        state.targets = [Math.floor(cfg.rng() * K), Math.floor(cfg.rng() * K)];
      }
      state.dealt = true;
      return true;
    }
    function plateAt2(slot, off) { return mod(slot - off, N); }

    function begin(now) {
      if (state.phase !== "idle") return false;
      if (!state.dealt) deal();
      state.dealt = false;
      state.round++;
      state.phase = "active";
      state.startOff = state.off;
      state.pushes = [0, 0];
      state.events = [];
      state.roundStart = now;
      state.earliestEnd = now + cfg.roundMs - cfg.endJitter;       // 가장 이른 종료 시각 (화면의 시계는 여기까지만 센다)
      state.endAt = now + cfg.roundMs + Math.round((cfg.rng() * 2 - 1) * cfg.endJitter);
      return true;
    }

    function push(seat, dir, now) {
      if (state.phase !== "active" || now >= state.endAt) return { ok: false, reason: "inactive" };
      if (dir !== 1 && dir !== -1) return { ok: false, reason: "bad-dir" };
      if (cfg.brake === "budget" && state.budget[seat] <= 0) return { ok: false, reason: "no-budget" };
      if (cfg.brake === "cap" && Math.abs(state.off + dir - state.startOff) > cfg.cap) return { ok: false, reason: "cap" };
      state.off += dir;
      if (cfg.brake === "budget") state.budget[seat]--;
      state.used[seat]++;
      state.pushes[seat]++;
      state.events.push({ t: now - state.roundStart, seat: seat, dir: dir });
      return { ok: true, off: state.off };
    }

    function finish() {
      var eaten = [eatenBy(0), eatenBy(1)], success = [], points = [0, 0], i;
      for (i = 0; i < 2; i++) {
        success[i] = accepts(i, eaten[i]);
        if (success[i]) points[i] = cfg.pointsBy === "order" ? state.orders[i].points : cfg.tierPoints[cfg.plates[eaten[i]].tier];
        state.scores[i] += points[i];
      }
      var res = {
        round: state.round, targets: state.targets.slice(), orders: state.orders.slice(), eaten: eaten, success: success, points: points,
        pushes: state.pushes.slice(), moved: state.off - state.startOff, off: state.off,
        budgetLeft: state.budget.slice()
      };
      state.history.push(res);
      state.phase = "result";
      return res;
    }

    function tick(now) {
      if (state.phase === "active" && now >= state.endAt) return finish();
      return null;
    }

    function next() {
      if (state.phase !== "result") return false;
      state.phase = state.round >= cfg.rounds ? "end" : "idle";
      return true;
    }

    // 한 판 요약 (플레이 테스트 후 규칙 판단용): 둘 다 먹은 라운드 / 한쪽만 / 아무도 못 먹은 라운드, 밀기 사용량.
    function summary() {
      var both = 0, one = 0, none = 0;
      state.history.forEach(function (h) {
        var n = (h.success[0] ? 1 : 0) + (h.success[1] ? 1 : 0);
        if (n === 2) both++; else if (n === 1) one++; else none++;
      });
      return {
        rounds: state.history.length, both: both, one: one, none: none,
        scores: state.scores.slice(), used: state.used.slice(),
        avgMoved: state.history.length ? state.history.reduce(function (a, h) { return a + Math.abs(h.moved); }, 0) / state.history.length : 0
      };
    }

    return {
      cfg: cfg, N: N, K: K, state: state,
      slotOf: slotOf, plateAt: plateAt, eatenBy: eatenBy, optionsToSeat: optionsToSeat, stepsToSeat: stepsToSeat,
      accepts: accepts, optionsToOrder: optionsToOrder, stepsToOrder: stepsToOrder, deal: deal, begin: begin, push: push, tick: tick, next: next, summary: summary
    };
  }

  // 컴퓨터 상대. 연타 속도(rate, 초당 밀기)와 아끼는 정도(thrift)만 있는 단순한 반응형:
  // 자기 주문이 자기 자리 앞에 없으면 가장 가까운 복사본 쪽으로 민다. 이미 와 있으면 가만히 있다가 밀려나면 되받는다.
  // 상대 주문은 모른다(숨겨진 정보). 예산이 있으면 남은 라운드로 나눈 평균치의 thrift배까지만 쓴다.
  function makeBot(game, seat, opt, rng) {
    opt = opt || {}; rng = rng || Math.random;
    var rate = opt.rate || 3, thrift = opt.thrift == null ? 1.4 : opt.thrift, nextAt = 0;
    return {
      opt: { rate: rate, thrift: thrift },
      // 프레임/타이머마다 불러준다. 밀었으면 방향(+1/-1), 아니면 0.
      step: function (now) {
        var s = game.state;
        if (s.phase !== "active" || now < nextAt) return 0;
        nextAt = now + (1000 / rate) * (0.6 + 0.8 * rng());
        var d = game.cfg.pointsBy === "order" ? game.stepsToOrder(seat) : game.stepsToSeat(s.targets[seat], seat);
        if (d === 0) return 0;
        if (game.cfg.brake === "budget") {
          var roundsLeft = game.cfg.rounds - s.round + 1;
          if (s.pushes[seat] >= (s.budget[seat] + s.pushes[seat]) / roundsLeft * thrift) return 0;
        }
        var dir = d > 0 ? 1 : -1;
        return game.push(seat, dir, now).ok ? dir : 0;
      }
    };
  }

  return { COLORS: COLORS, LAYOUT_COLOR: LAYOUT_COLOR, PLATES_COLOR: PLATES_COLOR, PATTERNS: PATTERNS, SUSHI_NAMES: SUSHI_NAMES, ORDER_TYPES: ORDER_TYPES, PRESET_COLOR: PRESET_COLOR, KINDS: KINDS, LAYOUT: LAYOUT, PLATES: PLATES, PLATES6: PLATES6, DEFAULTS: DEFAULTS, create: create, makeBot: makeBot, mulberry32: mulberry32, mod: mod };
});
