#!/usr/bin/env python3
"""만들어 본 결과를 구성 설계로 되돌립니다.

무엇을 하나: 만들어 본 결과(build/observed/)와 구성 설계를 맞대어, 구성 설계가 말한 것과
            실제 문서가 다른 곳만 골라 구성 설계의 '확인할 것'에 얹습니다.
무엇을 안 하나: 구성 설계의 값을 마음대로 고치지 않습니다. 고치는 것은 사람이 화면에서 합니다.

되돌릴 수 있는 것은 '내용을 보기 전에 확률·범위로 말한 것'뿐입니다.
  되돌릴 수 있음 — 표·그림이 들어갈 가능성 · 분량 기준 · 구성 요소 포함 여부 · 큰 항목 제목
  건드리지 않음 — 어떻게 쓸 것인가(방법론) · 내용을 채우면서 정할 것
내용 작성 단계에서 정했다고 해서 구성 설계가 정한 것이 되지는 않습니다.

무엇을 어긋남으로 볼지와 그 기준은 buildplan/rewind-rules.json 에 있습니다.

사용:
  python3 buildplan/rewind.py --scan --all              # 목록만, 고치지 않음
  python3 buildplan/rewind.py --load <문서>              # 구성 설계에 반영
  python3 buildplan/rewind.py --load --all
"""
import glob
import json
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))   # 코드뿌리/buildplan (규칙표)
ROOT = os.path.dirname(BASE)                        # 코드뿌리

# 관측 기록·등록부는 **자료**다 — 뿌리는 build/자료뿌리.py 가 정한다(WP-S2 ①).
# 규칙표(rewind-rules.json)는 코드라 BASE 에서 연다.
import importlib.util as _iu
_사양 = _iu.spec_from_file_location("자료뿌리", os.path.join(ROOT, "build", "자료뿌리.py"))
자료뿌리 = _iu.module_from_spec(_사양)
_사양.loader.exec_module(자료뿌리)

OBS = 자료뿌리.관측뿌리()
sys.path.insert(0, os.path.join(ROOT, "workspace"))

RULES = json.load(open(os.path.join(BASE, "rewind-rules.json"), encoding="utf-8"))
TH = RULES["문턱"]
CAT = RULES["관측"]


def nums(s):
    return [int(x) for x in re.findall(r"\d+", str(s))]


def card(code, 관측, 계획경로=None, 제안값=None, 계획값=None, 실물값=None, 심각도=None):
    """되돌림 카드 하나. 화면에 나가는 말은 여기서부터 사람말로 쓴다."""
    c = dict(CAT[code])
    it = {"개체": c["개체"], "관측": 관측, "성격": c["성격"],
          "심각도": 심각도 or c["심각도"], "바뀌는것": c["바뀌는것"],
          "_관측코드": code}
    if 계획경로:
        it["계획경로"] = 계획경로
    if 제안값 is not None:
        it["제안값"] = 제안값
    if 계획값 is not None:
        it["_계획값"] = 계획값
    if 실물값 is not None:
        it["_실물값"] = 실물값
    return it


# ── 관측 하나하나 ───────────────────────────────────────────────────────

def r01_empty(plan, obs):
    out = []
    filled = obs.get("개체_채워짐") or {}
    for i, o in enumerate(plan.get("개체구성") or []):
        name = o.get("개체")
        if not o.get("포함", True) or name not in filled:
            continue
        if not filled[name]:
            out.append(card("R01", f"'{name}' — 넣기로 했는데 문서에는 비어 있습니다.",
                            계획경로=f"개체구성.{i}.포함", 계획값=True, 실물값=False))
    return out


def r02_r03_elements(plan, obs):
    out = []
    cnt = obs.get("요소개수") or {}
    for i, o in enumerate(plan.get("등장요소_전망") or []):
        name, lv = o.get("요소"), o.get("가능성")
        if name not in cnt:
            continue
        n = cnt[name]
        code = "R02" if name == "표" else "R03"
        if lv in ("높음", "중간") and n == 0:
            sev = "구성과 다릅니다" if lv == "높음" else "확인해 주세요"
            out.append(card(code,
                            f"'{name}' — 들어갈 자리로 봤는데 문서에는 하나도 없습니다.",
                            계획경로=f"등장요소_전망.{i}.가능성", 제안값="낮음",
                            계획값=lv, 실물값=n, 심각도=sev))
        elif lv in ("없음", "낮음") and n >= 1:
            out.append(card(code,
                            f"'{name}' — 거의 안 쓸 것으로 봤는데 문서에는 {n}개 들어갔습니다.",
                            계획경로=f"등장요소_전망.{i}.가능성", 제안값="중간",
                            계획값=lv, 실물값=n, 심각도="확인해 주세요"))
    return out


def seq_host(plan):
    """표준시퀀스가 어느 개체 아래 있는지 — 장르마다 이름이 다르다."""
    for host, m in (plan.get("적용방법론") or {}).items():
        if host.startswith("_"):
            continue
        if ((m.get("구성") or {}).get("목차패턴") or {}).get("표준시퀀스"):
            return host
    return None


def r04_r05_headings(plan, obs):
    out = []
    host = seq_host(plan)
    real = obs.get("큰항목_제목")
    if not host or real is None:
        return out
    base = f"적용방법론.{host}.구성.목차패턴.표준시퀀스"
    want = (((plan["적용방법론"][host].get("구성") or {}).get("목차패턴") or {})
            .get("표준시퀀스") or [])
    diff = [(j, w, r) for j, (w, r) in enumerate(zip(want, real))
            if str(w).strip() != str(r).strip()]
    # 표준시퀀스는 '틀'이라 소재에 맞게 이름이 바뀌는 것이 정상일 수 있다.
    # 절반 넘게 다르면 항목마다 카드를 내지 않고 한 장으로 묶는다 — 안 그러면 화면이 못 쓰게 된다.
    if want and len(diff) > len(want) * TH["제목_어긋남_비율"]:
        out.append(card("R04",
                        f"큰 항목 제목이 구성 설계와 {len(diff)}곳 다릅니다 — "
                        f"구성 설계를 문서에 맞게 바꿀지 봐 주세요.",
                        계획값=list(want), 실물값=list(real)))
    else:
        for j, w, r in diff:
            out.append(card("R04",
                            f"큰 항목 {j + 1}번 — 구성 설계는 '{w}', 문서에는 '{r}'입니다.",
                            계획경로=f"{base}.{j}", 제안값=r, 계획값=w, 실물값=r))
    if len(want) != len(real):
        out.append(card("R05",
                        f"큰 항목을 {len(want)}개로 잡았는데 문서에는 {len(real)}개입니다.",
                        계획값=len(want), 실물값=len(real)))
    return out


def r06_budget(plan, obs):
    out = []
    genre = obs.get("장르")
    spec = RULES["분량_실측"].get(genre) or {}
    unit = spec.get("단위", "개")
    real = obs.get("쪽수") if unit == "쪽" else obs.get("항목수")
    if real is None:
        return out
    ceiling_only = spec.get("방향") == "상한"
    for k, v in ((plan.get("제약") or {}).get("분량예산") or {}).items():
        if str(k).startswith("_"):
            continue
        ns = nums(v)
        if not ns:
            continue
        lo, hi = min(ns), max(ns)
        if lo <= real <= hi:
            continue
        # 1페이지·시행문의 분량예산은 '넘지 마라'는 상한이다. 적게 쓴 것은
        # 어긋남이 아니라 채움도(R10)가 볼 일 — 여기서 잡으면 소음만 는다.
        if ceiling_only and real < lo:
            continue
        aim = hi if real > hi else lo
        if abs(real - aim) < TH["분량_최소차"] or abs(real - aim) < aim * TH["분량_비율"]:
            continue
        out.append(card("R06",
                        f"'{k}' — {v}이어야 하는데 문서는 {real}{unit}입니다.",
                        계획경로=f"제약.분량예산.{k}", 계획값=str(v), 실물값=real))
    return out


def r07_answers(plan, doc_text):
    out = []
    ask = ((plan.get("요구분석") or {}).get("_되묻기_답변") or {})
    for k, v in ask.items():
        if str(k).startswith("_"):
            continue
        s = str(v).strip()
        if len(s) < TH["되묻기_최소길이"]:
            continue
        # 조사가 붙은 채로 찾으면 '항목이라'가 '항목'을 못 찾는다 — 어간만 남긴다
        core = []
        for w in re.split(r"[\s·,()]+", s):
            w = re.sub(r"(으로|에서|이라|라고|입니다|한다|합니다|이고|하고|"
                       r"은|는|이|가|을|를|의|에|도|만|과|와|로)$", "", w)
            if len(w) >= 2:
                core.append(w)
        # '없다'는 답도 답이다 — 문서에 안 나오는 것이 정상이라 검사에서 뺀다
        if re.search(r"없|아니|전부입니다|해당\s*없", s):
            continue
        if len(core) >= 2 and not any(w in doc_text for w in core):
            out.append(card("R07",
                            f"'{k}'에 '{s}'라고 답해 주셨는데, 문서에서 찾을 수 없습니다.",
                            계획경로=f"요구분석._되묻기_답변.{k}", 계획값=s))
    return out


def r08_r10_onepage(plan, obs):
    out = []
    a = obs.get("audit")
    if not a:
        return out
    budget = list(((plan.get("제약") or {}).get("분량예산") or {}).keys())
    first = next((k for k in budget if not str(k).startswith("_")), None)
    path = f"제약.분량예산.{first}" if first else None
    if a.get("sheetMm", 0) > TH["쪽높이_mm"]:
        out.append(card("R08",
                        f"한 장에 담기로 했는데 넘쳤습니다.",
                        계획경로=path, 실물값=a["sheetMm"]))
    if a.get("sumLines", 0) > TH["요약_줄수_상한"]:
        idx = next((i for i, o in enumerate(plan.get("개체구성") or [])
                    if "요약" in str(o.get("개체", ""))), None)
        out.append(card("R09",
                        f"요약을 {TH['요약_줄수_상한']}줄 이내로 하기로 했는데 "
                        f"{a['sumLines']}줄이 됐습니다.",
                        계획경로=f"개체구성.{idx}.비고" if idx is not None else None,
                        실물값=a["sumLines"]))
    # 붙임이 없는 문서에서 채움도가 0으로 나오는 계측 오탐이 있다 — 0이면 만들지 않는다
    if a.get("sparse") and (a.get("contentMm") or 0) > 0:
        out.append(card("R10",
                        f"지면이 {int((a.get('fillRatio') or 0) * 100)}%만 차서 비어 보입니다.",
                        계획경로=path, 실물값=a.get("fillRatio")))
    return out


def r11_r14_full(plan, obs):
    out = []
    budget = [k for k in ((plan.get("제약") or {}).get("분량예산") or {})
              if not str(k).startswith("_")]
    body = next((k for k in budget if "본문" in k), budget[0] if budget else None)
    if obs.get("잘린쪽"):
        out.append(card("R11",
                        f"내용이 잘린 쪽이 {obs['잘린쪽']}쪽 있습니다.",
                        계획경로=f"제약.분량예산.{body}" if body else None,
                        실물값=obs["잘린쪽"]))
    for g in ((plan.get("제약") or {}).get("게이트") or []):
        if "장" in g and "이하" in g:
            ns = nums(g)
            if ns and obs.get("장수", 0) > ns[0]:
                out.append(card("R14",
                                f"장을 {ns[0]}개 이하로 하기로 했는데 "
                                f"{obs['장수']}개입니다.",
                                계획값=ns[0], 실물값=obs["장수"]))
    return out


def r13_gongmun(plan, obs):
    if (obs.get("쪽수") or 1) <= 1:
        return []
    budget = [k for k in ((plan.get("제약") or {}).get("분량예산") or {})
              if not str(k).startswith("_")]
    return [card("R13", f"한 장에 담기로 했는데 {obs['쪽수']}장이 됐습니다.",
                 계획경로=f"제약.분량예산.{budget[0]}" if budget else None,
                 실물값=obs["쪽수"])]


# ── 대조 ────────────────────────────────────────────────────────────────

def doc_text(doc):
    out = []

    def w(o):
        if isinstance(o, str):
            out.append(o)
        elif isinstance(o, dict):
            [w(v) for v in o.values()]
        elif isinstance(o, list):
            [w(v) for v in o]
    w(doc)
    return re.sub(r"<[^>]+>", " ", " ".join(out))


def scan(key, plan, obs, doc):
    genre = obs.get("장르")
    items = (r01_empty(plan, obs) + r02_r03_elements(plan, obs)
             + r04_r05_headings(plan, obs) + r06_budget(plan, obs)
             + r07_answers(plan, doc_text(doc)))
    if genre == "onepage-report":
        items += r08_r10_onepage(plan, obs)
    elif genre == "fullreport":
        items += r11_r14_full(plan, obs)
    elif genre == "gongmun":
        items += r13_gongmun(plan, obs)
    return items


def resolve(plan, live_keys):
    """어긋남이 사라진 대기 카드는 '해소'로 — 고쳤는데도 남아 있으면 화면이 거짓말을 한다."""
    import sys as _s
    _s.path.insert(0, os.path.join(ROOT, "workspace"))
    from apply_edit_any import back_key
    n = 0
    for b in plan.get("되돌림", []):
        if b.get("상태", "확인 전") != "확인 전" or not b.get("_관측코드"):
            continue
        if back_key(b) not in live_keys:
            b["상태"] = "해결됨"
            n += 1
    return n


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if "--scan" not in flags and "--load" not in flags:
        print(__doc__)
        return 2
    load = "--load" in flags
    sys.path.insert(0, os.path.join(ROOT, "workspace"))
    from apply_edit_any import plan_of, send_back, back_key

    docs = {}
    # 등록부는 **세어서** 얻는다 — 셋만 손으로 적어 두면 새 장르가 조용히 빠진다
    # (genres.py 머리말의 그 함정). 자료뿌리가 자료 쪽 뿌리를 안다(WP-S2 ①).
    for p in 자료뿌리.등록부들():
        if os.path.exists(p):
            for d in json.load(open(p, encoding="utf-8")):
                docs[d["filename"]] = d

    keys = args
    if "--all" in flags:
        keys = sorted(os.path.splitext(os.path.basename(f))[0]
                      for f in glob.glob(os.path.join(OBS, "*.json"))
                      if not os.path.basename(f).startswith("_"))

    touched, total, 없음 = set(), 0, []
    for key in keys:
        op = os.path.join(OBS, key + ".json")
        if not os.path.exists(op):
            print(f"· {key}: 아직 만들어 본 결과가 없습니다")
            continue
        path, plan = plan_of(key)
        if not plan:
            없음.append(key)               # 조용히 넘기지 않는다 — 왜 안 나왔는지 알려야 한다
            continue
        obs = json.load(open(op, encoding="utf-8"))
        items = scan(key, plan, obs, docs.get(key, {}))
        print(f"\n■ {key} — 확인할 것 {len(items)}건"
              + (f", 못 잰 것 {len(obs.get('_실패') or [])}건" if obs.get("_실패") else ""))
        for it in items:
            print(f"  [{it['심각도']}] {it['개체']} — {it['관측']}")
            if it.get("제안값") is not None:
                print(f"          → 이렇게 바꾸면 됩니다: {it['제안값']}")
        for why in (obs.get("_실패") or []):
            print(f"  (못 잼) {why}")
        total += len(items)
        if load:
            _, n = send_back(key, items, "자동 검사")
            live = {back_key(i) for i in items}
            _, plan2 = plan_of(key)
            gone = resolve(plan2, live)
            if gone:
                plan2["_수정시각"] = __import__("time").strftime("%Y-%m-%dT%H:%M:%S")
                자료뿌리.원자json(path, plan2, indent=1)     # 원자 쓰기(WP-S2 ③, E-3)
            print(f"  → 구성 설계에 {n}건 반영"
                  + (f", 해결된 것 {gone}건" if gone else ""))
            touched.add(path)

    if 없음:
        print(f"\n구성 설계 없이 만든 문서 {len(없음)}건은 되돌릴 곳이 없어 건너뛰었습니다.")
        print("  " + ", ".join(없음[:8]) + (" 외" if len(없음) > 8 else ""))
    if load and touched:
        for cmd in (["buildplan/render_skeleton.py", "--all"],
                    ["workspace/render_editor_any.py", "--skeletons"]):
            subprocess.run([sys.executable, os.path.join(ROOT, cmd[0]), cmd[1]],
                           capture_output=True, cwd=ROOT)
        print(f"\n구성 설계 화면을 다시 만들었습니다 ({len(touched)}건).")
    elif not load:
        print(f"\n모두 {total}건. 구성 설계에 반영하려면 --load 를 붙이세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
