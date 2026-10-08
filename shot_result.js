const { chromium } = require("playwright");
(async()=>{
 const b = await chromium.launch(); const S="/tmp/claude-0/-home-claude/e04d0e7b-388e-5a8d-98e3-060dfe2eabda/scratchpad/";
 const p = await b.newPage({viewport:{width:1280,height:900}});
 await p.goto("file:///home/claude/project/sushi_belt/belt_proto.html?test=1&sound=0&mode=two&seed=33&jitter=0&roundMs=1500");
 await p.keyboard.press("Space"); await p.waitForTimeout(500); await p.screenshot({path:S+"order_card.png"});
 await p.waitForFunction(()=>window.__belt.game.state.phase==="active");
 const need = await p.evaluate(()=>window.__belt.game.stepsToOrder(0));
 for (let i=0;i<Math.abs(need);i++) await p.keyboard.press(need>0?"KeyD":"KeyA");
 await p.waitForFunction(()=>window.__belt.game.state.phase==="result"); await p.waitForTimeout(900);
 await p.evaluate(()=>{document.querySelector("#ov").style.display="none";}); await p.screenshot({path:S+"result_plate.png"});
 await b.close();
})();
