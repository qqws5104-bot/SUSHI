// 재료 정리(소코반) 판 생성기 -- 사용: node gen_soko_pool.js <가로> <세로> <판수> <상자수> <최소이동> <최대이동> [시드]
// 벽 테두리 + 무작위 안쪽 벽, 상자를 접시 칸에 놓고 역방향(당기기)으로 섞은 뒤 BFS로 최적 이동 수(밀기 포함 키 수)를 재서 범위 안인 판만 모은다.
"use strict";
const [W, H, N, NB, LO, HI, SEED] = process.argv.slice(2).map(Number);
let s = (SEED || 7) >>> 0;
const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296), ri = (n) => Math.floor(rnd() * n);
const D = [[0, -1], [0, 1], [-1, 0], [1, 0]];
function solve(wall, tgtSet, p0, boxes0, cap) {
  const NC = W * H, enc = (p, bx) => { let k = p; for (const b of bx) k = k * NC + b; return k; };
  const sorted = (a) => a.slice().sort((x, y) => x - y);
  const start = sorted(boxes0), goal = (bx) => bx.every((b) => tgtSet.has(b));
  if (goal(start)) return 0;
  let frontier = [[p0, start]], seen = new Set([enc(p0, start)]), depth = 0;
  while (frontier.length && depth < cap) {
    depth++; const next = [];
    for (const [p, bx] of frontier) for (const [dx, dy] of D) {
      const x = (p % W) + dx, y = ((p / W) | 0) + dy, ni = y * W + x; if (wall[ni]) continue;
      let nb = bx; const bi = bx.indexOf(ni);
      if (bi >= 0) { const mi = (y + dy) * W + x + dx; if (wall[mi] || bx.indexOf(mi) >= 0) continue; nb = bx.slice(); nb[bi] = mi; nb = sorted(nb); }
      const k = enc(ni, nb); if (seen.has(k)) continue; seen.add(k);
      if (goal(nb)) return depth; next.push([ni, nb]);
    }
    frontier = next;
  }
  return null;
}
const out = []; const seenKey = new Set(); let tries = 0;
while (out.length < N && tries < (Number(process.env.MAXTRIES) || 200000)) {
  tries++;
  const wall = new Array(W * H).fill(false);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (x === 0 || y === 0 || x === W - 1 || y === H - 1 || rnd() < (Number(process.env.WD) || 0.16)) wall[y * W + x] = true;
  const freeCells = () => { const a = []; for (let i = 0; i < W * H; i++) if (!wall[i]) a.push(i); return a; };
  let fc = freeCells(); if (fc.length < 20) continue;
  const pick = (a) => a.splice(ri(a.length), 1)[0];
  const tg = []; for (let k = 0; k < NB; k++) tg.push(pick(fc));
  // 역방향 무작위 걷기: 플레이어가 움직이면서 (뒤에 상자가 있으면) 상자를 끌어당긴다
  let boxes = tg.slice(), p = pick(fc.slice());
  if (boxes.includes(p)) continue;
  const tgtSet = new Set(tg); let found = null;
  for (let step = 0; step < (Number(process.env.WALK) || 1500) && !found; step++) {
    const [dx, dy] = D[ri(4)], x = (p % W) + dx, y = ((p / W) | 0) + dy, ni = y * W + x;
    if (wall[ni] || boxes.includes(ni)) continue;
    const back = ((p / W) | 0) - dy, backX = (p % W) - dx, bi = boxes.indexOf(back * W + backX);
    if (bi >= 0 && rnd() < 0.9) boxes[bi] = p; // 당기기
    p = ni;
    if (step % 60 === 59 && !boxes.every((b) => tg.includes(b))) {
      const len = solve(wall, tgtSet, p, boxes, HI + 1);
      if (len !== null && len >= LO && len <= HI) found = { len, p, boxes: boxes.slice() };
    }
  }
  if (!found) continue;
  const len = found.len; p = found.p; boxes = found.boxes;
  const rows = []; for (let y = 0; y < H; y++) { let r = ""; for (let x = 0; x < W; x++) { const i = y * W + x, isT = tgtSet.has(i), isB = boxes.includes(i), isP = i === p; r += wall[i] ? "#" : isB ? (isT ? "*" : "$") : isP ? (isT ? "+" : "@") : isT ? "." : " "; } rows.push(r); }
  const key = rows.join("|"); if (seenKey.has(key)) continue; seenKey.add(key);
  out.push({ rows, len });
}
console.error(`${out.length}판 (시도 ${tries}) 최적 이동: ` + out.map((o) => o.len).join(","));
console.log("[" + out.map((o) => "[" + o.rows.map((r) => JSON.stringify(r)).join(",") + "]").join(",\n ") + "]");
