"use client";

import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  confirmAssessment,
  getQuestionnaire,
  productRiskRange,
  submitAssessment,
} from "@/lib/api";
import type { AssessmentResult, CustomerState, Questionnaire } from "@/lib/types";

const RATINGS = ["C1", "C2", "C3", "C4", "C5"];

type Props = {
  open: boolean;
  onClose: () => void;
  onConfirmed: (state: CustomerState, result: AssessmentResult) => void;
};

/** 问卷以固定表单呈现，计分完全在后端；LLM 不参与提问和计分。 */
export function AssessmentDialog({ open, onClose, onConfirmed }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const [questionnaire, setQuestionnaire] = useState<Questionnaire | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState<{ id: string; result: AssessmentResult } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      getQuestionnaire()
        .then((q) => {
          setQuestionnaire(q);
          setAnswers(q.prefill); // 银行系统已有的信息（如年龄）预选，客户确认或修改
        })
        .catch((e) => setError(e instanceof ApiError ? e.message : "问卷加载失败"));
    }
    if (!open && dialog.open) dialog.close();
  }, [open]);

  function reset() {
    setAnswers(questionnaire?.prefill ?? {});
    setSubmitted(null);
    setError(null);
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "操作失败，请重试。");
    } finally {
      setBusy(false);
    }
  }

  const total = questionnaire?.questions.length ?? 0;
  const answered = Object.keys(answers).length;

  return (
    <dialog
      ref={ref}
      onClose={() => {
        reset();
        onClose();
      }}
      aria-labelledby="assessment-title"
      className="m-auto w-[calc(100%-2rem)] max-w-2xl rounded-sm bg-surface p-0 text-ink backdrop:bg-ink/40"
    >
      <div className="flex max-h-[88vh] flex-col">
        <header className="border-b border-rule px-5 py-4 sm:px-7">
          <div className="flex items-start justify-between gap-4">
            <h2 id="assessment-title" className="font-serif text-xl font-bold">
              {submitted ? "您的测评结果" : (questionnaire?.title ?? "风险承受能力测评")}
            </h2>
            <button
              type="button"
              onClick={() => ref.current?.close()}
              className="shrink-0 rounded-sm px-2 py-1 text-sm text-ink-2 hover:bg-paper"
            >
              关闭
            </button>
          </div>
          {!submitted && questionnaire && (
            <>
              <p className="mt-1 text-xs leading-5 text-ink-3">{questionnaire.disclaimer}</p>
              {Object.keys(questionnaire.prefill).length > 0 && (
                <p className="mt-1 text-xs leading-5 text-ink-2">已根据您在本行登记的资料预选年龄，如有变化可直接修改。</p>
              )}
              <div className="mt-3 flex items-center gap-3 text-xs text-ink-2">
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-rule" aria-hidden>
                  <div
                    className="h-full bg-brand transition-[width]"
                    style={{ width: `${total ? (answered / total) * 100 : 0}%` }}
                  />
                </div>
                <span className="figures">
                  已答 {answered} / {total}
                </span>
              </div>
            </>
          )}
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-7">
          {submitted ? (
            <ResultView result={submitted.result} />
          ) : (
            <ol className="space-y-7">
              {questionnaire?.questions.map((q, index) => (
                <li key={q.id}>
                  <fieldset>
                    <legend className="font-medium leading-7">
                      <span className="figures mr-2 text-ink-3">{index + 1}.</span>
                      {q.text}
                    </legend>
                    <div className="mt-2 grid gap-1.5">
                      {q.options.map((o) => {
                        const checked = answers[q.id] === o.id;
                        return (
                          <label
                            key={o.id}
                            className={`flex cursor-pointer items-start gap-3 rounded-sm border px-3 py-2.5 text-sm leading-6 ${
                              checked ? "border-brand bg-brand-soft" : "border-rule hover:border-ink-3"
                            }`}
                          >
                            <input
                              type="radio"
                              name={q.id}
                              value={o.id}
                              checked={checked}
                              onChange={() => setAnswers((a) => ({ ...a, [q.id]: o.id }))}
                              className="mt-1.5 accent-[var(--brand)]"
                            />
                            {o.text}
                          </label>
                        );
                      })}
                    </div>
                  </fieldset>
                </li>
              ))}
            </ol>
          )}
        </div>

        <footer className="border-t border-rule px-5 py-4 sm:px-7">
          {error && (
            <p role="alert" className="mb-3 text-sm text-danger">
              {error}
            </p>
          )}
          {submitted ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-ink-2">确认后评级生效，有效期 12 个月。</p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={reset}
                  disabled={busy}
                  className="rounded-sm border border-rule px-4 py-2 text-sm hover:border-ink-3"
                >
                  重新作答
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      const state = await confirmAssessment(submitted.id);
                      onConfirmed(state, submitted.result);
                      ref.current?.close();
                    })
                  }
                  className="rounded-sm bg-brand px-4 py-2 text-sm font-medium text-surface disabled:opacity-40"
                >
                  确认评级
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-ink-3">请根据实际情况作答，结果将决定您可购买的产品范围。</p>
              <button
                type="button"
                disabled={busy || !total || answered < total}
                onClick={() =>
                  run(async () => {
                    const res = await submitAssessment(answers);
                    setSubmitted({ id: res.assessment_id, result: res.result });
                  })
                }
                className="shrink-0 rounded-sm bg-brand px-4 py-2 text-sm font-medium text-surface disabled:opacity-40"
              >
                提交测评
              </button>
            </div>
          )}
        </footer>
      </div>
    </dialog>
  );
}

function ResultView({ result }: { result: AssessmentResult }) {
  return (
    <div>
      <div className="flex items-end gap-3">
        <span className="font-serif text-5xl font-bold text-brand">{result.rating}</span>
        <span className="pb-1.5 font-serif text-xl font-bold">{result.rating_name}</span>
      </div>
      <p className="mt-2 leading-7 text-ink-2">{result.description}</p>

      <RatingScale current={result.rating} />

      <dl className="mt-5 grid gap-2 text-sm sm:grid-cols-2">
        <div className="rounded-sm bg-paper px-3 py-2.5">
          <dt className="text-ink-2">测评得分</dt>
          <dd className="figures mt-0.5 text-lg">{result.score} / 100</dd>
        </div>
        <div className="rounded-sm bg-paper px-3 py-2.5">
          <dt className="text-ink-2">可购买的产品风险等级</dt>
          <dd className="figures mt-0.5 text-lg">{productRiskRange(result.max_product_risk)}</dd>
        </div>
      </dl>

      {result.vetoed && (
        <Notice>您选择了「不能接受任何本金亏损」，按规则评为 C1（保守型），仅可购买 PR1 产品。</Notice>
      )}
      {result.warnings.map((w) => (
        <Notice key={w}>{w}</Notice>
      ))}
      {result.notes.map((n) => (
        <p key={n} className="mt-3 text-sm text-ink-2">
          {n}
        </p>
      ))}
    </div>
  );
}

/** 五级评级刻度：当前评级高亮，帮助客户理解自己处在哪一档。 */
function RatingScale({ current }: { current: string }) {
  const index = RATINGS.indexOf(current);
  return (
    <div className="mt-5" aria-label={`评级刻度，当前为 ${current}`}>
      <div className="grid grid-cols-5 gap-1">
        {RATINGS.map((r, i) => (
          <div key={r} className={`h-2 rounded-full ${i <= index ? "bg-brand" : "bg-rule"}`} />
        ))}
      </div>
      <div className="figures mt-1.5 grid grid-cols-5 gap-1 text-center text-xs">
        {RATINGS.map((r) => (
          <span key={r} className={r === current ? "font-bold text-brand" : "text-ink-3"}>
            {r}
          </span>
        ))}
      </div>
    </div>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-3 border-l-2 border-notice bg-notice-soft px-3 py-2 text-sm leading-6 text-ink-2">
      {children}
    </p>
  );
}
