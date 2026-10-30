#!/usr/bin/env python3
"""Prepare only the existing README for the owner-authorized r2 release."""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[2]
root = ROOT


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


require(blob((root / "README.md").read_bytes()) == "a37c0b223152a153dd555aec59ee0251404c8431", "README changed; do not overwrite")
require(blob((root / ".github/workflows/release.yml").read_bytes()) == "c7b494677e26ea3a5b6aadf06dcdfc4203236121", "Release workflow is not the reviewed ten-round gate")
# Update only the existing README; keep historical release distinctions honest.
p=root/'README.md';s=p.read_text(encoding='utf-8')
s=s.replace('\u6e90\u7801\u4fee\u6b63\uff08\u5c1a\u672a\u53d1\u5e03\u65b0\u5305\uff09', '\u6e90\u7801\u4fee\u6b63',1)
s=s.replace('\u540c\u65e5\u5341\u8f6e\u590d\u67e5\u8865\u5145\uff08\u4ecd\u672a\u53d1\u5e03\uff09','\u540c\u65e5\u5341\u8f6e\u590d\u67e5\u8865\u5145',1)
s=s.replace('\u6b63\u5f0f\u9644\u4ef6\u4ecd\u672a\u5305\u542b\u8fd9\u4e24\u6b21\u6e90\u7801\u4fee\u590d\u3002', '\u4e0a\u8ff0\u4fee\u590d\u7684\u53d1\u884c\u76ee\u6807\u4e3a `v0.166.0-portable.2`\uff1b\u65e7 r1 \u9644\u4ef6\u4e0d\u4f1a\u88ab\u8986\u76d6\u3002',1)
anchor='### \u4ee3\u7406\u4e0e\u8d26\u53f7\u68c0\u67e5\n\n'
require(s.count(anchor)==1,'README gate anchor')
paragraph=('**Portable r2 \u53d1\u5e03\u95e8\u7981\uff1a** \u4e24\u6b21\u4ee3\u7406\u4fee\u590d\u4f7f\u7528\u540c\u4e00\u5b98\u65b9 0.166.0 \u8fd0\u884c\u65f6\uff0c\u4e0d\u66f4\u6539\u8ba4\u8bc1\u6216\u6743\u9650\u9ed8\u8ba4\u503c\u3002\u6b63\u5f0f\u6253\u5305\u524d\u5fc5\u987b\u5728 Windows runner \u4f7f\u7528\u5305\u5185 Python \u5b8c\u6210\u5f53\u524d\u6e90\u7801\u7684\u5168\u91cf\u95e8\u7981\u548c\u65b0\u7684 10 \u8f6e\u968f\u673a\u79cd\u5b50\u56de\u5f52\uff0c\u6e90\u7801\u53d8\u5316\u6216\u4efb\u4e00\u5931\u8d25\u3001\u9519\u8bef\u3001\u8df3\u8fc7\u5747\u963b\u6b62\u53d1\u5e03\u3002\u5341\u8f6e\u5305\u542b\u4ee3\u7406\u5355\u5143\u3001\u56de\u73af TCP/\u5b50\u8fdb\u7a0b\u3001h11 \u4e92\u64cd\u4f5c\u4e0e\u8fd0\u884c\u65f6/\u6a21\u5f0f\u526f\u672c/\u6253\u5305\u56de\u5f52\uff0c\u4e0d\u5c06\u5b83\u79f0\u4e3a\u6574\u4e2a\u4ea7\u54c1\u5341\u6b21\u771f\u673a\u9a8c\u6536\u3002\u53d1\u5e03\u72b6\u6001\u548c\u771f\u5b9e\u7ed3\u679c\u4ee5\u5bf9\u5e94 Release/Actions \u4e3a\u51c6\u3002\n\n')
s=s.replace(anchor,anchor+paragraph,1);prepared = s.encode('utf-8')
print('Prepared audited runner and additive release gate; formal workflow remains manual.')

require(blob(prepared) == "89596f1e83eeef1cb26770a8be29d3cb2775abc2", "README output differs from reviewed bytes")
(root / "README.md").write_bytes(prepared)
print("README_RELEASE_PREPARATION=PASS runtime_unchanged=true")
