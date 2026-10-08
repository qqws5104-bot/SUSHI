const { chromium } = require("playwright");
(async()=>{
 const b = await chromium.launch();
 for (const [n,w,h] of [["d",1280,820],["m",390,860]]) {
  const p = await b.newPage({viewport:{width:w,height:h}});
  await p.goto("file:///home/claude/project/sushi_belt/belt_proto.html?test=1&sound=0&mode=two&seed=21&jitter=0");
  await p.keyboard.press("Space"); await p.waitForTimeout(4200);
  for(let i=0;i<2;i++) await p.keyboard.press("KeyD"); await p.waitForTimeout(900);
  await p.screenshot({path:"/tmp/claude-0/-home-claude/e04d0e7b-388e-5a8d-98e3-060dfe2eabda/scratchpad/shared_"+n+".png"});
  await p.close();
 }
 await b.close();
})();
