#!/usr/bin/env python3
"""belt_page.html + belt.css + belt-core.js + belt-ui.js -> belt_proto.html (단독 실행 파일)."""
import os
d = os.path.dirname(os.path.abspath(__file__))
rd = lambda n: open(os.path.join(d, n), encoding="utf-8").read()
html = rd("belt_page.html").replace("/*__CSS__*/", rd("belt.css")).replace("/*__CORE__*/", rd("belt-core.js")).replace("/*__UI__*/", rd("belt-ui.js"))
open(os.path.join(d, "belt_proto.html"), "w", encoding="utf-8").write(html)
print("belt_proto.html", len(html) // 1024, "KB")
