"""FastAPI application entry point."""

import hashlib
from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile, status
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import create_db_engine
from app.db.session import get_session
from app.db.models import CanonicalizationRun, CohortDefinition, CohortRun, DatasetProduct, FactoryBenchmarkRun, FieldLineage, ImportJob, LineageEvent, MappingCandidate, MappingConflictResolution, MappingDefinition, MappingImportAuditEvent, MappingProposal, MappingRerankAttempt, MappingReview, MappingSet, MappingSuggestion, MappingSuggestionReview, OmopMappingRun, ProductExportAttempt, ProposalResolution, QualityRun, RawRecord, SourceFieldProfile
from app.cohort.service import create_definition, preview_cohort, run_cohort
from app.omop.service import run_omop_mapping
from app.mapping.service import TARGET_REGISTRY, create_import_job, parse_tabular_upload, profile_postgres_table
from app.mapping.llm import DeepSeekMappingProvider, build_safe_rerank_context
from app.mapping.publish import publish_reviewed_mapping_set
from app.mapping.benchmark import SHEETS, run_factory_benchmark
from app.core.config import get_settings
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, select

app = FastAPI(title="Healthcare Dataset Factory", version="0.1.0")


class FactoryBenchmarkRequest(BaseModel):
    jobs: dict[str, str]


@app.post("/benchmarks/factory")
def create_factory_benchmark(request: FactoryBenchmarkRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    """Run the synthetic-fixture-only local retrieval benchmark and return safe aggregates."""
    if set(request.jobs) != set(SHEETS):
        raise HTTPException(422, {"code": "invalid_benchmark_sheets", "message": "Exactly the six synthetic source sheets are required"})
    try:
        return run_factory_benchmark(session, request.jobs, get_settings().factory_benchmark_bundle_path)
    except ValueError as exc:
        raise HTTPException(422, {"code": "invalid_benchmark_input", "message": str(exc)})


@app.get("/benchmarks/factory/{run_id}")
def get_factory_benchmark(run_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Return one immutable aggregate synthetic benchmark report, never Gold answers."""
    run = session.get(FactoryBenchmarkRun, run_id)
    if not run:
        raise HTTPException(404, {"code": "benchmark_not_found", "message": "Benchmark run not found"})
    return {"id": str(run.factory_benchmark_run_id), **run.report}

CONSOLE_HTML = """<!doctype html><html><head><meta charset='utf-8'><title>Healthcare Dataset Factory</title><style>body{font-family:ui-sans-serif,system-ui;background:#071421;color:#dcecff;margin:0}header{padding:28px 8%;background:#0d2438}nav button,.action{background:#163c59;color:#dcecff;border:1px solid #2c678e;padding:9px 12px;margin:4px;border-radius:7px}.action{background:#0e8d7b}main{padding:30px 8%}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}.card{background:#10283d;padding:18px;border-radius:10px}.n{font-size:28px;color:#58d4c4}section{display:none}section.active{display:block}a{color:#58d4c4}</style></head><body><header><h1>Healthcare Dataset Factory</h1><p>Raw hospital data → governed, privacy-aware dataset product</p><nav><button onclick="show('home')">Pipeline</button><button onclick="show('mapping')">Mapping</button><button onclick="show('quality')">Quality</button><button onclick="show('review')">Review Queue</button><button onclick="show('cohort')">Cohort</button><button onclick="show('product')">Dataset Product</button></nav></header><main><section id='home' class='active'><h2>Pipeline</h2><div class='cards' id='cards'></div><button class='action' onclick='load()'>Refresh live status</button></section><section id='mapping'><h2>Mapping</h2><p>Approved source-to-canonical mapping registry.</p><p><a href='/imports/console'>Import a CSV or Excel schema →</a></p><p><a href='/mapping/workbench'>Open Mapping Workbench →</a></p></section><section id='quality'><h2>Quality</h2><p>Versioned quality scores and rule outcomes.</p></section><section id='review'><h2>Review Queue</h2><p>Human review of mapping evidence and decisions.</p></section><section id='cohort'><h2>Cohort</h2><p>Versioned liver cohort, reported as a privacy-safe count.</p></section><section id='product'><h2>Dataset Product</h2><p>CSV + Dataset Card generated under the approved privacy policy.</p></section></main><script>function show(id){document.querySelectorAll('section').forEach(x=>x.classList.remove('active'));document.getElementById(id).classList.add('active')}async function load(){let d=await fetch('/dashboard').then(r=>r.json());let labels=[['Sources',d.sources],['Raw records',d.raw_records],['Mapped fields',d.mapped_fields],['Quality score',d.quality_score],['Review pending',d.review_pending],['Cohort members',d.cohort_members],['Dataset product',d.product.status]];document.getElementById('cards').innerHTML=labels.map(x=>`<div class=card><small>${x[0]}</small><div class=n>${x[1]??'—'}</div></div>`).join('')}load()</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
def console() -> str:
    """Serve the six-view, count-only prototype operator console."""
    return CONSOLE_HTML


IMPORT_CONSOLE_HTML = """<!doctype html><html><head><meta charset='utf-8'><title>Import & Map</title><style>body{font:15px ui-sans-serif,system-ui;margin:0;background:#071421;color:#dcecff}main{max-width:980px;margin:auto;padding:48px 24px}.card{background:#10283d;border:1px solid #28516d;border-radius:12px;padding:22px;margin:18px 0}button{background:#0e8d7b;color:white;border:0;border-radius:7px;padding:10px 15px;cursor:pointer}input{margin:7px 0;color:#dcecff;background:#0d2438;border:1px solid #28516d;border-radius:6px;padding:8px;width:min(600px,95%)}table{width:100%;border-collapse:collapse;margin-top:16px}td,th{padding:10px;border-bottom:1px solid #28516d;text-align:left}small{color:#9db5c7}.badge{padding:3px 7px;border-radius:12px;background:#163c59}a{color:#58d4c4}</style></head><body><main><a href='/'>← Operator console</a><h1>Import & Map</h1><p>CSV, Excel, or a selected PostgreSQL table. This workflow retains only metadata-safe profiles and never persists source cells or connection credentials.</p><div class='card'><h2>1. Select a source</h2><form id='upload'><b>CSV / Excel</b><br><input id='file' type='file' accept='.csv,.xlsx,.xlsm' required><br><button>Profile file</button></form><hr><form id='postgres'><b>PostgreSQL (session only)</b><br><input id='connection' type='password' placeholder='postgresql+psycopg://reader:password@host:5432/database' required><br><input id='schema' placeholder='schema' value='public' required><br><input id='table' placeholder='table' required><br><button>Profile selected table</button></form><p id='status' role='status'></p></div><div class='card'><h2>2. Review suggestions</h2><small>Suggestions are non-executable until a human reviews and publishes a mapping version.</small><p id='actions'></p><table><thead><tr><th>Source field</th><th>Type</th><th>Suggested target</th><th>Method</th><th>Confidence</th><th>Status</th></tr></thead><tbody id='results'><tr><td colspan='6'>No import yet.</td></tr></tbody></table></div></main><script>const s=document.getElementById('status'),r=document.getElementById('results'),a=document.getElementById('actions');async function showJob(j){let z=await fetch('/imports/'+j.id+'/suggestions').then(q=>q.json());s.textContent=`Completed: ${j.field_count} fields profiled; ${j.suggestion_count} suggestions created.`;a.innerHTML=`<button onclick="rerank('${j.id}')">Run optional AI rerank</button> <a href='/mapping/workbench?import=${j.id}'>Open Mapping Workbench →</a>`;r.innerHTML=z.items.map(i=>`<tr><td>${i.field}</td><td>${i.type}</td><td>${i.target||'—'}</td><td>${i.route}</td><td>${i.confidence?Math.round(i.confidence*100)+'%':'—'}</td><td><span class=badge>${i.status}</span></td></tr>`).join('')}async function rerank(id){let q=await fetch('/imports/'+id+'/rerank',{method:'POST'}).then(x=>x.json());s.textContent=`AI rerank: ${q.status}; ${q.reranked||0} suggestions updated. Local candidates remain available.`}document.getElementById('upload').onsubmit=async e=>{e.preventDefault();try{let d=new FormData();d.append('file',document.getElementById('file').files[0]);showJob(await fetch('/imports/uploads',{method:'POST',body:d}).then(async q=>{let b=await q.json();if(!q.ok)throw Error(b.detail?.message||'Import failed');return b}))}catch(x){s.textContent='Unable to import: '+x.message}};document.getElementById('postgres').onsubmit=async e=>{e.preventDefault();try{let q=await fetch('/imports/postgres',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({connection_url:connection.value,schema:schema.value,table:table.value})});let b=await q.json();if(!q.ok)throw Error(b.detail?.message||'PostgreSQL profiling failed');showJob(b)}catch(x){s.textContent='Unable to import: '+x.message}};</script></body></html>"""


@app.get("/imports/console", response_class=HTMLResponse)
def import_console() -> str:
    """Serve the Stage 1 file-import and mapping-suggestion interface."""
    return IMPORT_CONSOLE_HTML


BENCHMARK_CONSOLE_HTML = """<!doctype html><html><head><meta charset='utf-8'><title>Factory Benchmark</title><style>body{font:15px ui-sans-serif,system-ui;margin:0;background:#071421;color:#dcecff}main{max-width:940px;margin:auto;padding:42px 24px}.card{background:#10283d;border:1px solid #28516d;border-radius:12px;padding:20px;margin:16px 0}input{display:block;background:#0d2438;color:#dcecff;border:1px solid #28516d;border-radius:6px;padding:8px;margin:7px 0;width:min(640px,95%)}button{background:#0e8d7b;color:white;border:0;border-radius:6px;padding:9px 12px;cursor:pointer}.metric{display:inline-block;background:#0d2438;padding:14px;margin:5px;border-radius:8px}.muted{color:#9db5c7}.error{color:#ffb2b2}a{color:#58d4c4}</style></head><body><main><a href='/'>← Operator console</a><h1>Factory Benchmark</h1><p class='muted'>Synthetic-fixture-only, retrieval-only benchmark. It stores candidate snapshots and aggregates—not Gold answers or source values.</p><div class='card'><div id='inputs'></div><button onclick='run()'>Run local benchmark</button><p id='status'></p></div><div id='report' class='card'><span class='muted'>No run selected.</span></div></main><script>const sheets=['Source_Patient','Source_Visit','Source_Diagnosis','Source_Lab','Source_Medication','Source_Procedure'];const inputs=document.getElementById('inputs'),statusEl=document.getElementById('status'),report=document.getElementById('report');inputs.innerHTML=sheets.map(s=>`<label>${s}<input id='${s}' placeholder='Import job ID'></label>`).join('');async function run(){let jobs=Object.fromEntries(sheets.map(s=>[s,document.getElementById(s).value.trim()]));statusEl.textContent='Running local retrieval benchmark…';let r=await fetch('/benchmarks/factory',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({jobs})});let j=await r.json();if(!r.ok){statusEl.className='error';statusEl.textContent=j.detail?.message||'Benchmark failed';return}show(j);history.replaceState(null,'','?run='+j.id)}async function show(j){statusEl.className='';statusEl.textContent='Immutable benchmark run: '+j.id;let c=j.counts,q=j.rates;report.innerHTML=`<h2>Results</h2><div class=metric>Top-1<br><b>${(q.top1*100).toFixed(1)}%</b></div><div class=metric>Top-5<br><b>${(q.top5*100).toFixed(1)}%</b></div><div class=metric>Abstention<br><b>${(q.abstention*100).toFixed(1)}%</b></div><div class=metric>Fields<br><b>${c.total}</b></div><p class=muted>Registry ${j.registry.version} · local ${j.retrieval_version} · review required ${c.review_required}</p>`}let runId=new URLSearchParams(location.search).get('run');if(runId)fetch('/benchmarks/factory/'+runId).then(r=>r.json()).then(show);</script></body></html>"""


@app.get("/benchmarks/console", response_class=HTMLResponse)
def benchmark_console() -> str:
    """Serve the safe aggregate-only Factory benchmark console."""
    return BENCHMARK_CONSOLE_HTML


MAPPING_WORKBENCH_HTML = """<!doctype html><html><head><meta charset='utf-8'><title>Mapping Workbench</title><style>body{font:15px ui-sans-serif,system-ui;margin:0;background:#071421;color:#dcecff}main{max-width:1080px;margin:auto;padding:42px 24px}.card{background:#10283d;border:1px solid #28516d;border-radius:12px;padding:20px;margin:16px 0}input,select{background:#0d2438;color:#dcecff;border:1px solid #28516d;border-radius:6px;padding:8px;margin:4px;width:260px}button{background:#0e8d7b;color:white;border:0;border-radius:6px;padding:8px 10px;margin:4px;cursor:pointer}.muted{color:#9db5c7}.candidate{background:#0d2438;border-radius:6px;padding:7px;margin:5px 0}.error{color:#ffb2b2}.ok{color:#58d4c4}a{color:#58d4c4}</style></head><body><main><a href='/'>← Operator console</a><h1>Mapping Workbench</h1><p class='muted'>Human decisions are append-only. Approval requires a retrieved target candidate; no decision executes data mapping.</p><div class='card'><label>Import job ID <input id='job' placeholder='Paste import job ID'></label><button onclick='load()'>Load review queue</button><button onclick='publish()'>Publish approved version</button><p id='status' class='muted'></p></div><div id='queue'></div></main><script>let suggestions=[],candidateByField={};const statusEl=document.getElementById('status'),queue=document.getElementById('queue');const params=new URLSearchParams(location.search);if(params.get('import')){document.getElementById('job').value=params.get('import');load()}async function load(){let id=document.getElementById('job').value.trim();if(!id)return;statusEl.textContent='Loading safe metadata…';try{let [s,c]=await Promise.all([fetch('/imports/'+id+'/suggestions').then(r=>r.json()),fetch('/imports/'+id+'/candidates').then(r=>r.json())]);if(!s.items)throw Error(s.detail?.message||'Import not found');suggestions=s.items;candidateByField=Object.fromEntries(c.items.map(x=>[x.field,x.candidates]));render();statusEl.textContent=`${suggestions.length} fields ready for human review.`}catch(e){statusEl.className='error';statusEl.textContent=e.message}}function render(){queue.innerHTML=suggestions.map(x=>{let cs=candidateByField[x.field]||[];let opts=cs.map(c=>`<option value='${c.target}'>${c.target} · ${Math.round(c.fusion_score*100)}%</option>`).join('');return `<div class=card id='card-${x.id}'><h3>${x.field} <span class=muted>(${x.type}${x.unit?' · '+x.unit:''})</span></h3><p>Current suggestion: <b>${x.target||'Unmapped'}</b> · ${x.route} · ${x.confidence?Math.round(x.confidence*100)+'%':'—'} · <span class=muted>${x.status}</span></p><div>${cs.map(c=>`<div class=candidate>${c.rank}. ${c.target} <span class=muted>BM25 ${c.bm25_score}, local semantic ${c.dense_score}</span></div>`).join('')||'<span class=muted>No safe candidate.</span>'}</div><label>Target <select id='target-${x.id}'><option value=''>Select candidate</option>${opts}</select></label><label>Reviewer <input id='reviewer-${x.id}' value='Jerry'></label><label>Comment <input id='comment-${x.id}' value='Reviewed schema evidence'></label><div><button onclick="decide('${x.id}','approved')">Approve</button><button onclick="decide('${x.id}','edited')">Edit target</button><button onclick="decide('${x.id}','rejected')">Reject</button><button onclick="decide('${x.id}','unmapped')">Mark unmapped</button></div></div>`}).join('')}async function decide(id,action){let target=document.getElementById('target-'+id).value,reviewer=document.getElementById('reviewer-'+id).value,comment=document.getElementById('comment-'+id).value;let body={action,reviewer,comment};if(action==='approved'||action==='edited')body.target=target;let response=await fetch('/mapping-suggestions/'+id+'/reviews',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});let result=await response.json();if(!response.ok){statusEl.className='error';statusEl.textContent=result.detail?.message||'Decision failed';return}document.getElementById('card-'+id).innerHTML='<p class=ok>Decision recorded: '+result.status+(result.target?' → '+result.target:'')+'.</p>'}async function publish(){let id=document.getElementById('job').value.trim();let response=await fetch('/imports/'+id+'/publish-mapping-set',{method:'POST'});let result=await response.json();statusEl.className=response.ok?'ok':'error';statusEl.textContent=response.ok?`Published ${result.scope}@${result.version}: ${result.definition_count} mappings.`:(result.detail?.message||'Publishing failed')}</script></body></html>"""


@app.get("/mapping/workbench", response_class=HTMLResponse)
def mapping_workbench() -> str:
    """Serve the safe human-review workbench for imported suggestions."""
    return MAPPING_WORKBENCH_HTML

@app.get("/dashboard")
def dashboard(session: Session = Depends(get_session)) -> dict[str, object]:
    """Return the console's aggregate-only pipeline summary."""
    mapping = session.scalar(select(func.count()).select_from(MappingDefinition))
    review = session.scalar(select(func.count()).select_from(MappingDefinition)) - session.scalar(select(func.count()).select_from(MappingReview))
    quality = session.scalars(select(QualityRun).where(QualityRun.status == "completed")).first()
    cohort = session.scalars(select(CohortRun).where(CohortRun.status == "completed")).first()
    product = session.scalars(select(ProductExportAttempt).where(ProductExportAttempt.status == "completed")).first()
    return {"sources": 3, "raw_records": session.scalar(select(func.count()).select_from(RawRecord)), "mapped_fields": mapping, "quality_score": (quality.report or {}).get("overall_score") if quality else None, "review_pending": max(review, 0), "cohort_members": cohort.member_count if cohort else 0, "product": {"status": "ready" if product else "not_generated", "patient_count": product.patient_count if product else 0}}

@app.post("/imports/uploads")
async def upload_import(file: UploadFile = File(...), session: Session = Depends(get_session)) -> dict[str, object]:
    """Create a metadata-only CSV/Excel import job and deterministic suggestions."""
    content = await file.read()
    try:
        settings = get_settings()
        table, headers, rows = parse_tabular_upload(file.filename or "upload.csv", content, settings.import_max_rows, settings.import_max_upload_bytes)
        return create_import_job(session, "file", table, headers, rows, hashlib.sha256(content).hexdigest())
    except ValueError as exc: raise HTTPException(422, {"code": "invalid_import", "message": str(exc)})

class PostgresImportRequest(BaseModel):
    connection_url: str
    schema_name: str = Field(alias="schema")
    table: str

@app.post("/imports/postgres")
def postgres_import(request: PostgresImportRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    """Profile one allowlisted PostgreSQL table through a read-only bounded query."""
    settings = get_settings()
    try: return profile_postgres_table(session, request.connection_url, request.schema_name, request.table, {x.strip() for x in settings.import_allowed_postgres_hosts.split(",")}, {int(x.strip()) for x in settings.import_allowed_postgres_ports.split(",")}, settings.import_max_rows)
    except ValueError as exc: raise HTTPException(422, {"code": "invalid_postgres_import", "message": str(exc)})
    except SQLAlchemyError: raise HTTPException(502, {"code": "postgres_connection_failed", "message": "The selected PostgreSQL source could not be profiled"})

@app.get("/imports/{import_job_id}/suggestions")
def import_suggestions(import_job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Return schema metadata and non-executable suggestions; no source values."""
    if not session.get(ImportJob, import_job_id): raise HTTPException(404, {"code": "import_not_found", "message": "Import job not found"})
    suggestions = session.scalars(
        select(MappingSuggestion).where(MappingSuggestion.import_job_id == import_job_id)
    ).all()
    profiles = {
        item.source_field_profile_id: item
        for item in session.scalars(
            select(SourceFieldProfile).where(SourceFieldProfile.import_job_id == import_job_id)
        ).all()
    }
    return {
        "items": [
            {
                "field": profiles[suggestion.source_field_profile_id].field_name,
                "id": str(suggestion.mapping_suggestion_id),
                "table": profiles[suggestion.source_field_profile_id].table_name,
                "type": profiles[suggestion.source_field_profile_id].inferred_type,
                "unit": profiles[suggestion.source_field_profile_id].unit,
                "target": f"{suggestion.target_entity}.{suggestion.target_field}" if suggestion.target_entity else None,
                "confidence": suggestion.confidence,
                "route": suggestion.route,
                "evidence": suggestion.evidence,
                "status": suggestion.status,
            }
            for suggestion in suggestions
        ]
    }


@app.get("/imports/{import_job_id}/candidates")
def import_candidates(import_job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Return local, metadata-only retrieval candidates grouped by source field."""
    if not session.get(ImportJob, import_job_id):
        raise HTTPException(404, {"code": "import_not_found", "message": "Import job not found"})
    profiles = {
        item.source_field_profile_id: item.field_name
        for item in session.scalars(
            select(SourceFieldProfile).where(SourceFieldProfile.import_job_id == import_job_id)
        ).all()
    }
    suggestions = session.scalars(
        select(MappingSuggestion).where(MappingSuggestion.import_job_id == import_job_id)
    ).all()
    items = []
    for suggestion in suggestions:
        candidates = session.scalars(
            select(MappingCandidate)
            .where(MappingCandidate.mapping_suggestion_id == suggestion.mapping_suggestion_id)
            .order_by(MappingCandidate.rank)
        ).all()
        items.append({
            "field": profiles[suggestion.source_field_profile_id],
            "candidates": [
                {
                    "target": f"{candidate.target_entity}.{candidate.target_field}",
                    "domain": candidate.domain,
                    "rank": candidate.rank,
                    "bm25_score": candidate.bm25_score,
                    "dense_score": candidate.dense_score,
                    "fusion_score": candidate.fusion_score,
                    "evidence": candidate.evidence,
                }
                for candidate in candidates
            ],
        })
    return {"items": items, "retrieval_version": "local-hybrid-retrieval@1.0.0"}


@app.post("/imports/{import_job_id}/rerank")
def rerank_import_suggestions(import_job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Optionally rerank local candidates; unavailable AI leaves local review suggestions intact."""
    if not session.get(ImportJob, import_job_id):
        raise HTTPException(404, {"code": "import_not_found", "message": "Import job not found"})
    settings = get_settings()
    if settings.mapping_mode == "RULE_ONLY":
        return {"status": "skipped_rule_only", "attempted": 0, "reranked": 0}
    provider = DeepSeekMappingProvider(settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model, settings.deepseek_timeout_seconds)
    suggestions = session.scalars(select(MappingSuggestion).where(MappingSuggestion.import_job_id == import_job_id)).all()
    profiles = {item.source_field_profile_id: item for item in session.scalars(select(SourceFieldProfile).where(SourceFieldProfile.import_job_id == import_job_id)).all()}
    reranked = 0
    attempted = 0
    for suggestion in suggestions:
        profile = profiles[suggestion.source_field_profile_id]
        candidates = session.scalars(select(MappingCandidate).where(MappingCandidate.mapping_suggestion_id == suggestion.mapping_suggestion_id).order_by(MappingCandidate.rank)).all()
        context = build_safe_rerank_context(
            {"field": profile.field_name, "inferred_type": profile.inferred_type, "unit": profile.unit, "safe_summary": profile.safe_summary},
            [{"target": f"{candidate.target_entity}.{candidate.target_field}", "domain": candidate.domain, "rank": candidate.rank} for candidate in candidates],
        )
        if context is None:
            continue
        attempted += 1
        outcome = provider.rerank(context)
        session.add(MappingRerankAttempt(
            mapping_suggestion_id=suggestion.mapping_suggestion_id, provider=outcome.provider, model=outcome.model,
            status=outcome.status, context_hash=outcome.context_hash, response_hash=outcome.response_hash,
            outcome=outcome.result.model_dump() if outcome.result else None,
        ))
        if outcome.result and not outcome.result.abstain and outcome.result.candidate_target:
            entity, field = outcome.result.candidate_target.split(".", 1)
            suggestion.target_entity = entity
            suggestion.target_field = field
            suggestion.confidence = outcome.result.confidence
            suggestion.route = "llm_rerank"
            suggestion.evidence = {**suggestion.evidence, "llm": {"provider": outcome.provider, "model": outcome.model, "context_hash": outcome.context_hash, "response_hash": outcome.response_hash, "evidence": outcome.result.evidence, "transform_proposal": outcome.result.transform_proposal}}
            reranked += 1
        session.add(MappingImportAuditEvent(import_job_id=import_job_id, mapping_suggestion_id=suggestion.mapping_suggestion_id, event_type="rerank_attempted", details={"provider": outcome.provider, "model": outcome.model, "status": outcome.status, "context_hash": outcome.context_hash, "response_hash": outcome.response_hash}))
    session.commit()
    return {"status": "completed_with_fallback" if reranked < attempted else "completed", "attempted": attempted, "reranked": reranked}


class SuggestionReviewRequest(BaseModel):
    action: str = Field(pattern="^(approved|edited|rejected|unmapped)$")
    reviewer: str = Field(min_length=1, max_length=128)
    target: str | None = None
    transform: str = Field(default="identity", pattern="^(identity|normalize_sex|normalize_unit|parse_date)$")
    comment: str = Field(min_length=1, max_length=500)


@app.post("/mapping-suggestions/{suggestion_id}/reviews")
def review_mapping_suggestion(suggestion_id: str, request: SuggestionReviewRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    """Append one final human decision; it cannot execute or overwrite a mapping registry."""
    suggestion = session.get(MappingSuggestion, suggestion_id)
    if not suggestion:
        raise HTTPException(404, {"code": "suggestion_not_found", "message": "Mapping suggestion not found"})
    if session.scalar(select(MappingSuggestionReview).where(MappingSuggestionReview.mapping_suggestion_id == suggestion_id)):
        raise HTTPException(409, {"code": "suggestion_already_reviewed", "message": "Mapping suggestion already has a final review"})
    target_entity: str | None = None
    target_field: str | None = None
    candidate_targets = {
        f"{candidate.target_entity}.{candidate.target_field}"
        for candidate in session.scalars(select(MappingCandidate).where(MappingCandidate.mapping_suggestion_id == suggestion_id)).all()
    }
    if request.action in {"approved", "edited"}:
        selected_target = request.target or (f"{suggestion.target_entity}.{suggestion.target_field}" if suggestion.target_entity else None)
        registry_targets = {f"{entity}.{field}" for entity, field, _, _ in TARGET_REGISTRY}
        if not selected_target or selected_target not in registry_targets:
            raise HTTPException(422, {"code": "invalid_target", "message": "A registered target is required"})
        if request.action == "approved" and selected_target not in candidate_targets:
            raise HTTPException(422, {"code": "target_not_a_candidate", "message": "Approval requires a retrieved candidate; use edit for another registered target"})
        target_entity, target_field = selected_target.split(".", 1)
    snapshot = {
        "source": {"field": session.get(SourceFieldProfile, suggestion.source_field_profile_id).field_name},
        "suggestion": {"route": suggestion.route, "target": f"{suggestion.target_entity}.{suggestion.target_field}" if suggestion.target_entity else None, "confidence": suggestion.confidence, "evidence": suggestion.evidence},
        "candidate_targets": sorted(candidate_targets),
        "mapping_policy": "mapping-review@1.0.0",
    }
    review = MappingSuggestionReview(
        mapping_suggestion_id=suggestion.mapping_suggestion_id, action=request.action, reviewer=request.reviewer,
        target_entity=target_entity, target_field=target_field, transform=request.transform, comment=request.comment, snapshot=snapshot,
    )
    suggestion.status = request.action
    session.add(review)
    session.add(MappingImportAuditEvent(import_job_id=suggestion.import_job_id, mapping_suggestion_id=suggestion.mapping_suggestion_id, event_type="human_reviewed", details={"action": request.action, "reviewer": request.reviewer, "target": f"{target_entity}.{target_field}" if target_entity else None, "transform": request.transform, "mapping_policy": "mapping-review@1.0.0"}))
    session.commit()
    return {"status": review.action, "target": f"{review.target_entity}.{review.target_field}" if review.target_entity else None, "transform": review.transform}


@app.post("/imports/{import_job_id}/publish-mapping-set")
def publish_mapping_set(import_job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Publish approved external mappings as a reproducible draft registry version."""
    try:
        return publish_reviewed_mapping_set(session, import_job_id)
    except LookupError:
        raise HTTPException(404, {"code": "import_not_found", "message": "Import job not found"})
    except ValueError as exc:
        raise HTTPException(409, {"code": "no_approved_reviews", "message": str(exc)})


@app.get("/health")
def health(response: Response) -> dict[str, str]:
    """Return readiness after verifying PostgreSQL can answer a query."""

    try:
        with create_db_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "database": "unavailable"}
    return {"status": "ok", "database": "ok"}

@app.get("/mapping-sets")
def mapping_sets(scope: str = "liver-core", session: Session = Depends(get_session)) -> dict[str, object]:
    """List versioned mapping sets for a semantic scope."""
    items=session.scalars(select(MappingSet).where(MappingSet.scope==scope)).all()
    return {"items":[{"id":str(x.mapping_set_id),"scope":x.scope,"version":x.version,"status":x.status} for x in items]}

@app.get("/mapping-sets/{mapping_set_id}/definitions")
def mapping_definitions(mapping_set_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Return auditable mapping definitions."""
    definitions=session.scalars(select(MappingDefinition).where(MappingDefinition.mapping_set_id==mapping_set_id)).all()
    if not definitions: raise HTTPException(404, "Mapping set not found")
    return {"items":[{"source":f"{x.source_system}.{x.source_entity}.{x.source_field}","target":f"{x.canonical_entity}.{x.canonical_field}","rule_key":x.rule_key,"confidence":x.confidence,"evidence":x.evidence,"status":x.status} for x in definitions]}

@app.get("/quality-reports/{quality_run_id}")
def quality_report(quality_run_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Return the persisted transparent quality report."""
    run=session.get(QualityRun,quality_run_id)
    if not run or not run.report: raise HTTPException(404, "Quality report not found")
    return run.report

@app.get("/lineage/canonicalization-runs/{run_id}")
def lineage(run_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Return job-level lineage for a canonicalization run."""
    if not session.get(CanonicalizationRun,run_id): raise HTTPException(404, "Canonicalization run not found")
    events=session.scalars(select(LineageEvent).where(LineageEvent.canonicalization_run_id==run_id)).all()
    return {"items":[{"id":str(x.lineage_event_id),"stage":x.stage,"inputs":x.inputs,"outputs":x.outputs,"versions":x.versions,"occurred_at":x.occurred_at} for x in events]}

class ReviewRequest(BaseModel):
    action: str = Field(pattern="^(approved|rejected|edited)$")
    reviewer: str = Field(min_length=1)
    reason: str = Field(min_length=1)

class ProposalRequest(BaseModel):
    proposer: str = Field(default="Jerry", min_length=1)
    replacement: dict[str, object]

class ResolutionRequest(BaseModel):
    action: str = Field(pattern="^(accept_for_next_mapping_set|reject)$")
    resolver: str = Field(default="Jerry", min_length=1)
    reason: str = Field(min_length=1)

class ConflictResolutionRequest(BaseModel):
    action: str = Field(pattern="^(resolve_approve|resolve_reject)$")
    resolver: str = Field(default="Jerry", min_length=1)
    role: str = Field(pattern="^mapping_admin$")
    reason: str = Field(min_length=1)

class OmopRunRequest(BaseModel):
    canonicalization_run_id: str
    retry: bool = False

class CohortDefinitionRequest(BaseModel):
    slug: str = Field(min_length=1)
    version: str = Field(min_length=1)
    condition_tree: dict[str, object]
    creator: str = Field(min_length=1)
    time_window: str = "all_time"

class CohortRunRequest(BaseModel):
    omop_run_id: str
    retry: bool = False

@app.get("/review-queue")
def review_queue(session: Session = Depends(get_session)) -> dict[str, object]:
    """List mappings with no review event yet (unauthenticated prototype queue)."""
    reviewed={x for x in session.scalars(select(MappingReview.mapping_definition_id)).all()}
    items=session.scalars(select(MappingDefinition)).all()
    return {"items":[{"mapping_definition_id":str(x.mapping_definition_id),"source":f"{x.source_entity}.{x.source_field}","target":f"{x.canonical_entity}.{x.canonical_field}","confidence":x.confidence,"evidence":x.evidence,"status":"pending"} for x in items if x.mapping_definition_id not in reviewed]}

@app.post("/mapping-definitions/{mapping_definition_id}/reviews")
def create_review(mapping_definition_id: str, request: ReviewRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    """Append an advisory mapping review; it cannot alter active mappings."""
    definition=session.get(MappingDefinition,mapping_definition_id)
    if not definition: raise HTTPException(404,"Mapping definition not found")
    duplicate=session.scalar(select(MappingReview).where(MappingReview.mapping_definition_id==mapping_definition_id,MappingReview.action==request.action,MappingReview.reviewer==request.reviewer))
    if duplicate: raise HTTPException(409,"Identical review already exists")
    snapshot={"mapping_definition_id":str(definition.mapping_definition_id),"source":f"{definition.source_entity}.{definition.source_field}","target":f"{definition.canonical_entity}.{definition.canonical_field}","rule_key":definition.rule_key,"status":definition.status}
    review=MappingReview(mapping_definition_id=definition.mapping_definition_id,action=request.action,reviewer=request.reviewer,reason=request.reason,snapshot=snapshot); session.add(review); session.commit()
    return {"id":str(review.review_id),"action":review.action,"reviewer":review.reviewer}

@app.post("/mapping-definitions/{mapping_definition_id}/proposals")
def create_proposal(mapping_definition_id: str, request: ProposalRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    """Create an immutable edited-mapping proposal without changing the active set."""
    if not session.get(MappingDefinition,mapping_definition_id): raise HTTPException(404,"Mapping definition not found")
    proposal=MappingProposal(mapping_definition_id=mapping_definition_id,proposer=request.proposer,replacement=request.replacement); session.add(proposal); session.commit()
    return {"id":str(proposal.proposal_id),"status":"submitted"}

@app.post("/mapping-proposals/{proposal_id}/resolutions")
def resolve_proposal(proposal_id: str, request: ResolutionRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    """Append the one allowed prototype resolution for a mapping proposal."""
    if not session.get(MappingProposal,proposal_id): raise HTTPException(404,"Proposal not found")
    if session.scalar(select(ProposalResolution).where(ProposalResolution.proposal_id==proposal_id)): raise HTTPException(409,"Proposal already resolved")
    resolution=ProposalResolution(proposal_id=proposal_id,action=request.action,resolver=request.resolver,reason=request.reason); session.add(resolution); session.commit()
    return {"id":str(resolution.resolution_id),"action":resolution.action}

@app.post("/mapping-definitions/{mapping_definition_id}/conflict-resolutions")
def resolve_conflict(mapping_definition_id: str, request: ConflictResolutionRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    """Append a prototype definition-level conflict-resolution event."""
    if not session.get(MappingDefinition,mapping_definition_id): raise HTTPException(404,"Mapping definition not found")
    event=MappingConflictResolution(mapping_definition_id=mapping_definition_id,action=request.action,resolver=request.resolver,reason=request.reason); session.add(event); session.commit()
    return {"id":str(event.resolution_id),"action":event.action}

@app.get("/lineage/canonicalization-runs/{run_id}/fields")
def field_lineage(run_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Return record-level canonical field lineage."""
    items=session.scalars(select(FieldLineage).where(FieldLineage.canonicalization_run_id==run_id)).all()
    return {"items":[{"canonical_record_id":str(x.canonical_record_id),"canonical":f"{x.canonical_entity}.{x.canonical_field}","source":f"{x.source_entity}.{x.source_field}","source_row_id":str(x.source_row_id),"transform_version":x.transform_version} for x in items]}

@app.post("/omop-runs")
def create_omop_run(request: OmopRunRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    """Run deterministic OMOP-lite mapping for a completed canonicalization run."""
    try: return run_omop_mapping(session, request.canonicalization_run_id, request.retry)
    except (ValueError, RuntimeError) as exc: raise HTTPException(409, str(exc))

@app.get("/omop-runs/{omop_run_id}")
def get_omop_run(omop_run_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Return a public, identifier-safe mapping execution summary."""
    run = session.get(OmopMappingRun, omop_run_id)
    if not run: raise HTTPException(404, "OMOP run not found")
    return {"id": str(run.omop_run_id), "status": run.status, "manifest_hash": run.manifest_hash, "summary": run.summary}

@app.post("/cohort-definitions")
def create_cohort_definition(request: CohortDefinitionRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    """Create an immutable cohort definition version."""
    try: item = create_definition(session, **request.model_dump())
    except ValueError as exc: raise HTTPException(422, str(exc))
    except RuntimeError as exc: raise HTTPException(409, str(exc))
    return {"id": str(item.cohort_definition_id), "slug": item.slug, "version": item.version}

@app.get("/cohort-definitions/{definition_id}")
def get_cohort_definition(definition_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Return an immutable cohort definition without patient data."""
    item = session.get(CohortDefinition, definition_id)
    if not item: raise HTTPException(404, "Cohort definition not found")
    return {"id": str(item.cohort_definition_id), "slug": item.slug, "version": item.version, "condition_tree": item.condition_tree, "time_window": item.time_window}

@app.post("/cohort-definitions/{definition_id}/preview")
def preview(definition_id: str, request: CohortRunRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    """Return only the eligible count; cohort preview does not disclose member IDs."""
    try: return {"member_count": len(preview_cohort(session, definition_id, request.omop_run_id))}
    except LookupError as exc: raise HTTPException(404, str(exc))
    except (ValueError, RuntimeError) as exc: raise HTTPException(409, str(exc))

@app.post("/cohort-definitions/{definition_id}/runs")
def create_cohort_run(definition_id: str, request: CohortRunRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    """Persist a privacy-safe cohort execution and its count."""
    try: return run_cohort(session, definition_id, request.omop_run_id, request.retry)
    except LookupError as exc: raise HTTPException(404, str(exc))
    except (ValueError, RuntimeError) as exc: raise HTTPException(409, str(exc))

@app.get("/cohort-runs/{cohort_run_id}")
def get_cohort_run(cohort_run_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Return count and execution lineage, never cohort member identifiers."""
    run = session.get(CohortRun, cohort_run_id)
    if not run: raise HTTPException(404, "Cohort run not found")
    return {"id": str(run.cohort_run_id), "status": run.status, "member_count": run.member_count, "lineage": run.lineage}

@app.get("/dataset-products")
def dataset_products(session: Session = Depends(get_session)) -> dict[str, object]:
    """List public product summaries without artifact paths or source identifiers."""
    products = session.scalars(select(DatasetProduct)).all()
    items = []
    for product in products:
        attempt = session.scalars(select(ProductExportAttempt).where(ProductExportAttempt.dataset_product_id == product.dataset_product_id, ProductExportAttempt.status == "completed")).first()
        if attempt: items.append({"id": str(product.dataset_product_id), "slug": product.slug, "version": product.version, "patient_count": attempt.patient_count, "record_count": attempt.record_count})
    return {"items": items}

@app.get("/dataset-products/{product_id}/card")
def dataset_product_card(product_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Return the machine-readable, privacy-safe Dataset Card."""
    if not session.get(DatasetProduct, product_id): raise HTTPException(404, "Dataset product not found")
    attempt = session.scalars(select(ProductExportAttempt).where(ProductExportAttempt.dataset_product_id == product_id, ProductExportAttempt.status == "completed")).first()
    if not attempt or not attempt.card: raise HTTPException(404, "Dataset product card not found")
    return attempt.card
