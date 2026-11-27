#!/usr/bin/env python3
"""관찰일지 한글(.hwpx) 틀 만들기.

사용자가 한글로 만든 관찰일지 .hwpx(한 달치, 하루 한 쪽)에서 하루치 쪽의 모양만 뽑아
index.html의 <script type="application/json" id="hwpxTpl"> 안에 넣습니다.
틀에는 실제 이름·날짜 같은 내용을 남기지 않고 {{...}} 자리표시만 남깁니다.
원본 .hwpx는 요원 실명이 들어 있으므로 저장소에 올리지 않습니다.

    python3 tools/build_hwpx_template.py 원본.hwpx index.html

lxml이 필요합니다(python-hwpx를 설치하면 함께 설치됨).
"""
import json
import re
import sys
import zipfile
from copy import deepcopy

from lxml import etree

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def strip_ns(s):
    """잘라 낸 조각에 lxml이 붙인 xmlns 선언을 뺌(문서 맨 위 hs:sec에 모두 선언돼 있음)."""
    return re.sub(r' xmlns:[A-Za-z0-9]+="[^"]*"', "", s)


def ser(el):
    return strip_ns(etree.tostring(el, encoding="unicode"))


def drop_linesegs(el):
    """줄 배치 정보(hp:linesegarray)는 지움. 한글이 열 때 다시 계산함."""
    for ls in list(el.iter(HP + "linesegarray")):
        ls.getparent().remove(ls)


def text_of(el):
    return "".join(t.text or "" for t in el.iter(HP + "t"))


def set_text(tc, value):
    ts = list(tc.iter(HP + "t"))
    assert ts, "글이 없는 칸"
    ts[0].text = value
    for t in ts[1:]:
        t.text = ""


def main(src, html_path):
    z = zipfile.ZipFile(src)
    raw = {n: z.read(n).decode("utf-8") for n in z.namelist() if n != "Preview/PrvImage.png"}
    sec_raw = raw["Contents/section0.xml"]
    sec_open = sec_raw[: sec_raw.index(">", sec_raw.index("<hs:sec")) + 1]

    root = etree.fromstring(sec_raw.encode("utf-8"))
    paras = list(root)
    # 첫 쪽: 0 결재(쪽 설정 포함), 1~4 빈 줄, 5 제목, 6 빈 줄, 7 큰 표, 8 빈 줄, 9 맨 아래 문구
    page = [deepcopy(p) for p in paras[:10]]
    for p in page:
        drop_linesegs(p)
    assert "관찰일지" in text_of(page[5]) and text_of(page[9]).startswith("※"), "예상한 양식 모양이 아님"

    # 0: 결재 표. 첫 쪽은 쪽 설정(secPr) 포함, 다음 쪽부터는 쪽 나누기로 시작
    p0 = page[0]
    sign = p0.find(".//" + HP + "tbl")
    sign.set("id", "{{TID0}}")
    sign.set("zOrder", "{{Z0}}")
    p0_first = ser(p0)
    p0n = deepcopy(p0)
    p0n.set("pageBreak", "1")
    p0n.set("id", "0")
    for run in list(p0n.findall(HP + "run")):
        if run.find(HP + "secPr") is not None:
            p0n.remove(run)
    p0_next = ser(p0n)

    # 7: 큰 표(기관명 줄 + 머리 두 줄 + 요원 줄)
    p7 = page[7]
    tbl = p7.find(".//" + HP + "tbl")
    tbl.set("id", "{{TID1}}")
    tbl.set("zOrder", "{{Z1}}")
    trs = tbl.findall(HP + "tr")
    head_h = int(trs[0].find(HP + "tc/" + HP + "cellSz").get("height"))
    head2_h = int(trs[1].find(HP + "tc/" + HP + "cellSz").get("height"))  # 머리 두 줄 합(줄 합침 칸)
    body = trs[3:]
    body_h = [int(tr.find(HP + "tc/" + HP + "cellSz").get("height")) for tr in body]

    info = trs[0]
    by_col = {tc.find(HP + "cellAddr").get("colAddr"): tc for tc in info.findall(HP + "tc")}
    labels = [text_of(by_col[c]) for c in ("0", "6", "10")]
    assert labels[0] == "기관명" and labels[1] == "작성일", labels
    set_text(by_col["3"], "{{ORG}}")
    set_text(by_col["8"], "{{DATE}}")
    set_text(by_col["11"], "{{WRITER}}")
    by_col["10"].find(".//" + HP + "t").text = "{{WLABEL}}"
    head_rows = "".join(ser(tr) for tr in trs[:3])

    # 요원 한 줄 틀: 칸마다 (칸 틀, 문단 틀)
    cells = []
    for tc in body[0].findall(HP + "tc"):
        tc = deepcopy(tc)
        tc.find(HP + "cellAddr").set("rowAddr", "{{R}}")
        tc.find(HP + "cellSz").set("height", "{{H}}")
        sub = tc.find(HP + "subList")
        ps = sub.findall(HP + "p")
        p = deepcopy(ps[0])
        runs = p.findall(HP + "run")
        for r in runs[1:]:
            p.remove(r)
        run = runs[0]
        for ch in list(run):
            run.remove(ch)
        run.text = "{{RUN}}"
        p.set("id", "0")
        for x in ps:
            sub.remove(x)
        sub.text = "{{PS}}"
        cells.append({"tc": ser(tc), "p": ser(p)})
    assert len(cells) == 8, len(cells)

    for tr in trs:
        tbl.remove(tr)
    tbl.append(etree.Comment("ROWS"))
    p7s = ser(p7)
    tbl_open, tbl_close = p7s.split("<!--ROWS-->")
    tbl_open = re.sub(r'rowCnt="\d+"', 'rowCnt="{{ROWCNT}}"', tbl_open, count=1)
    tbl_open = re.sub(r'(<hp:sz width="\d+" widthRelTo="[A-Z]+" height=")\d+(")', r"\g<1>{{TBLH}}\2", tbl_open, count=1)
    assert "{{TBLH}}" in tbl_open and "{{ROWCNT}}" in tbl_open

    hpf = raw["Contents/content.hpf"]
    hpf = re.sub(r"(<opf:meta name=\"CreatedDate\" content=\"text\">)[^<]*", r"\g<1>{{CREATED}}", hpf)
    hpf = re.sub(r"(<opf:meta name=\"ModifiedDate\" content=\"text\">)[^<]*", r"\g<1>{{MODIFIED}}", hpf)
    hpf = re.sub(r"(<opf:meta name=\"date\" content=\"text\">)[^<]*", r"\g<1>{{DATEKO}}", hpf)
    hpf = re.sub(r"(<opf:meta name=\"creator\" content=\"text\">)[^<]*", r"\g<1>user", hpf)
    settings = re.sub(r'<ha:CaretPosition [^>]*/>', '<ha:CaretPosition listIDRef="0" paraIDRef="0" pos="0"/>', raw["settings.xml"])

    tpl = {
        "src": "사용자 관찰일지 한글 파일(2026-11-27)에서 뽑은 하루치 쪽 틀",
        "files": {
            "mimetype": raw["mimetype"],
            "version.xml": raw["version.xml"],
            "Contents/header.xml": raw["Contents/header.xml"],
            "settings.xml": settings,
            "META-INF/container.rdf": raw["META-INF/container.rdf"],
            "META-INF/container.xml": raw["META-INF/container.xml"],
            "META-INF/manifest.xml": raw["META-INF/manifest.xml"],
        },
        "hpf": hpf,
        "secOpen": sec_open,
        "p0First": p0_first,
        "p0Next": p0_next,
        "between": [ser(page[i]) for i in (1, 2, 3, 4)],
        "title": ser(page[5]),
        "afterTitle": ser(page[6]),
        "tblOpen": tbl_open,
        "headRows": head_rows,
        "cells": cells,
        "tblClose": tbl_close,
        "afterTbl": ser(page[8]),
        "foot": ser(page[9]),
        "headH": head_h + head2_h,
        "bodyH": body_h,
    }
    js = json.dumps(tpl, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    # 실제 이름·날짜가 틀에 남지 않았는지 확인: 칸 글자는 머리 글자와 자리표시만 있어야 함
    allowed = {"결", "재", "결재", "결 재", "담당자", "사무국장", "원장", "사회복무요원 일일 관찰일지", "기관명", "작성일", "순번", "성명",
               "배치부서", "근무시간", "출근", "퇴근", "근무내용", "작성자(인)", "특이사항 및 관찰내용", "(태도, 컨디션, 건강, 안전 등)"}
    texts = re.findall(r"<hp:t>([^<]*)</hp:t>", js.replace("<\\/", "</"))
    leftover = [t for t in texts if t.strip() and t not in allowed and not t.startswith("{{") and not t.startswith("※")]
    assert not leftover, f"틀에 실제 내용이 남음: {leftover[:10]}"

    html = open(html_path, encoding="utf-8").read()
    start = '<script type="application/json" id="hwpxTpl">'
    i = html.index(start) + len(start)
    j = html.index("</script>", i)
    html = html[:i] + js + html[j:]
    open(html_path, "w", encoding="utf-8").write(html)
    print("hwpx 틀을 넣었습니다:", len(js), "글자, 요원 줄 높이", body_h, "머리 높이", head_h + head2_h)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
