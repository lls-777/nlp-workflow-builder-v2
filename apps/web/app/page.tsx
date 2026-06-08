"use client";

import { useEffect, useMemo, useState } from "react";
import {
  createSession,
  executePrepared,
  FileRef,
  OutputResponse,
  prepareRequest,
  PrepareResponse,
  RunResponse,
  submitFeedback,
  submitFollowUp,
  uploadFiles
} from "../lib/api";
import {
  chartRows,
  localizeText,
  outputLabel,
  publicErrorMessage,
  statusLabel,
  tableRows
} from "../lib/display";

type Notice = { kind: "info" | "error" | "success"; text: string } | null;

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string>("");
  const [uploadedFiles, setUploadedFiles] = useState<FileRef[]>([]);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [requestText, setRequestText] = useState("");
  const [followUpText, setFollowUpText] = useState("");
  const [feedbackText, setFeedbackText] = useState("");
  const [prepared, setPrepared] = useState<PrepareResponse | null>(null);
  const [runResult, setRunResult] = useState<RunResponse | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void startNewSession();
  }, []);

  async function startNewSession() {
    setBusy(true);
    try {
      const session = await createSession();
      setSessionId(session.session_id);
      setUploadedFiles([]);
      setPendingFiles([]);
      setRequestText("");
      setFollowUpText("");
      setFeedbackText("");
      setPrepared(null);
      setRunResult(null);
      setNotice(null);
    } catch (error) {
      setNotice({ kind: "error", text: publicErrorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  async function ensureUploadedFiles(): Promise<FileRef[]> {
    if (!sessionId) {
      throw new Error("会话还没有准备好，请稍后重试。");
    }
    if (pendingFiles.length === 0) {
      return uploadedFiles;
    }
    const files = await uploadFiles(sessionId, pendingFiles);
    setUploadedFiles(files);
    setPendingFiles([]);
    return files;
  }

  async function handlePrepare() {
    if (!requestText.trim()) {
      setNotice({ kind: "error", text: "请先描述你的需求。" });
      return;
    }
    setBusy(true);
    try {
      const files = await ensureUploadedFiles();
      const response = await prepareRequest(sessionId, requestText.trim(), files);
      setPrepared(response);
      setRunResult(null);
      setNotice(response.message ? { kind: "info", text: response.message } : null);
    } catch (error) {
      setNotice({ kind: "error", text: publicErrorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  async function handleExecute() {
    if (!prepared) {
      return;
    }
    setBusy(true);
    try {
      const files = await ensureUploadedFiles();
      const result = await executePrepared(sessionId, requestText.trim(), files);
      setRunResult(result);
      setPrepared(null);
      setNotice({ kind: "success", text: "处理完成。" });
    } catch (error) {
      setNotice({ kind: "error", text: publicErrorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  async function handleFollowUp() {
    if (!followUpText.trim()) {
      return;
    }
    setBusy(true);
    try {
      const files = await ensureUploadedFiles();
      const result = await submitFollowUp(sessionId, followUpText.trim(), files);
      setRunResult(result);
      setFollowUpText("");
      setNotice({ kind: "success", text: "已基于同一批文件继续处理。" });
    } catch (error) {
      setNotice({ kind: "error", text: publicErrorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  async function handleFeedback() {
    if (!feedbackText.trim()) {
      return;
    }
    setBusy(true);
    try {
      const response = await submitFeedback(sessionId, feedbackText.trim());
      setPrepared(response);
      setRunResult(null);
      setFeedbackText("");
      setNotice({ kind: "info", text: "已根据反馈更新处理方案，请确认后重新处理。" });
    } catch (error) {
      setNotice({ kind: "error", text: publicErrorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  const visibleFiles = useMemo(
    () => uploadedFiles.map((file) => file.name).concat(pendingFiles.map((file) => file.name)),
    [uploadedFiles, pendingFiles]
  );

  return (
    <main className="shell">
      <header className="header">
        <h1>自然语言工作助手</h1>
        <p>上传文件，然后直接描述你希望完成的事情。</p>
      </header>

      <div className="grid">
        <aside>
          <section className="panel">
            <h2>文件</h2>
            <p className="muted">单文件不超过 20MB，最多 10 个文件，总计不超过 50MB。</p>
            <input
              type="file"
              multiple
              accept=".txt,.md,.pdf,.docx,.csv,.xlsx"
              onChange={(event) => setPendingFiles(Array.from(event.target.files ?? []))}
            />
            {visibleFiles.length > 0 ? (
              <ul className="file-list">
                {visibleFiles.map((fileName) => (
                  <li key={fileName}>{fileName}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">还没有选择文件。</p>
            )}
            <div className="actions">
              <button className="secondary" onClick={startNewSession} disabled={busy}>
                开始新的会话
              </button>
            </div>
          </section>
        </aside>

        <section>
          <div className="panel">
            <h2>描述需求</h2>
            <textarea
              value={requestText}
              onChange={(event) => setRequestText(event.target.value)}
              placeholder="例如：请总结这份资料，或者：退款需要提供什么信息？"
            />
            <div className="actions">
              <button onClick={handlePrepare} disabled={busy || !sessionId}>
                生成处理方案 / 处理新需求
              </button>
            </div>
            {notice ? <NoticeMessage notice={notice} /> : null}
          </div>

          {prepared ? (
            <PlanPanel prepared={prepared} busy={busy} onExecute={handleExecute} />
          ) : null}

          {runResult ? (
            <ResultPanel
              result={runResult}
              followUpText={followUpText}
              feedbackText={feedbackText}
              busy={busy}
              onFollowUpText={setFollowUpText}
              onFeedbackText={setFeedbackText}
              onFollowUp={handleFollowUp}
              onFeedback={handleFeedback}
            />
          ) : null}
        </section>
      </div>
    </main>
  );
}

function NoticeMessage({ notice }: { notice: NonNullable<Notice> }) {
  const className = notice.kind === "error" ? "error" : notice.kind === "success" ? "success" : "notice";
  return <div className={className}>{notice.text}</div>;
}

function PlanPanel({
  prepared,
  busy,
  onExecute
}: {
  prepared: PrepareResponse;
  busy: boolean;
  onExecute: () => void;
}) {
  return (
    <section className="panel">
      <h2>处理方案</h2>
      {prepared.questions.length > 0 ? (
        <div className="notice">
          {prepared.questions.map((question) => (
            <p key={question}>{question}</p>
          ))}
        </div>
      ) : null}
      {prepared.plan_text ? <p className="text-output">{prepared.plan_text}</p> : null}
      {prepared.plan_text ? (
        <div className="actions">
          <button onClick={onExecute} disabled={busy}>
            确认并开始处理
          </button>
        </div>
      ) : null}
    </section>
  );
}

function ResultPanel({
  result,
  followUpText,
  feedbackText,
  busy,
  onFollowUpText,
  onFeedbackText,
  onFollowUp,
  onFeedback
}: {
  result: RunResponse;
  followUpText: string;
  feedbackText: string;
  busy: boolean;
  onFollowUpText: (value: string) => void;
  onFeedbackText: (value: string) => void;
  onFollowUp: () => void;
  onFeedback: () => void;
}) {
  return (
    <section className="panel">
      <h2>处理结果</h2>
      <div className={result.status === "completed" ? "success" : "error"}>
        {result.status === "completed" ? "处理完成" : `处理未完成：${statusLabel(result.status)}`}
      </div>
      {result.outputs.map((output) => (
        <OutputBlock key={`${output.label}-${output.display_type}`} output={output} />
      ))}
      <details className="details">
        <summary>查看执行详情</summary>
        <p>方案版本：{result.version}</p>
        <p>整体状态：{statusLabel(result.status)}</p>
        {result.error_message ? <p>错误摘要：{result.error_message}</p> : null}
        <ol>
          {result.activities.map((activity, index) => (
            <li key={`${activity.title}-${index}`}>
              {activity.title}：{statusLabel(activity.status)}
              {activity.error_message ? `，错误摘要：${activity.error_message}` : ""}
            </li>
          ))}
        </ol>
      </details>

      <div className="panel">
        <h3>继续处理</h3>
        <input
          type="text"
          value={followUpText}
          onChange={(event) => onFollowUpText(event.target.value)}
          placeholder="可以继续提问，或使用同一批文件再次处理"
        />
        <div className="actions">
          <button className="secondary" onClick={onFollowUp} disabled={busy || !followUpText.trim()}>
            提交新问题
          </button>
        </div>
        <textarea
          value={feedbackText}
          onChange={(event) => onFeedbackText(event.target.value)}
          placeholder="需要调整处理方式时，请描述修改要求"
        />
        <div className="actions">
          <button className="secondary" onClick={onFeedback} disabled={busy || !feedbackText.trim()}>
            根据反馈更新结果
          </button>
        </div>
      </div>
    </section>
  );
}

function OutputBlock({ output }: { output: OutputResponse }) {
  return (
    <div className="output-card">
      <h3>{outputLabel(output.label)}</h3>
      {output.display_type === "text" ? (
        <p className="text-output">{localizeText(String(output.value ?? "暂无文字结果。"))}</p>
      ) : null}
      {output.display_type === "table" ? <TableOutput value={output.value} /> : null}
      {output.display_type === "citations" ? <CitationOutput value={output.value} /> : null}
      {output.display_type === "chart" ? <ChartOutput value={output.value} /> : null}
    </div>
  );
}

function TableOutput({ value }: { value: unknown }) {
  const rows = tableRows(value);
  if (rows.length === 0) {
    return <p className="muted">当前结果没有可展示的表格数据。</p>;
  }
  const columns = Object.keys(rows[0]);
  return (
    <table>
      <thead>
        <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index}>
            {columns.map((column) => <td key={column}>{String(row[column] ?? "")}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CitationOutput({ value }: { value: unknown }) {
  const citations = Array.isArray(value) ? value : [];
  if (citations.length === 0) {
    return <p className="muted">未找到足够的文件依据。</p>;
  }
  return (
    <ol>
      {citations.map((item, index) => {
        const citation = item as Record<string, unknown>;
        return (
          <li key={index}>
            <strong>{String(citation.source_name ?? "文件")}</strong>
            {typeof citation.score === "number" ? ` · 相关度 ${citation.score.toFixed(3)}` : ""}
            <p>{String(citation.excerpt ?? "")}</p>
          </li>
        );
      })}
    </ol>
  );
}

function ChartOutput({ value }: { value: unknown }) {
  const rows = chartRows(value);
  const spec = value as { x?: string; y?: string; title?: string };
  const x = spec?.x;
  const y = spec?.y;
  if (!x || !y || rows.length === 0) {
    return <p className="muted">当前结果没有可展示的图表数据。</p>;
  }
  const maxValue = Math.max(...rows.map((row) => Number(row[y]) || 0), 1);
  return (
    <div>
      <p className="muted">{spec.title ?? "图表"}</p>
      {rows.map((row, index) => {
        const numericValue = Number(row[y]) || 0;
        const width = `${Math.max(4, (numericValue / maxValue) * 100)}%`;
        return (
          <div className="bar-row" key={index}>
            <span>{String(row[x] ?? "")}</span>
            <div className="bar" style={{ width }} />
            <span>{String(row[y] ?? "")}</span>
          </div>
        );
      })}
    </div>
  );
}
