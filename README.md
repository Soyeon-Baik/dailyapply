# DailyApply

매일 아침 PM 채용공고를 자동 수집하고, Claude API로 fit scoring해서 GitHub Pages 대시보드에 보여주는 툴.

**GitHub Actions 매일 자동 실행 → `docs/jobs.json` 업데이트 → GitHub Pages 반영**

---

## 기능

- **자동 스크래핑**: Greenhouse · Lever · Ashby · Workable 공개 API (HTML 스크래핑 아님)
- **필터 파이프라인**: PM title 매칭 → Location 필터 → Visa/clearance hard reject
- **Fit Scoring**: Claude API (claude-sonnet-4-6) + tool_use로 구조화된 0-100점 평가
- **Resume Coaching**: 역할별 키워드, 추천 summary, 강조 bullet, gap handling 제안
- **GitHub Pages 대시보드**: 필터/정렬, 상태 관리(localStorage), 라이트 클린 테마

---

## 빠른 시작

### 1. 로컬 설정

```bash
git clone <your-repo-url>
cd dailyapply

pip3 install -r requirements.txt

cp .env.example .env
# .env 파일에 ANTHROPIC_API_KEY 입력
```

### 2. 이력서 데이터 입력

`data/resume.json`을 실제 데이터로 채워 넣기:

```json
{
  "name": "Your Name",
  "headline": "Senior PM | AI/Search",
  "years_of_experience": 7,
  "visa_status": "requires_sponsorship",
  "target_archetypes": ["AI/ML", "Search", "Consumer"],
  "experience": [...]
}
```

### 3. 회사 목록 조정

`data/companies.json`에 30개 스타터 팩이 포함돼 있음. 각 회사의 ATS slug를 확인해서 수정:

```json
{
  "name": "Anthropic",
  "priority": "high",
  "slugs": {
    "greenhouse": "anthropic",   // https://boards.greenhouse.io/anthropic 에서 확인
    "lever": null,
    "ashby": null,
    "workable": null
  }
}
```

**Slug 확인 방법:**
- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs` 에서 200 응답 확인
- Lever: `https://api.lever.co/v0/postings/{slug}?mode=json` 에서 배열 응답 확인
- Ashby: `https://api.ashbyhq.com/posting-api/job-board/{slug}` 에서 확인
- Workable: `https://apply.workable.com/api/v3/accounts/{slug}/jobs` 에서 확인

### 4. 파이프라인 실행

```bash
python3 main.py
```

### 5. 대시보드 로컬 확인

```bash
cd docs && python3 -m http.server 8080
# http://localhost:8080 에서 확인
```

---

## GitHub Actions 설정

### 1. Repository에 Push

```bash
git init
git add .
git commit -m "init: dailyapply"
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin main
```

### 2. GitHub Secret 추가

Repository → Settings → Secrets and variables → Actions → **New repository secret**

| Name | Value |
|------|-------|
| `ANTHROPIC_API_KEY` | `sk-ant-...` |

### 3. GitHub Pages 활성화

Repository → Settings → Pages → Source: **Deploy from branch** → Branch: `main` → Folder: `/docs`

### 4. 첫 수동 실행

Actions 탭 → **Daily Job Scrape** → **Run workflow**

이후 매일 오전 6시 PST에 자동 실행.

---

## 파일 구조

```
dailyapply/
├── .github/workflows/daily.yml    # 스케줄 + 자동 커밋
├── scrapers/
│   ├── common.py                  # RawJob 모델 + HTML 파싱 유틸
│   ├── greenhouse.py
│   ├── lever.py
│   ├── ashby.py
│   └── workable.py
├── filters/
│   ├── hard_filters.py            # Visa/clearance hard reject + soft concern
│   ├── role_filter.py             # PM title 매칭 (보수적 include + 강한 exclude)
│   └── location_filter.py        # Seattle/CA/NY/Remote
├── scoring/
│   ├── schemas.py                 # ScoredJob, ScoreBreakdown Pydantic 모델
│   ├── prompts.py                 # 시스템 프롬프트 (cache_control)
│   └── scorer.py                  # Claude API tool_use 호출
├── data/
│   ├── resume.json                # 이력서 (직접 편집)
│   ├── companies.json             # 30개 스타터 팩 (slug 편집 필요)
│   ├── blocked_companies.json     # 제외할 회사 목록
│   └── run_log.json               # 실행 로그 (CI가 업데이트)
├── docs/
│   ├── index.html                 # 대시보드 (정적 shell)
│   ├── jobs.json                  # CI가 매일 업데이트
│   └── assets/
│       ├── style.css
│       └── app.js
├── tests/
│   ├── fixtures/                  # 샘플 API 응답
│   ├── conftest.py
│   ├── test_filters.py            # 45개 단위 테스트
│   ├── test_scrapers.py
│   ├── test_scorer.py
│   └── test_publisher.py
├── main.py                        # 파이프라인 오케스트레이터
├── requirements.txt
└── .env.example
```

---

## 스코어링 기준

| 항목 | 점수 | 설명 |
|------|------|------|
| Requirements Match | 0–25 | 요구 스킬/도메인이 이력서와 일치하는가 |
| Domain Alignment | 0–25 | AI/Search/Consumer 등 도메인 매칭 |
| PM Archetype Fit | 0–20 | Consumer/Growth/Platform/AI 아키타입 |
| Evidence Strength | 0–15 | 이력서 bullet로 증명 가능한가 |
| Seniority Fit | 0–10 | 타겟 레벨과 역할 레벨 매칭 |
| Nice-to-have Bonus | 0–5 | 브랜드, 기술 스택, 팀 신호 |

**Fit Score = 합계 (0–100)**

### 별도 필드 (점수와 분리)
- `sponsorship_status`: `does_sponsor` / `unknown` / `does_not_sponsor`
- `location_fit`: `exact` / `remote` / `mismatch`
- `seniority_level`: `too_junior` / `target` / `stretch` / `too_senior` / `unclear`
- `hard_filter`: visa/clearance 구문으로 hard reject 여부

---

## Hard Filter 기준

**즉시 제외 (hard_filter=True):**
- `will not sponsor`, `does not sponsor`, `no sponsorship`, `cannot sponsor`
- `US citizen only`, `U.S. citizen only`
- `security clearance required`, `active clearance`, `secret clearance`, `TS/SCI`

**소프트 우려 (Claude가 sponsorship_status 판단):**
- `must be authorized to work`, `authorized to work in the United States`
- `work authorization required`

---

## 비용 예측

- 런당 스코어링 공고 수: ~20–80개
- 시스템 프롬프트 캐싱: 첫 호출만 cache miss, 이후 ~10% 요금
- **예상 비용: $1–4/day** (claude-sonnet-4-6 기준)

---

## 테스트 실행

```bash
pytest tests/ -v
```

78개 단위 테스트: 필터 로직, HTML 파싱, 타임스탬프 변환, 스코어러 mock, publisher 머지/retention 로직.

---

## 차단 회사 추가

`data/blocked_companies.json`:

```json
["Acme Corp", "Some Company I Don't Want"]
```

---

## 상태 관리

대시보드의 Status 드롭다운 (New / Saved / Applied / Skip)은 **browser localStorage**에 저장됩니다. CI가 `jobs.json`을 업데이트해도 상태는 job ID 기반으로 유지됩니다.
