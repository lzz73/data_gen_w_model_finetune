"""
评估工作台 API - 使用 llamafactory 数据管道进行模型评估
"""
import sys, os, json, threading, uuid, subprocess, re
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.response import ApiResponse

router = APIRouter()

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent

_eval_tasks: dict = {}
_eval_file = PROJECT_ROOT / "eval_tasks.json"
EVAL_DIR = PROJECT_ROOT / "eval_results"
EVAL_DIR.mkdir(parents=True, exist_ok=True)


class EvalConfig(BaseModel):
    model: str = ""
    dataset: str = ""
    template: str = "qwen"
    cutoff_len: int = 1024
    batch_size: int = 8
    metrics: list[str] = ["bleu", "rouge_l"]
    temperature: float = 0.2
    topP: float = 0.9
    max_tokens: int = 256
    max_samples: int = 200
    use_judge: bool = False
    judge_api: str = ""
    judge_key: str = ""
    judge_model: str = ""


def _load_eval_tasks():
    if _eval_file.exists():
        try:
            d = json.loads(_eval_file.read_text(encoding="utf-8"))
            _eval_tasks.update(d)
        except Exception:
            pass

def _save_eval_tasks():
    try:
        _eval_file.write_text(json.dumps(_eval_tasks, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass

def _append_log(tid: str, msg: str):
    _eval_tasks[tid]["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

_load_eval_tasks()


@router.get("/tasks")
def api_eval_tasks():
    return ApiResponse.ok(data=sorted(_eval_tasks.values(), key=lambda t: t["created_at"], reverse=True))


@router.post("/run")
def api_eval_run(config: EvalConfig):
    tid = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    now = datetime.now().isoformat()
    task = {
        "task_id": tid,
        "name": f"评估-{Path(config.model).name}-{config.dataset}",
        "model": config.model,
        "config": config.model_dump(),
        "status": "running",
        "progress": 0,
        "score": None,
        "error": None,
        "results": None,
        "created_at": now,
        "logs": [],
    }
    _eval_tasks[tid] = task
    _save_eval_tasks()
    threading.Thread(target=_run_eval, args=(tid, config.model_dump()), daemon=True).start()
    return ApiResponse.ok(data={"task_id": tid}, message="评估已启动")


@router.get("/report/{task_id}")
def api_eval_report(task_id: str):
    task = _eval_tasks.get(task_id)
    if not task:
        return ApiResponse.fail(message="任务不存在")
    return ApiResponse.ok(data=task)


@router.delete("/tasks/{task_id}")
def api_eval_delete(task_id: str):
    if task_id in _eval_tasks:
        del _eval_tasks[task_id]
        _save_eval_tasks()
        return ApiResponse.ok(message="已删除")
    return ApiResponse.fail(message="任务不存在")


def _run_eval(task_id: str, cfg: dict):
    """使用 llamafactory 的数据管道 + 原生 transformers 推理进行评估"""
    def _update_progress(pct: int, msg: str):
        _eval_tasks[task_id]["progress"] = pct
        _eval_tasks[task_id]["eta"] = f"阶段: {msg}"
        _append_log(task_id, msg)
        print(f">>> [EVAL {datetime.now().strftime('%H:%M:%S')}] {pct}% {msg}", flush=True)
        _save_eval_tasks()

    try:
        _update_progress(5, "正在初始化...")

        from llamafactory.data import get_dataset
        from llamafactory.data.template import get_template_and_fix_tokenizer
        from llamafactory.hparams import get_train_args
        from llamafactory.model import load_tokenizer
        from transformers import AutoModelForCausalLM
        import torch

        ds_name = cfg["dataset"]
        model_path = cfg["model"]
        temp = cfg.get("temperature", 0.2)
        top_p = cfg.get("topP", 0.9)
        max_tok = cfg.get("max_tokens", 256)

        _update_progress(10, f"模型: {Path(model_path).name}")

        template_name = cfg.get("template", "qwen")
        cutoff = cfg.get("cutoff_len", 1024)
        train_args = ["--model_name_or_path", model_path, "--dataset", ds_name,
                       "--template", template_name, "--cutoff_len", str(cutoff),
                       "--max_samples", str(cfg.get("max_samples", 200))]
        model_args, data_args, training_args, finetuning_args, _ = get_train_args(train_args)
        data_args.dataset_dir = str(PROJECT_ROOT / "data")

        _update_progress(15, "加载 tokenizer...")
        tokenizer_module = load_tokenizer(model_args)
        tokenizer = tokenizer_module["tokenizer"]
        template = get_template_and_fix_tokenizer(tokenizer, data_args)

        _update_progress(20, "读取数据集...")

        import json as _json
        data_dir = data_args.dataset_dir or str(PROJECT_ROOT / "data")
        info_file = Path(data_dir) / "dataset_info.json"
        raw_samples = []
        if info_file.exists():
            info = _json.loads(info_file.read_text(encoding="utf-8"))
            ds_entry = info.get(ds_name, {})
            fn = ds_entry.get("file_name", f"{ds_name}.jsonl")
            data_file = Path(data_dir) / fn
            if not data_file.exists():
                data_file = PROJECT_ROOT / "data" / fn
            if data_file.exists():
                raw = data_file.read_text(encoding="utf-8")
                if fn.endswith(".jsonl"):
                    for line in raw.strip().split("\n"):
                        try:
                            raw_samples.append(_json.loads(line))
                        except Exception:
                            pass
                else:
                    loaded = _json.loads(raw)
                    raw_samples = loaded if isinstance(loaded, list) else [loaded]

        max_n = min(cfg.get("max_samples", 200), len(raw_samples))
        if max_n == 0:
            _eval_tasks[task_id]["status"] = "failed"
            _eval_tasks[task_id]["error"] = "数据集为空或格式不匹配"
            _eval_tasks[task_id]["progress"] = 0
            _save_eval_tasks()
            return

        _update_progress(25, f"有效样本: {max_n}")
        _update_progress(30, "加载模型中...")

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = AutoModelForCausalLM.from_pretrained(
            model_path, trust_remote_code=True, local_files_only=True,
            torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
            device_map="auto" if device == "cuda" else None,
        )
        if device == "cpu":
            model = model.to(device)
        model.eval()

        _update_progress(40, "开始推理...")

        predictions = []
        references = []
        total = max_n
        batch_sz = cfg.get("batch_size", 8)
        start_time = datetime.now()

        texts = []
        valid_indices = []
        for i in range(total):
            sample = raw_samples[i]
            inst = sample.get("instruction", "") or sample.get("query", "")
            out = sample.get("output", "") or sample.get("response", "")
            if inst and out:
                messages = [{"role": "user", "content": inst}]
                try:
                    t = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                except Exception:
                    t = inst
                texts.append(t)
                references.append(out)
                valid_indices.append(i)
            predictions.append("")

        for batch_start in range(0, len(texts), batch_sz):
            batch_texts = texts[batch_start:batch_start + batch_sz]
            inputs = tokenizer(batch_texts, return_tensors="pt", padding=True,
                              truncation=True, max_length=cutoff).to(device)

            with torch.no_grad():
                outputs = model.generate(
                    **inputs, max_new_tokens=max_tok,
                    temperature=temp, top_p=top_p,
                    do_sample=True if temp > 0 else False,
                    pad_token_id=tokenizer.eos_token_id,
                )

            for j, out_ids in enumerate(outputs):
                pred = tokenizer.decode(out_ids[inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
                orig_idx = valid_indices[batch_start + j]
                predictions[orig_idx] = pred

            done = batch_start + len(batch_texts)
            pct = min(95, 40 + done / len(texts) * 55)
            elapsed = (datetime.now() - start_time).total_seconds()
            if done > 0:
                eta_sec = (elapsed / done) * (len(texts) - done)
                eta_str = f"{int(eta_sec//60)}分{int(eta_sec%60)}秒" if eta_sec>60 else f"{int(eta_sec)}秒"
            else:
                eta_str = "计算中..."

            _eval_tasks[task_id]["progress"] = round(pct, 1)
            _eval_tasks[task_id]["eta"] = eta_str
            print(f">>> [EVAL {datetime.now().strftime('%H:%M:%S')}] {done}/{len(texts)} ({round(pct)}%) ETA: {eta_str}", flush=True)
            _save_eval_tasks()

        _update_progress(95, "计算指标...")
        scores = _compute_metrics(predictions, references, cfg.get("metrics", ["bleu", "rouge_l"]))

        judge_scores = []
        if cfg.get("use_judge") and cfg.get("judge_api"):
            _update_progress(96, "LLM 评审中...")
            judge_scores = _judge_with_llm(
                [(raw_samples[j].get("instruction",""), references[j], predictions[j])
                 for j in range(min(20, len(predictions)))],
                cfg["judge_api"], cfg.get("judge_key", ""), cfg.get("judge_model", ""), task_id
            )
            scores["llm_judge"] = round(sum(s["score"] for s in judge_scores) / max(len(judge_scores), 1), 2)

        numeric = [v for v in scores.values() if isinstance(v, (int, float))]
        overall = sum(numeric) / len(numeric) if numeric else 0

        _eval_tasks[task_id]["status"] = "completed"
        _eval_tasks[task_id]["progress"] = 100
        _eval_tasks[task_id]["score"] = round(overall, 2)
        _eval_tasks[task_id]["results"] = {
            "scores": scores,
            "total": len(predictions),
            "samples": [{"instruction": raw_samples[j].get("instruction", raw_samples[j].get("query","")),
                         "reference": references[j], "prediction": predictions[j],
                         "judge": judge_scores[k] if k < len(judge_scores) else None}
                        for k, j in enumerate(range(min(20, len(predictions))))],
        }
        _update_progress(100, f"完成! BLEU={scores.get('bleu','N/A')} ROUGE-L={scores.get('rouge_l','N/A')}")

        result_file = EVAL_DIR / f"{task_id}.json"
        result_file.write_text(json.dumps({
            "task_id": task_id,
            "model": model_path,
            "dataset": ds_name,
            "scores": scores,
            "total": len(predictions),
            "predictions": [{"instruction": raw_samples[j].get("instruction", ""),
                            "reference": references[j],
                            "prediction": predictions[j]}
                           for j in range(min(50, len(predictions)))],
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        _save_eval_tasks()

    except Exception as e:
        import traceback
        err = traceback.format_exc()[-400:]
        _eval_tasks[task_id]["status"] = "failed"
        _eval_tasks[task_id]["error"] = str(e)[:250]
        _append_log(task_id, f"错误: {str(e)[:150]}")
        print(f"[EVAL ERROR] {err}", flush=True)
        _save_eval_tasks()


def _compute_metrics(predictions: list[str], references: list[str], metrics: list[str]) -> dict:
    scores = {}
    if not predictions:
        return {"bleu": 0, "rouge_l": 0, "exact_match": 0}
    if "exact_match" in metrics:
        correct = sum(1 for p, r in zip(predictions, references) if p.strip() == r.strip())
        scores["exact_match"] = round(correct / max(len(predictions), 1) * 100, 2)
    if "bleu" in metrics:
        try:
            import nltk
            nltk.data.path.append(str(Path.home() / "nltk_data"))
            from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
            smooth = SmoothingFunction()
            bleus = [sentence_bleu([r.split()], p.split(), smoothing_function=smooth.method1)
                     for p, r in zip(predictions, references) if p and r]
            scores["bleu"] = round(sum(bleus) / max(len(bleus), 1) * 100, 2)
        except ImportError:
            scores["bleu"] = "N/A"
    def _rouge_n(n: int):
        vals = []
        for p, r in zip(predictions, references):
            if not p or not r:
                vals.append(0); continue
            p_ngrams = set(zip(*[p.split()[j:] for j in range(n)])) if len(p.split())>=n else set()
            r_ngrams = set(zip(*[r.split()[j:] for j in range(n)])) if len(r.split())>=n else set()
            overlap = len(p_ngrams & r_ngrams)
            prec = overlap/len(p_ngrams) if p_ngrams else 0
            rec = overlap/len(r_ngrams) if r_ngrams else 0
            f1 = 2*prec*rec/(prec+rec) if (prec+rec)>0 else 0
            vals.append(f1)
        return round(sum(vals)/max(len(vals),1)*100, 2)
    if "rouge_1" in metrics:
        scores["rouge_1"] = _rouge_n(1)
    if "rouge_2" in metrics:
        scores["rouge_2"] = _rouge_n(2)
    if "rouge_l" in metrics:
        def lcs(a, b):
            m, n = len(a), len(b)
            dp = [[0]*(n+1) for _ in range(m+1)]
            for i in range(m):
                for j in range(n):
                    dp[i+1][j+1] = dp[i][j]+1 if a[i]==b[j] else max(dp[i+1][j], dp[i][j+1])
            return dp[m][n]
        rouge_ls = []
        for p, r in zip(predictions, references):
            if not p or not r:
                rouge_ls.append(0); continue
            l = lcs(p, r)
            prec = l/len(p) if p else 0
            rec = l/len(r) if r else 0
            f1 = 2*prec*rec/(prec+rec) if (prec+rec)>0 else 0
            rouge_ls.append(f1)
        scores["rouge_l"] = round(sum(rouge_ls)/max(len(rouge_ls),1)*100, 2)
    return scores


def _judge_with_llm(samples: list, api_url: str, api_key: str, model_name: str, task_id: str) -> list:
    """使用 LLM API 评审预测质量"""
    try:
        import urllib.request, json as _json
        results = []
        total = len(samples)
        for i, (instruction, reference, prediction) in enumerate(samples):
            prompt = f"""你是一个专业的模型评估专家。请对以下微调模型的回答质量进行评审。

【指令】{instruction}
【标准答案】{reference}
【模型回答】{prediction}

请从以下四个维度评分（1-10分）：

1. 核心事实正确性：回答中的事实信息是否与标准答案一致，无错误数据
2. 信息完整性：是否覆盖了标准答案中的所有关键信息点
3. 无幻觉：回答中是否没有编造标准答案中不存在的内容
4. 格式合规性：回答的格式、措辞是否符合专业规范

请严格返回 JSON 格式（不要有其他文字）：
{{"score": 平均分, "factual": 核心事实正确性分, "completeness": 信息完整性分, "no_hallucination": 无幻觉分, "format": 格式合规性分, "reason": "简要综合评价"}}"""

            body = _json.dumps({
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1, "max_tokens": 256
            }).encode("utf-8")

            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            req = urllib.request.Request(
                f"{api_url.rstrip('/')}/chat/completions",
                data=body, headers=headers
            )
            try:
                resp = _json.loads(urllib.request.urlopen(req, timeout=30).read())
                content = resp["choices"][0]["message"]["content"]
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    judge = _json.loads(content[start:end])
                    results.append({
                        "score": int(judge.get("score", 5)),
                        "factual": int(judge.get("factual", 5)),
                        "completeness": int(judge.get("completeness", 5)),
                        "no_hallucination": int(judge.get("no_hallucination", 5)),
                        "format": int(judge.get("format", 5)),
                        "reason": judge.get("reason", ""),
                    })
                else:
                    results.append({"score": 5, "reason": content[:100]})
            except Exception:
                results.append({"score": 5, "reason": "API 调用失败"})
            print(f"  [JUDGE] {i+1}/{total}", flush=True)
        return results
    except Exception:
        return []
