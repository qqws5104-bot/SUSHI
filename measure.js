const { chromium } = require("playwright");
(async()=>{
 const b = await chromium.launch(); const p = await b.newPage({viewport:{width:1280,height:820}});
 await p.goto("file:///home/claude/project/sushi_belt/belt_proto.html?test=1&sound=0&mode=two&seed=7&jitter=0&seatRule=any");
 const r = await p.evaluate(()=>{ const belt=document.querySelector(".belt").getBoundingClientRect(), cx=belt.left+belt.width/2, cy=belt.top+belt.height/2;
  return [...document.querySelectorAll(".seatf")].map(f=>{const q=f.getBoundingClientRect(); return [(q.left+q.width/2-cx).toFixed(0),(q.top+q.height/2-cy).toFixed(0)];}); });
 console.log("fixed frames (seats 0,5):", JSON.stringify(r));
 await b.close();
})();
