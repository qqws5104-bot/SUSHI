// 회전초밥 벨트 시험판을 Render 같은 Node 웹 서비스로 띄우는 최소 서버. 의존성 없음.
// 실행: node server.js  (PORT 환경변수가 있으면 그 포트, 없으면 3000)
"use strict";
const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = process.env.PORT || 3000;
const PAGE = path.join(__dirname, "belt_proto.html");   // python3 build.py 로 만든 한 파일짜리 시험판

const server = http.createServer((req, res) => {
  const url = (req.url || "/").split("?")[0];
  if (url === "/health") { res.writeHead(200, { "Content-Type": "text/plain" }); return res.end("ok"); }
  if (url === "/" || url === "/index.html" || url === "/belt_proto.html") {
    fs.readFile(PAGE, (err, buf) => {
      if (err) { res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" }); return res.end("belt_proto.html 이 없어요. python3 build.py 를 먼저 실행하세요."); }
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-cache" });
      res.end(buf);
    });
    return;
  }
  res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
  res.end("not found");
});
server.listen(PORT, () => console.log("sushi belt on :" + PORT));
