"use client";

import { useEffect, useRef, useState } from "react";

import { RATING_EN, riskRange } from "@/components/Profile";
import { Button, Icon } from "@/components/ui";
import { ApiError, confirmAssessment, getQuestionnaire, submitAssessment } from "@/lib/api";
import { defineCopy, useCopy, useLocale } from "@/lib/i18n";
import type { AssessmentResult, CustomerState, Questionnaire } from "@/lib/types";

const RATINGS = ["C1", "C2", "C3", "C4", "C5"];

const COPY = defineCopy({
  zh: {
    title: "风险承受能力测评",
    resultTitle: "您的测评结果",
    close: "关闭",
    loadFailed: "问卷加载失败",
    failed: "操作失败，请重试。",
    prefilled: "已根据您在本行登记的资料预选年龄，如有变化可直接修改。",
    answered: (a: number, t: number) => `已答 ${a} / ${t}`,
    validity: "确认后评级生效，有效期 12 个月。",
    retake: "重新作答",
    confirm: "确认评级",
    honest: "请根据实际情况作答，结果将决定您可购买的产品范围。",
    submit: "提交测评",
    score: "测评得分",
    eligible: "可购买的产品风险等级",
    vetoed: "您选择了「不能接受任何本金亏损」，按规则评为 C1（保守型），仅可购买 PR1 产品。",
    scale: (r: string) => `评级刻度，当前为 ${r}`,
  },
  en: {
    title: "Risk tolerance profile",
    resultTitle: "Your result",
    close: "Close",
    loadFailed: "Couldn't load the questionnaire",
    failed: "Something went wrong. Please try again.",
    prefilled: "We pre-selected your age from bank records. Change it if it's out of date.",
    answered: (a: number, t: number) => `${a} of ${t} answered`,
    validity: "Your rating takes effect once confirmed and is valid for 12 months.",
    retake: "Answer again",
    confirm: "Confirm rating",
    honest: "Answer honestly. Your result decides which products you can buy.",
    submit: "Submit",
    score: "Score",
    eligible: "Eligible product risk levels",
    vetoed: "You chose “cannot accept any loss of principal,” so you're rated C1 (Conservative) and can buy PR1 products only.",
    scale: (r: string) => `Rating scale, currently ${r}`,
  },
});

type Props = {
  open: boolean;
  onClose: () => void;
  onConfirmed: (state: CustomerState, result: AssessmentResult) => void;
};

/** 问卷以固定表单呈现，计分完全在后端；LLM 不参与提问和计分。手机上从底部弹出。 */
export function AssessmentDialog({ open, onClose, onConfirmed }: Props) {
  const c = useCopy(COPY);
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
        .catch((e) => setError(e instanceof ApiError ? e.message : c.loadFailed));
    }
    if (!open && dialog.open) dialog.close();
  }, [open, c.loadFailed]);

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
      setError(e instanceof ApiError ? e.message : c.failed);
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
      className="mx-0 mt-auto mb-0 w-full max-w-none rounded-t-3xl bg-surface p-0 text-ink backdrop:bg-navy/50 sm:m-auto sm:w-[calc(100%-2rem)] sm:max-w-2xl sm:rounded-3xl"
    >
      <div className="flex max-h-[92vh] flex-col sm:max-h-[88vh]">
        <span aria-hidden className="mx-auto mt-3 h-1 w-10 rounded-full bg-line sm:hidden" />
        <header className="flex flex-col gap-3 px-5 pt-4 pb-3 sm:px-7 sm:pt-6">
          <div className="flex items-start justify-between gap-4">
            <h2 id="assessment-title" className="text-[22px] leading-tight font-extrabold tracking-tight">
              {submitted ? c.resultTitle : (questionnaire?.title ?? c.title)}
            </h2>
            <button
              type="button"
              onClick={() => ref.current?.close()}
              aria-label={c.close}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-fill hover:bg-line"
            >
              <Icon name="close" size={18} />
            </button>
          </div>
          {!submitted && questionnaire && (
            <>
              <p className="text-xs leading-5 text-ink-3">{questionnaire.disclaimer}</p>
              {Object.keys(questionnaire.prefill).length > 0 && <p className="text-xs leading-5 text-ink-2">{c.prefilled}</p>}
              <div className="flex items-center gap-3 text-xs font-semibold text-ink-2">
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line" aria-hidden>
                  <div className="h-full rounded-full bg-brand transition-[width]" style={{ width: `${total ? (answered / total) * 100 : 0}%` }} />
                </div>
                <span className="figures">{c.answered(answered, total)}</span>
              </div>
            </>
          )}
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3 sm:px-7">
          {submitted ? (
            <ResultView result={submitted.result} />
          ) : (
            <ol className="flex flex-col gap-7">
              {questionnaire?.questions.map((q, index) => (
                <li key={q.id}>
                  <fieldset>
                    <legend className="leading-7 font-bold">
                      <span className="figures mr-2 text-ink-3">{index + 1}.</span>
                      {q.text}
                    </legend>
                    <div className="mt-2.5 grid gap-2">
                      {q.options.map((o) => {
                        const checked = answers[q.id] === o.id;
                        return (
                          <label
                            key={o.id}
                            className={`flex cursor-pointer items-start gap-3 rounded-2xl px-4 py-3 text-sm leading-6 transition-colors ${
                              checked ? "bg-brand-soft font-semibold text-brand-strong ring-2 ring-brand" : "bg-fill hover:bg-line"
                            }`}
                          >
                            <input
                              type="radio"
                              name={q.id}
                              value={o.id}
                              checked={checked}
                              onChange={() => setAnswers((a) => ({ ...a, [q.id]: o.id }))}
                              className="mt-1 h-4 w-4 accent-[var(--brand)]"
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

        <footer className="flex flex-col gap-3 border-t border-line px-5 pt-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:px-7">
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          {submitted ? (
            <>
              <p className="text-xs text-ink-2">{c.validity}</p>
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <Button variant="quiet" onClick={reset} disabled={busy}>
                  {c.retake}
                </Button>
                <Button
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      const state = await confirmAssessment(submitted.id);
                      onConfirmed(state, submitted.result);
                      ref.current?.close();
                    })
                  }
                >
                  {c.confirm}
                </Button>
              </div>
            </>
          ) : (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-ink-3">{c.honest}</p>
              <Button
                disabled={busy || !total || answered < total}
                onClick={() =>
                  run(async () => {
                    const res = await submitAssessment(answers);
                    setSubmitted({ id: res.assessment_id, result: res.result });
                  })
                }
              >
                {c.submit}
              </Button>
            </div>
          )}
        </footer>
      </div>
    </dialog>
  );
}

function ResultView({ result }: { result: AssessmentResult }) {
  const c = useCopy(COPY);
  const { locale } = useLocale();
  const name = locale === "en" ? RATING_EN[result.rating] ?? result.rating_name : result.rating_name;
  return (
    <div className="flex flex-col gap-5 pb-2">
      <div className="flex flex-col gap-2 rounded-card bg-navy p-5 text-white">
        <span className="flex items-end gap-3">
          <span className="text-5xl font-extrabold">{result.rating}</span>
          <span className="pb-1.5 text-xl font-bold">{name}</span>
        </span>
        <p className="text-sm leading-6 text-on-navy-2">{result.description}</p>
      </div>

      <RatingScale current={result.rating} />

      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div className="rounded-2xl bg-fill px-4 py-3">
          <dt className="text-ink-2">{c.score}</dt>
          <dd className="figures mt-0.5 text-xl font-extrabold">{result.score} / 100</dd>
        </div>
        <div className="rounded-2xl bg-fill px-4 py-3">
          <dt className="text-ink-2">{c.eligible}</dt>
          <dd className="figures mt-0.5 text-xl font-extrabold">{riskRange(result.max_product_risk)}</dd>
        </div>
      </dl>

      {result.vetoed && <Notice>{c.vetoed}</Notice>}
      {result.warnings.map((w) => (
        <Notice key={w}>{w}</Notice>
      ))}
      {result.notes.map((n) => (
        <p key={n} className="text-sm text-ink-2">
          {n}
        </p>
      ))}
    </div>
  );
}

/** 五级评级刻度：当前评级高亮，帮助客户理解自己处在哪一档。 */
function RatingScale({ current }: { current: string }) {
  const c = useCopy(COPY);
  const index = RATINGS.indexOf(current);
  return (
    <div aria-label={c.scale(current)}>
      <div className="grid grid-cols-5 gap-1.5">
        {RATINGS.map((r, i) => (
          <div key={r} className={`h-2 rounded-full ${i <= index ? "bg-brand" : "bg-line"}`} />
        ))}
      </div>
      <div className="figures mt-1.5 grid grid-cols-5 gap-1.5 text-center text-xs">
        {RATINGS.map((r) => (
          <span key={r} className={r === current ? "font-extrabold text-brand" : "text-ink-3"}>
            {r}
          </span>
        ))}
      </div>
    </div>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return <p className="rounded-2xl bg-notice-soft px-4 py-3 text-sm leading-6 text-notice">{children}</p>;
}
