# Lance, dans le bon ordre, toutes les commandes AUTOMATIQUES des consignes du 17/10.
# Usage (dans le venv, à la racine du projet) :
#     powershell -ExecutionPolicy Bypass -File .\lancer_consignes_17-10.ps1
# Durée : environ 1 h 30 (surtout l'étape 2, avec Mistral). Ne pas fermer la fenêtre.
# Si une étape échoue, le script s'arrête et affiche laquelle.

$ErrorActionPreference = "Continue"
function Etape($titre, [scriptblock]$cmd) {
    Write-Host "`n==================== $titre ====================" -ForegroundColor Cyan
    & $cmd
    if ($LASTEXITCODE -ne 0) { Write-Host "[X] Échec : $titre" -ForegroundColor Red; exit 1 }
}

$review = "results/review_knowledge_table_llm.csv"
$calib  = "results/causal_calibration.json"

Etape "1/6 Self-refine : relance de la requête corrigée" {
    if (Test-Path results\rq3_selfrefine\remediation_triggered_keyword.json) {
        Remove-Item results\rq3_selfrefine\remediation_triggered_keyword.json
    }
    python run_remediation.py --table results/knowledge_table_llm_raw.jsonl --queries data/eval_queries.json --verifiers selfrefine --modes retrieval_loop --unanchored --calibration $calib --output-dir results/rq3_selfrefine --resume
}

Etape "2/6 Ablation N = 0, 1, 2, 3 (environ 1 h)" {
    python run_remediation.py --table results/knowledge_table_llm_raw.jsonl --queries data/eval_queries.json --verifiers labels --modes retrieval_loop --iterations 0 1 2 3 --unanchored --calibration $calib --output-dir results/rq3_ablation_N --resume
}

Etape "3/6 Flux des cas + fichier des mitigations nulles" {
    python review_cases.py flow --review $review
    if (-not (Test-Path results/review_knowledge_table_llm_nulls.csv)) {
        python review_cases.py null-export --review $review
    }
}

Etape "4/6 Fichier pour le deuxième annotateur (30 cas stratifiés)" {
    python review_cases.py iaa-export --review $review --force
}

Etape "5/6 Fiches de l'évaluation humaine (3 évaluateurs)" {
    pip install -q scipy
    python human_eval.py export --raters 3 --config "No retrieval=results/rq3_raw:no_retrieval|lexical" "Retrieval, no verify-revise=results/rq3_raw:retrieval|lexical" "Loop, lexical=results/rq3_raw:retrieval_loop|lexical" "Loop, rule=results/rq3_raw:retrieval_loop|rule" "Loop, labels=results/rq3_raw:retrieval_loop|labels" "Loop, LLM judge=results/rq3_raw:retrieval_loop|llm" "Self-refine=results/rq3_selfrefine:retrieval_loop|selfrefine" "Curated, labels cal.=results/rq3_curated:retrieval_loop|labels" "Loop, labels cal. (ours)=results/rq3_raw_calib:retrieval_loop|labels"
}

Etape "6/6 Intervalles de confiance bootstrap (Tables 2 et 3)" {
    foreach ($t in @("raw", "curated")) {
        python calibrate_retrieval.py --table "results/knowledge_table_llm_$t.jsonl" --gold-review $review --output-dir "results/calibration_$t"
        if ($LASTEXITCODE -ne 0) { exit 1 }
        $f = Get-ChildItem "results/calibration_$t/calibration_*.json" | Sort-Object LastWriteTime | Select-Object -Last 1
        python bootstrap.py table2 --calibration $f.FullName --output "results/bootstrap_table2_$t.json"
        if ($LASTEXITCODE -ne 0) { exit 1 }
    }
    python bootstrap.py table3 --summary results/rq3_raw/table_iv_summary.json results/rq3_raw_calib/table_iv_summary.json results/rq3_curated/table_iv_summary.json results/rq3_selfrefine/table_iv_summary.json results/rq3_ablation_N/table_iv_summary.json --output results/bootstrap_table3.json
}

Write-Host "`n[OK] Toutes les étapes automatiques sont terminées." -ForegroundColor Green
Write-Host "Envoyez à Claude : results\rq3_selfrefine\table_iv_summary.json, results\rq3_ablation_N\table_iv_summary.json,"
Write-Host "results\review_knowledge_table_llm_flow.json, results\bootstrap_table2_raw.json, results\bootstrap_table2_curated.json, results\bootstrap_table3.json"
